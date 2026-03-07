from collections.abc import Callable
import base64
import json
import os
from importlib import import_module
from typing import Any

from llm.response_models import Decision


def normalize_provider_name(name: str) -> str:
    lowered = name.lower()
    if "gpt" in lowered or lowered == "openai":
        return "openai"
    if "claude" in lowered or lowered == "anthropic":
        return "anthropic"
    return "gemini"


def _extract_json_payload(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return json.loads(cleaned)


def normalize_decision_payload(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload.get("action", "wait")
    parameters = payload.get("parameters")
    reason = payload.get("reason")
    confidence = payload.get("confidence")
    args = payload.get("args")
    task_payload = payload.get("task")

    if not isinstance(parameters, dict):
        parameters = {}

    if parameters.get("keys") is None:
        parameters["keys"] = []

    if isinstance(args, dict):
        parameters = {**args, **parameters}
    if not isinstance(reason, str) or not reason.strip():
        if isinstance(args, str) and args.strip():
            reason = args.strip()
        else:
            reason = "Model returned a partial decision payload"

    if isinstance(confidence, bool) or not isinstance(confidence, int):
        confidence = 0
    confidence = max(0, min(100, confidence))

    if not isinstance(task_payload, dict):
        task_payload = {}

    inferred_goal = task_payload.get("inferred_goal")
    if not isinstance(inferred_goal, str) or not inferred_goal.strip():
        inferred_goal = None

    success_criteria = task_payload.get("success_criteria")
    if not isinstance(success_criteria, str) or not success_criteria.strip():
        success_criteria = None

    is_complete = task_payload.get("is_complete")
    if not isinstance(is_complete, bool):
        is_complete = False

    completion_confidence = task_payload.get("completion_confidence")
    if isinstance(completion_confidence, bool) or not isinstance(completion_confidence, int):
        completion_confidence = 0
    completion_confidence = max(0, min(100, completion_confidence))

    completion_reason = task_payload.get("completion_reason")
    if not isinstance(completion_reason, str) or not completion_reason.strip():
        completion_reason = None

    def is_numeric_coordinate(value: Any) -> bool:
        if isinstance(value, bool):
            return False
        return isinstance(value, (int, float))

    pointer_actions = {"click", "double_click", "drag"}
    has_click_coords = is_numeric_coordinate(parameters.get("x_loc")) and is_numeric_coordinate(parameters.get("y_loc"))
    has_drag_coords = has_click_coords and is_numeric_coordinate(parameters.get("end_x_loc")) and is_numeric_coordinate(parameters.get("end_y_loc"))

    text_value = parameters.get("text")
    has_text = isinstance(text_value, str) and len(text_value.strip()) > 0
    keys_value = parameters.get("keys")
    has_keys = isinstance(keys_value, list) and len(keys_value) > 0

    if action in pointer_actions:
        if action == "drag" and not has_drag_coords:
            action = "wait"
            parameters = {}
            confidence = 0
        elif action in {"click", "double_click"} and not has_click_coords:
            action = "wait"
            parameters = {}
            confidence = 0

    if action == "type_text" and not has_text:
        action = "wait"
        parameters = {}
        confidence = 0

    if action == "press_hotkey" and not has_keys:
        action = "wait"
        parameters = {}
        confidence = 0

    reason_lower = reason.lower()
    uncertainty_markers = (
        "not visible",
        "off-screen",
        "off screen",
        "below the fold",
        "below fold",
        "unclear",
        "cannot",
        "can't",
        "likely",
        "typically",
        "maybe",
        "might",
        "assume",
        "need to scroll",
    )
    reason_indicates_missing_prerequisite = any(marker in reason_lower for marker in uncertainty_markers)
    if action in {"click", "double_click", "drag", "type_text"} and reason_indicates_missing_prerequisite:
        action = "wait"
        parameters = {}
        confidence = min(confidence, 20)

    if is_complete and completion_confidence <= 0:
        completion_confidence = confidence

    return {
        "action": action,
        "parameters": parameters,
        "reason": reason,
        "confidence": confidence,
        "task": {
            "inferred_goal": inferred_goal,
            "success_criteria": success_criteria,
            "is_complete": is_complete,
            "completion_confidence": completion_confidence,
            "completion_reason": completion_reason,
        },
    }


def _build_openai_input(
    messages: list[dict[str, str]],
    image_base64: str,
) -> list[dict[str, Any]]:
    response_input: list[dict[str, Any]] = []
    for message in messages:
        response_input.append(
            {
                "role": message["role"],
                "content": [{"type": "input_text", "text": message["content"]}],
            }
        )
    response_input.append(
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "Analyze the screenshot and return only valid JSON."},
                {"type": "input_image", "image_url": f"data:image/jpeg;base64,{image_base64}"},
            ],
        }
    )
    return response_input


def build_openai_adapter(
    client: Any | None = None,
    model: str = "gpt-4.1-mini",
    api_key: str | None = None,
) -> Callable[..., Decision]:
    runtime_client = client
    if runtime_client is None:
        openai_module = import_module("openai")
        runtime_client = openai_module.OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))

    def adapter(*, messages: list[dict[str, str]], image_base64: str, **_: Any) -> Decision:
        response = runtime_client.responses.create(
            model=model,
            input=_build_openai_input(messages, image_base64),
        )
        return Decision.model_validate(normalize_decision_payload(_extract_json_payload(response.output_text)))

    return adapter


def build_gemini_adapter(
    client: Any | None = None,
    model: str = "gemini-2.5-flash",
    api_key: str | None = None,
) -> Callable[..., Decision]:
    runtime_client = client
    types_module = import_module("google.genai.types")
    if runtime_client is None:
        genai_module = import_module("google.genai")
        runtime_client = genai_module.Client(api_key=api_key or os.getenv("GEMINI_API_KEY"))

    def adapter(*, messages: list[dict[str, str]], image_base64: str, **_: Any) -> Decision:
        prompt_text = "\n\n".join(message["content"] for message in messages)
        image_part = types_module.Part.from_bytes(
            data=base64.b64decode(image_base64),
            mime_type="image/jpeg",
        )
        response = runtime_client.models.generate_content(
            model=model,
            contents=[
                prompt_text,
                image_part,
            ],
            config={"response_mime_type": "application/json"},
        )
        return Decision.model_validate(normalize_decision_payload(_extract_json_payload(response.text)))

    return adapter


def build_default_client() -> "LlmClient":
    return LlmClient(
        {
            "openai": build_openai_adapter(),
            "gemini": build_gemini_adapter(),
        }
    )


class LlmClient:
    def __init__(self, adapters: dict[str, Callable[..., Any]] | None = None) -> None:
        self.adapters = adapters or {}

    def register_adapter(self, provider: str, adapter: Callable[..., Any]) -> None:
        self.adapters[normalize_provider_name(provider)] = adapter

    def _coerce_decision(self, result: Any) -> Decision:
        if isinstance(result, Decision):
            return result
        if isinstance(result, dict):
            return Decision.model_validate(normalize_decision_payload(result))
        raise TypeError("Provider adapter must return a Decision or decision-shaped dict")

    def analyze_screen(self, provider: str, **payload: Any) -> Decision:
        provider_name = normalize_provider_name(provider)
        adapter = self.adapters.get(provider_name)
        if adapter is None:
            raise ValueError(f"No adapter configured for provider: {provider_name}")
        return self._coerce_decision(adapter(**payload))
