# Local LLM Vision Desktop Automation Agent Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Windows-only Python MVP with a native desktop control panel that captures a single target application window, asks a selected vision-capable LLM for a structured action, and safely executes the result with optional dry-run and debug logging.

**Architecture:** The system follows an `observe -> decide -> act` loop behind a native desktop operator panel. Capture, LLM analysis, action execution, and UI state publishing are separated behind narrow interfaces so the loop stays simple and later additions like fallback providers, OpenCV assists, local vision backends, or a remote web dashboard do not require a redesign.

**Tech Stack:** Python 3.11+, PySide6, typer, pydantic, pydantic-settings, PyYAML, mss, Pillow, pywin32, pygetwindow, pydirectinput, pynput, loguru, google-generativeai or google-genai, openai, anthropic, instructor, pytest

---

### Task 1: Bootstrap the repository skeleton

**Files:**
- Create: `requirements.txt`
- Create: `config.yaml`
- Create: `main.py`
- Create: `agent.py`
- Create: `ui/__init__.py`
- Create: `ui/main_window.py`
- Create: `ui/view_models.py`
- Create: `capture/__init__.py`
- Create: `capture/window_capture.py`
- Create: `llm/__init__.py`
- Create: `llm/client.py`
- Create: `llm/prompts.py`
- Create: `llm/response_models.py`
- Create: `actions/__init__.py`
- Create: `actions/executor.py`
- Create: `interaction/__init__.py`
- Create: `interaction/mouse_dynamics.py`
- Create: `interaction/timing_engine.py`
- Create: `interaction/variance_injector.py`
- Create: `vision/__init__.py`
- Create: `vision/element_detector.py`
- Create: `utils/__init__.py`
- Create: `utils/helpers.py`
- Create: `tests/__init__.py`

**Step 1: Write the failing test**

```python
from pathlib import Path


def test_project_entrypoints_exist():
    assert Path("main.py").exists()
    assert Path("agent.py").exists()
    assert Path("llm/client.py").exists()
```

Save as `tests/test_project_layout.py`.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_project_layout.py -v`
Expected: FAIL because the files do not exist yet.

**Step 3: Write minimal implementation**

Create the package skeleton and minimal placeholders, for example:

```python
def main() -> None:
    raise SystemExit(0)


if __name__ == "__main__":
    main()
```

Put matching stubs in the other files so imports work.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_project_layout.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add requirements.txt config.yaml main.py agent.py capture llm actions interaction vision utils tests/test_project_layout.py
git commit -m "chore: scaffold desktop automation agent"
```

Add `ui` to the staged paths when you create the commit.

### Task 2: Add config models and default settings

**Files:**
- Create: `settings.py`
- Modify: `config.yaml`
- Test: `tests/test_settings.py`

**Step 1: Write the failing test**

```python
from settings import AppSettings


def test_settings_load_nested_window_and_runtime_defaults():
    settings = AppSettings.model_validate(
        {
            "window": {"title_regex": "Calculator"},
            "runtime": {"confidence_threshold": 80},
        }
    )

    assert settings.window.title_regex == "Calculator"
    assert settings.runtime.confidence_threshold == 80
    assert settings.runtime.dry_run is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_settings.py::test_settings_load_nested_window_and_runtime_defaults -v`
Expected: FAIL with `ModuleNotFoundError` or missing fields.

**Step 3: Write minimal implementation**

```python
from pydantic import BaseModel, Field


class WindowSettings(BaseModel):
    title_regex: str


class RuntimeSettings(BaseModel):
    confidence_threshold: int = 80
    dry_run: bool = True


class AppSettings(BaseModel):
    window: WindowSettings
    runtime: RuntimeSettings = Field(default_factory=RuntimeSettings)
```

Update `config.yaml` with representative defaults for provider, prompt, debug, and interaction sections.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_settings.py::test_settings_load_nested_window_and_runtime_defaults -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add settings.py config.yaml tests/test_settings.py
git commit -m "feat: add typed application settings"
```

### Task 3: Define structured LLM response models

**Files:**
- Modify: `llm/response_models.py`
- Test: `tests/test_response_models.py`

**Step 1: Write the failing test**

```python
import pytest
from pydantic import ValidationError

from llm.response_models import Decision


def test_click_decision_accepts_percent_coordinates():
    decision = Decision.model_validate(
        {
            "action": "click",
            "parameters": {"x_percent": 50.0, "y_percent": 25.0},
            "reason": "Target button is visible",
            "confidence": 92,
        }
    )

    assert decision.action == "click"
    assert decision.parameters.x_percent == 50.0


def test_confidence_must_be_between_zero_and_hundred():
    with pytest.raises(ValidationError):
        Decision.model_validate(
            {
                "action": "wait",
                "parameters": {},
                "reason": "Not enough certainty",
                "confidence": 140,
            }
        )
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_response_models.py -v`
Expected: FAIL because `Decision` is undefined or under-validated.

**Step 3: Write minimal implementation**

```python
from typing import Literal
from pydantic import BaseModel, Field


class ActionParameters(BaseModel):
    x_percent: float | None = None
    y_percent: float | None = None
    text: str | None = None
    keys: list[str] = Field(default_factory=list)


class Decision(BaseModel):
    action: Literal["wait", "click", "double_click", "drag", "type_text", "press_hotkey"]
    parameters: ActionParameters = Field(default_factory=ActionParameters)
    reason: str
    confidence: int = Field(ge=0, le=100)
```

Add any action-specific validators needed to reject incomplete payloads.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_response_models.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add llm/response_models.py tests/test_response_models.py
git commit -m "feat: add structured LLM decision schema"
```

### Task 4: Implement prompt building and provider-independent request shaping

**Files:**
- Modify: `llm/prompts.py`
- Modify: `llm/client.py`
- Test: `tests/test_prompts.py`
- Test: `tests/test_llm_client.py`

**Step 1: Write the failing test**

```python
from llm.prompts import build_messages


def test_build_messages_includes_named_regions_and_operator_goal():
    messages = build_messages(
        operator_goal="Press confirm when the dialog is ready",
        named_regions={"dialog_area": [0.5, 0.5, 1.0, 1.0]},
    )

    joined = "\n".join(part["content"] for part in messages)
    assert "dialog_area" in joined
    assert "Press confirm" in joined
```

```python
from llm.client import normalize_provider_name


def test_normalize_provider_name_supports_known_aliases():
    assert normalize_provider_name("gpt-4o") == "openai"
    assert normalize_provider_name("claude-3-5-sonnet") == "anthropic"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_prompts.py tests/test_llm_client.py -v`
Expected: FAIL because the helpers do not exist yet.

**Step 3: Write minimal implementation**

```python
def build_messages(operator_goal: str, named_regions: dict[str, list[float]] | None = None) -> list[dict[str, str]]:
    regions = named_regions or {}
    return [
        {"role": "system", "content": "You are a desktop vision automation analyst."},
        {
            "role": "user",
            "content": f"Goal: {operator_goal}\nRegions: {regions}",
        },
    ]


def normalize_provider_name(name: str) -> str:
    if "gpt" in name:
        return "openai"
    if "claude" in name:
        return "anthropic"
    return "gemini"
```

Then extend `llm/client.py` to hold a provider-agnostic `analyze_screen()` interface and injectable adapter methods.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_prompts.py tests/test_llm_client.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add llm/prompts.py llm/client.py tests/test_prompts.py tests/test_llm_client.py
git commit -m "feat: add prompt builder and unified LLM client surface"
```

### Task 5: Build image preprocessing and coordinate helpers

**Files:**
- Modify: `utils/helpers.py`
- Test: `tests/test_helpers.py`

**Step 1: Write the failing test**

```python
from utils.helpers import percent_to_absolute


def test_percent_to_absolute_converts_window_relative_coordinates():
    point = percent_to_absolute(
        bounds={"left": 100, "top": 200, "width": 400, "height": 300},
        x_percent=25.0,
        y_percent=50.0,
    )

    assert point == (200, 350)
```

Add a second test for image encoding that verifies a small PIL image becomes base64 text.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_helpers.py -v`
Expected: FAIL because helper functions do not exist.

**Step 3: Write minimal implementation**

```python
import base64
from io import BytesIO


def percent_to_absolute(bounds: dict[str, int], x_percent: float, y_percent: float) -> tuple[int, int]:
    x = bounds["left"] + round(bounds["width"] * (x_percent / 100.0))
    y = bounds["top"] + round(bounds["height"] * (y_percent / 100.0))
    return x, y


def encode_image_to_base64(image) -> str:
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    return base64.b64encode(buffer.getvalue()).decode("ascii")
```

Add bounds validation helpers in the same module.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_helpers.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add utils/helpers.py tests/test_helpers.py
git commit -m "feat: add image and coordinate utility helpers"
```

### Task 6: Implement target window discovery and client-area capture

**Files:**
- Modify: `capture/window_capture.py`
- Test: `tests/test_window_capture.py`

**Step 1: Write the failing test**

```python
from capture.window_capture import compute_client_capture_region


def test_compute_client_capture_region_returns_mss_monitor_shape():
    region = compute_client_capture_region(
        window_rect={"left": 10, "top": 20, "right": 410, "bottom": 320},
        client_rect={"left": 18, "top": 48, "right": 402, "bottom": 312},
    )

    assert region == {"left": 18, "top": 48, "width": 384, "height": 264}
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_window_capture.py::test_compute_client_capture_region_returns_mss_monitor_shape -v`
Expected: FAIL because the pure helper is missing.

**Step 3: Write minimal implementation**

```python
def compute_client_capture_region(window_rect: dict[str, int], client_rect: dict[str, int]) -> dict[str, int]:
    return {
        "left": client_rect["left"],
        "top": client_rect["top"],
        "width": client_rect["right"] - client_rect["left"],
        "height": client_rect["bottom"] - client_rect["top"],
    }
```

Then add thin wrappers around `pygetwindow`, `win32gui`, and `mss` to resolve the real target window and capture a `PIL.Image` plus metadata object.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_window_capture.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add capture/window_capture.py tests/test_window_capture.py
git commit -m "feat: add client-area window capture"
```

### Task 7: Add the humanized interaction layer and executor

**Files:**
- Modify: `interaction/mouse_dynamics.py`
- Modify: `interaction/timing_engine.py`
- Modify: `interaction/variance_injector.py`
- Modify: `actions/executor.py`
- Test: `tests/test_executor.py`
- Test: `tests/test_timing_engine.py`

**Step 1: Write the failing test**

```python
from actions.executor import translate_click


def test_translate_click_returns_absolute_coordinates_for_decision():
    coords = translate_click(
        bounds={"left": 100, "top": 200, "width": 500, "height": 400},
        parameters={"x_percent": 10.0, "y_percent": 25.0},
    )

    assert coords == (150, 300)
```

```python
from interaction.timing_engine import bounded_delay


def test_bounded_delay_stays_within_configured_limits():
    delay = bounded_delay(base_seconds=0.7, spread_seconds=0.2, minimum=0.3, maximum=1.2)
    assert 0.3 <= delay <= 1.2
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_executor.py tests/test_timing_engine.py -v`
Expected: FAIL because translation and delay helpers do not exist.

**Step 3: Write minimal implementation**

```python
from utils.helpers import percent_to_absolute


def translate_click(bounds: dict[str, int], parameters: dict[str, float]) -> tuple[int, int]:
    return percent_to_absolute(bounds, parameters["x_percent"], parameters["y_percent"])
```

```python
import random


def bounded_delay(base_seconds: float, spread_seconds: float, minimum: float, maximum: float) -> float:
    sampled = random.gauss(base_seconds, spread_seconds)
    return max(minimum, min(maximum, sampled))
```

Then add executor methods that call `pydirectinput` only after bounds and mode checks pass.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_executor.py tests/test_timing_engine.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add interaction/mouse_dynamics.py interaction/timing_engine.py interaction/variance_injector.py actions/executor.py tests/test_executor.py tests/test_timing_engine.py
git commit -m "feat: add interaction layer and action executor"
```

### Task 8: Implement the main agent loop with dry-run and debug artifacts

**Files:**
- Modify: `agent.py`
- Modify: `utils/helpers.py`
- Test: `tests/test_agent.py`

**Step 1: Write the failing test**

```python
from llm.response_models import Decision
from agent import run_cycle


class StubCapture:
    def capture(self):
        return "image", {"left": 0, "top": 0, "width": 100, "height": 100}


class StubLlm:
    def analyze_screen(self, *_args, **_kwargs):
        return Decision.model_validate(
            {
                "action": "click",
                "parameters": {"x_percent": 50.0, "y_percent": 50.0},
                "reason": "Center target",
                "confidence": 95,
            }
        )


class StubExecutor:
    def __init__(self):
        self.called = False

    def execute(self, *_args, **_kwargs):
        self.called = True


def test_run_cycle_executes_when_confidence_is_high_enough():
    executor = StubExecutor()
    run_cycle(StubCapture(), StubLlm(), executor, confidence_threshold=80, dry_run=False)
    assert executor.called is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_agent.py::test_run_cycle_executes_when_confidence_is_high_enough -v`
Expected: FAIL because `run_cycle` is missing or not injectable.

**Step 3: Write minimal implementation**

```python
def run_cycle(capture_service, llm_client, executor, confidence_threshold: int, dry_run: bool) -> None:
    image, metadata = capture_service.capture()
    decision = llm_client.analyze_screen(image=image, metadata=metadata)
    if decision.confidence < confidence_threshold:
        return
    if dry_run:
        return
    executor.execute(decision=decision, metadata=metadata)
```

Then add artifact writing helpers and a higher-level `DesktopAutomationAgent` class for repeated cycles and runtime state.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_agent.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add agent.py utils/helpers.py tests/test_agent.py
git commit -m "feat: add agent cycle orchestration"
```

### Task 9: Add the native desktop panel and UI state mapping

**Files:**
- Modify: `agent.py`
- Modify: `settings.py`
- Modify: `utils/helpers.py`
- Create: `ui/main_window.py`
- Create: `ui/view_models.py`
- Test: `tests/test_view_models.py`

**Step 1: Write the failing test**

```python
from ui.view_models import build_status_view_model


def test_build_status_view_model_maps_runtime_state_for_ui():
    view_model = build_status_view_model(
        agent_state="running",
        last_action="click",
        confidence=91,
        dry_run=True,
    )

    assert view_model.status_label == "Running"
    assert view_model.last_action == "click"
    assert view_model.confidence == 91
    assert view_model.mode_label == "Dry Run"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_view_models.py::test_build_status_view_model_maps_runtime_state_for_ui -v`
Expected: FAIL because the UI mapping helpers do not exist.

**Step 3: Write minimal implementation**

```python
from pydantic import BaseModel


class StatusViewModel(BaseModel):
    status_label: str
    last_action: str | None = None
    confidence: int | None = None
    mode_label: str


def build_status_view_model(agent_state: str, last_action: str | None, confidence: int | None, dry_run: bool) -> StatusViewModel:
    return StatusViewModel(
        status_label=agent_state.capitalize(),
        last_action=last_action,
        confidence=confidence,
        mode_label="Dry Run" if dry_run else "Live",
    )
```

Create a small PySide6 `MainWindow` with start, pause, stop buttons, provider and window selectors, a screenshot preview placeholder, and a log panel wired to the view-model layer.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_view_models.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add agent.py settings.py utils/helpers.py ui/main_window.py ui/view_models.py tests/test_view_models.py
git commit -m "feat: add native control panel"
```

### Task 10: Wire the CLI, hotkeys, and startup composition

**Files:**
- Modify: `main.py`
- Modify: `settings.py`
- Test: `tests/test_main.py`

**Step 1: Write the failing test**

```python
from typer.testing import CliRunner

from main import app


def test_cli_accepts_provider_override_and_dry_run_flag():
    result = CliRunner().invoke(app, ["--provider", "gemini", "--dry-run"])
    assert result.exit_code == 0
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_main.py::test_cli_accepts_provider_override_and_dry_run_flag -v`
Expected: FAIL because the Typer app or options are missing.

**Step 3: Write minimal implementation**

```python
import typer


app = typer.Typer()


@app.callback()
def main(provider: str = "gemini", dry_run: bool = True) -> None:
    _ = (provider, dry_run)
```

Extend startup composition to load config, apply CLI overrides, assemble the capture/LLM/executor services, and register F8, F9, and F10 handlers.

The Typer entrypoint should launch the native desktop panel by default, not a headless session.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_main.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add main.py settings.py tests/test_main.py
git commit -m "feat: add CLI startup and hotkey wiring"
```

### Task 11: Add manual verification notes and MVP hardening checks

**Files:**
- Create: `README.md`
- Modify: `config.yaml`
- Test: `tests/test_config_examples.py`

**Step 1: Write the failing test**

```python
from pathlib import Path


def test_config_example_contains_hotkeys_and_provider_section():
    content = Path("config.yaml").read_text(encoding="utf-8")
    assert "provider:" in content
    assert "hotkeys:" in content
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_config_examples.py -v`
Expected: FAIL if the config example is incomplete.

**Step 3: Write minimal implementation**

```yaml
provider:
  name: gemini
hotkeys:
  start: F8
  pause: F9
  stop: F10
```

Create `README.md` with install steps, dry-run usage, required permissions, native panel screenshots or descriptions, and a manual smoke-test checklist for a safe target application.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_config_examples.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add README.md config.yaml tests/test_config_examples.py
git commit -m "docs: add setup and smoke-test guide"
```

### Task 12: Run the full test suite and perform a safe manual smoke test

**Files:**
- Modify: `README.md`

**Step 1: Write the failing test**

There is no new unit test for this task. Instead, add a short checklist entry in `README.md` describing expected smoke-test behavior.

```markdown
- Start in dry-run mode and confirm no mouse or keyboard events are injected.
- Confirm the native control panel updates status, last action, and confidence after each cycle.
- Confirm debug screenshots and parsed decisions are saved locally.
- Switch to live mode only on a non-critical application window.
```

**Step 2: Run test to verify it fails**

Run: `pytest -v`
Expected: FAIL until all previous tasks are complete.

**Step 3: Write minimal implementation**

Finalize any missing glue code found by the test suite, then add the smoke-test checklist to `README.md`.

**Step 4: Run test to verify it passes**

Run: `pytest -v`
Expected: PASS.

Manual run:

```bash
python main.py --provider gemini --dry-run --window-title-regex "Calculator"
```

Expected: the app starts, resolves the target window, captures screenshots, logs decisions, and executes no real inputs.

Expected UI behavior: the native panel opens locally, reflects runtime state changes, and shows the latest capture preview and decision summary.

**Step 5: Commit**

```bash
git add .
git commit -m "feat: deliver local LLM vision automation MVP"
```

## Notes For The Implementer

- Prefer dry-run mode as the default until manual validation is complete.
- Keep provider adapters thin and injectable so unit tests never need real API calls.
- Do not let `actions/executor.py` call raw coordinate math directly; route through shared helpers.
- Keep `vision/element_detector.py` intentionally small for MVP.
- Treat debug artifacts as first-class output because prompt tuning will be frequent.
- If `instructor` integration becomes awkward across providers, keep the external interface stable and use provider-specific parsing behind `llm/client.py`.
- Keep the UI thin: it should observe and control the agent, not contain capture or execution logic.
- Design the runtime state publisher so a later local web dashboard can reuse the same data contract for remote access.

Plan complete and saved to `docs/plans/2026-03-06-local-llm-vision-agent.md`. Two execution options:

1. Subagent-Driven (this session) - I dispatch fresh subagent per task, review between tasks, fast iteration
2. Parallel Session (separate) - Open new session with executing-plans, batch execution with checkpoints

Which approach?
