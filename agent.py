from dataclasses import dataclass
from pathlib import Path
from typing import Any

from llm.prompts import build_messages
from utils.helpers import encode_image_to_base64, image_fingerprint, resize_image_for_llm


def write_debug_artifact(path: str, content: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


@dataclass
class CycleResult:
    action: str
    confidence: int
    reason: str
    metadata: dict[str, Any]
    executed: bool
    image: Any | None = None
    execution_result: dict[str, Any] | None = None


def _analyze_with_retries(
    llm_client: Any,
    provider: str,
    image: Any,
    image_base64: str,
    metadata: dict[str, Any],
    messages: list[dict[str, str]],
    max_retries: int,
    retry_backoff_seconds: float,
    sleep_fn,
    model: str | None = None,
) -> Any:
    attempts = max(1, max_retries)
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return llm_client.analyze_screen(
                provider=provider,
                model=model,
                image=image,
                image_base64=image_base64,
                metadata=metadata,
                messages=messages,
            )
        except Exception as exc:
            last_error = exc
            if attempt >= attempts:
                break
            sleep_fn(retry_backoff_seconds * attempt)
    message = f"Provider {provider} request failed after {attempts} attempts"
    if model:
        message += f" using model {model}"
    if last_error is not None:
        message += f": {last_error}"
    raise RuntimeError(message)


def run_cycle(
    capture_service: Any,
    llm_client: Any,
    executor: Any,
    provider: str,
    title_regex: str,
    operator_goal: str,
    confidence_threshold: int,
    dry_run: bool,
    preferred_hwnd: int | None = None,
    llm_max_width: int = 1024,
    llm_max_height: int = 1024,
    llm_jpeg_quality: int = 70,
    max_retries: int = 1,
    retry_backoff_seconds: float = 0.5,
    sleep_fn=None,
    model: str | None = None,
    stagnation_count: int = 0,
    recovery_wait_threshold: int = 3,
    action_stagnation_count: int = 0,
    recovery_action_threshold: int = 3,
    recovery_hotkey_min_confidence: int = 50,
    past_actions: list[dict[str, Any]] | None = None,
) -> CycleResult:
    runtime_sleep = sleep_fn or __import__("time").sleep
    image, metadata = capture_service.capture(title_regex, preferred_hwnd=preferred_hwnd)
    llm_image = resize_image_for_llm(image, llm_max_width, llm_max_height)
    runtime_metadata = {
        **metadata,
        "llm_image_width": llm_image.width,
        "llm_image_height": llm_image.height,
        "llm_frame_fingerprint": image_fingerprint(llm_image),
    }
    messages = build_messages(
        operator_goal=operator_goal, 
        named_regions=metadata.get("named_regions"), 
        past_actions=past_actions
    )
    if action_stagnation_count >= recovery_action_threshold:
        messages = [
            *messages,
            {
                "role": "user",
                "content": (
                    "Recent actions repeated without measurable progress. "
                    "Avoid repeating the same interaction target. "
                    "Choose a safer alternative action that gathers new information, "
                    "or return wait if no safe alternative exists."
                ),
            },
        ]
    image_base64 = encode_image_to_base64(llm_image, quality=llm_jpeg_quality)
    decision = _analyze_with_retries(
        llm_client=llm_client,
        provider=provider,
        model=model,
        image=llm_image,
        image_base64=image_base64,
        metadata=runtime_metadata,
        messages=messages,
        max_retries=max_retries,
        retry_backoff_seconds=retry_backoff_seconds,
        sleep_fn=runtime_sleep,
    )

    forced_hotkey_recovery = False

    if decision.action == "wait" and stagnation_count >= recovery_wait_threshold:
        recovery_messages = [
            *messages,
            {
                "role": "user",
                "content": (
                    "Progress has stalled with repeated wait decisions. "
                    "Choose the safest non-wait exploratory action that could reveal missing context. "
                    "Only return wait if no safe interaction exists."
                ),
            },
        ]
        decision = _analyze_with_retries(
            llm_client=llm_client,
            provider=provider,
            model=model,
            image=llm_image,
            image_base64=image_base64,
            metadata=runtime_metadata,
            messages=recovery_messages,
            max_retries=max_retries,
            retry_backoff_seconds=retry_backoff_seconds,
            sleep_fn=runtime_sleep,
        )

        if decision.action == "wait" or decision.confidence < confidence_threshold:
            forced_hotkey_recovery = True
            hotkey_messages = [
                *messages,
                {
                    "role": "user",
                    "content": (
                        "Progress remains stalled. Return exactly one press_hotkey action only. "
                        "Do not use click, drag, or type_text. "
                        "Choose the safest key combo to reveal more context (for example Escape to close overlays "
                        "or a page navigation key to move the viewport)."
                    ),
                },
            ]
            decision = _analyze_with_retries(
                llm_client=llm_client,
                provider=provider,
                model=model,
                image=llm_image,
                image_base64=image_base64,
                metadata=runtime_metadata,
                messages=hotkey_messages,
                max_retries=max_retries,
                retry_backoff_seconds=retry_backoff_seconds,
                sleep_fn=runtime_sleep,
            )

    task_assessment = getattr(decision, "task", None)
    task_complete = bool(getattr(task_assessment, "is_complete", False))
    task_completion_confidence = getattr(task_assessment, "completion_confidence", 0)
    if not isinstance(task_completion_confidence, int):
        task_completion_confidence = 0
    task_completion_reason = getattr(task_assessment, "completion_reason", None)
    if not isinstance(task_completion_reason, str) or not task_completion_reason.strip():
        task_completion_reason = decision.reason
    inferred_goal = getattr(task_assessment, "inferred_goal", None)
    if not isinstance(inferred_goal, str) or not inferred_goal.strip():
        inferred_goal = operator_goal

    if task_complete and task_completion_confidence >= confidence_threshold:
        return CycleResult(
            action=decision.action,
            confidence=task_completion_confidence,
            reason=task_completion_reason,
            metadata=runtime_metadata,
            executed=False,
            image=image,
            execution_result={
                "action": decision.action,
                "executed": False,
                "goal_complete": True,
                "goal_completion_reason": task_completion_reason,
                "goal_completion_confidence": task_completion_confidence,
                "inferred_goal": inferred_goal,
            },
        )

    effective_threshold = confidence_threshold
    if forced_hotkey_recovery and decision.action == "press_hotkey":
        effective_threshold = min(confidence_threshold, recovery_hotkey_min_confidence)

    if decision.confidence < effective_threshold:
        return CycleResult(
            action=decision.action,
            confidence=decision.confidence,
            reason=decision.reason,
            metadata=runtime_metadata,
            executed=False,
            image=image,
            execution_result={
                "action": decision.action,
                "executed": False,
                "recovery_hotkey_attempted": forced_hotkey_recovery,
                "goal_complete": task_complete,
                "goal_completion_reason": task_completion_reason if task_complete else None,
                "goal_completion_confidence": task_completion_confidence,
                "inferred_goal": inferred_goal,
            },
        )
    execution_result = executor.execute(decision=decision, metadata=runtime_metadata, dry_run=dry_run)
    if isinstance(execution_result, dict):
        execution_result = {
            **execution_result,
            "recovery_hotkey_attempted": forced_hotkey_recovery,
            "goal_complete": task_complete,
            "goal_completion_reason": task_completion_reason if task_complete else None,
            "goal_completion_confidence": task_completion_confidence,
            "inferred_goal": inferred_goal,
        }
    return CycleResult(
        action=decision.action,
        confidence=decision.confidence,
        reason=decision.reason,
        metadata=runtime_metadata,
        executed=execution_result["executed"],
        image=image,
        execution_result=execution_result,
    )


class DesktopAutomationAgent:
    def __init__(
        self,
        capture_service: Any,
        llm_client: Any,
        executor: Any,
        settings: Any,
    ) -> None:
        self.capture_service = capture_service
        self.llm_client = llm_client
        self.executor = executor
        self.settings = settings
        self.state = "idle"
        self._consecutive_waits = 0
        self._recovery_wait_threshold = 3
        self._consecutive_stagnant_actions = 0
        self._recovery_action_threshold = 3
        self._recovery_hotkey_min_confidence = 50
        self._last_action_signature: tuple[Any, ...] | None = None
        self._past_actions: list[dict[str, Any]] = []

    def reset_cycle_state(self) -> None:
        self._consecutive_waits = 0
        self._consecutive_stagnant_actions = 0
        self._last_action_signature = None
        self._past_actions = []

    def _build_action_signature(self, result: CycleResult) -> tuple[Any, ...] | None:
        execution_result = result.execution_result if isinstance(result.execution_result, dict) else None
        if not isinstance(execution_result, dict):
            return None
        if not execution_result.get("executed"):
            return None

        action = execution_result.get("action")
        if not isinstance(action, str):
            return None

        if "coordinates" in execution_result and isinstance(execution_result["coordinates"], tuple):
            x, y = execution_result["coordinates"]
            if isinstance(x, int) and isinstance(y, int):
                return (
                    action,
                    round(x / 40),
                    round(y / 40),
                )

        if "start" in execution_result and "end" in execution_result:
            start = execution_result["start"]
            end = execution_result["end"]
            if (
                isinstance(start, tuple)
                and len(start) == 2
                and isinstance(end, tuple)
                and len(end) == 2
                and all(isinstance(v, int) for v in (*start, *end))
            ):
                return (
                    action,
                    round(start[0] / 40),
                    round(start[1] / 40),
                    round(end[0] / 40),
                    round(end[1] / 40),
                )

        if action == "press_hotkey":
            keys = execution_result.get("keys")
            if isinstance(keys, list):
                normalized = tuple(str(key).lower() for key in keys)
                return (action, normalized)

        if action == "type_text":
            text = execution_result.get("text")
            if isinstance(text, str):
                normalized = text.strip().lower()
                if normalized:
                    return (action, normalized[:80])

        return None

    def run_once(
        self,
        provider: str | None = None,
        title_regex: str | None = None,
        preferred_hwnd: int | None = None,
    ) -> CycleResult:
        result = run_cycle(
            capture_service=self.capture_service,
            llm_client=self.llm_client,
            executor=self.executor,
            provider=provider or self.settings.provider.name,
            title_regex=title_regex or self.settings.window.title_regex,
            operator_goal=self.settings.prompt.operator_goal,
            confidence_threshold=self.settings.runtime.confidence_threshold,
            dry_run=self.settings.runtime.dry_run,
            preferred_hwnd=preferred_hwnd,
            llm_max_width=self.settings.runtime.llm_max_width,
            llm_max_height=self.settings.runtime.llm_max_height,
            llm_jpeg_quality=self.settings.runtime.llm_jpeg_quality,
            max_retries=self.settings.runtime.max_retries,
            retry_backoff_seconds=self.settings.runtime.retry_backoff_seconds,
            model=self.settings.provider.model,
            stagnation_count=self._consecutive_waits,
            recovery_wait_threshold=self._recovery_wait_threshold,
            action_stagnation_count=self._consecutive_stagnant_actions,
            recovery_action_threshold=self._recovery_action_threshold,
            recovery_hotkey_min_confidence=self._recovery_hotkey_min_confidence,
            past_actions=self._past_actions,
        )

        execution_result = result.execution_result if isinstance(result.execution_result, dict) else {}
        goal_complete = bool(execution_result.get("goal_complete"))
        executed = bool(execution_result.get("executed"))
        action_signature = self._build_action_signature(result)

        if action_signature is None:
            self._consecutive_stagnant_actions = 0
            self._last_action_signature = None
        elif action_signature == self._last_action_signature:
            self._consecutive_stagnant_actions += 1
        else:
            self._last_action_signature = action_signature
            self._consecutive_stagnant_actions = 1

        if goal_complete:
            self._consecutive_waits = 0
            self._consecutive_stagnant_actions = 0
            self._last_action_signature = None
        elif not executed:
            self._consecutive_waits += 1
        else:
            self._consecutive_waits = 0

        self._past_actions.append({
            "action": result.action,
            "reason": result.reason,
            "executed": executed,
        })
        if len(self._past_actions) > 5:
            self._past_actions.pop(0)

        return result
