# Desktop Automation Agent

Windows desktop automation agent with a native PySide6 control panel, screenshot-driven LLM decisions, and a dry-run-first execution model.

## Current App State

This repository is no longer just an MVP shell. The current app can:

- launch a native desktop control panel
- enumerate visible desktop windows and pin a target window by title and `HWND`
- capture the target window client area with `PrintWindow`, with `mss` fallback
- send the current frame to Gemini or OpenAI for the next-step decision
- execute `click`, `double_click`, `drag`, `type_text`, and `press_hotkey` actions
- run in dry-run mode so decisions are visible without injecting input
- test provider connectivity from the UI
- save config changes to `config.yaml` and API keys to `.secrets.yaml`
- import and export non-secret settings profiles
- register global start, pause, and stop hotkeys
- track task completion confidence and stop automatically when the model marks the goal complete with enough confidence

## What The App Does

Each cycle looks like this:

1. The app finds the selected window.
2. It captures the visible client area.
3. It resizes and compresses the image for provider cost/performance control.
4. It asks the selected model for the safest next action in a strict JSON schema.
5. It validates the model response.
6. It either logs the result in dry-run mode or activates the target window and performs the action live.

The control panel shows:

- current runtime state
- latest screenshot preview
- last action, confidence, and reason
- pinned `HWND`
- execution result details
- inferred goal and completion trend
- recent logs and error details

## Supported Providers

Current runtime support is:

- `gemini`
- `openai`

The dependency list includes `anthropic`, but the app does not currently register an Anthropic adapter in the runtime or expose it in the UI.

## Requirements

- Windows 10 or Windows 11
- Python 3.11+
- a visible target application window
- an API key for Gemini or OpenAI

Notes:

- The app is Windows-specific. It depends on `pywin32`, `pygetwindow`, `pydirectinput`, and global hotkeys.
- Minimized windows are not supported. The capture layer attempts to restore minimized windows, but automation should be run against a normal visible window.

## Install

```powershell
python -m pip install -r requirements.txt
```

## Configuration Files

### `config.yaml`

Committed app settings live in `config.yaml`.

Current sections:

- `window`
- `runtime`
- `provider`
- `prompt`
- `debug`
- `interaction`
- `hotkeys`

Important active fields:

- `window.title_regex`
- `runtime.confidence_threshold`
- `runtime.dry_run`
- `runtime.cycle_interval_seconds`
- `runtime.llm_max_width`
- `runtime.llm_max_height`
- `runtime.llm_jpeg_quality`
- `runtime.max_retries`
- `runtime.retry_backoff_seconds`
- `provider.name`
- `provider.model`
- `prompt.operator_goal`
- `hotkeys.start`
- `hotkeys.pause`
- `hotkeys.stop`

### `.secrets.yaml`

Provider API keys are loaded from a separate `.secrets.yaml` next to `config.yaml`.

```yaml
provider:
  openai_api_key: null
  gemini_api_key: "your-key-here"
```

`config.yaml` is safe to commit. `.secrets.yaml` should stay local.

## Running The App

Start the native panel:

```powershell
python main.py
```

Useful overrides:

```powershell
python main.py --provider gemini --dry-run --window-title-regex "Calculator"
```

Available CLI options:

- `--provider`
- `--dry-run`
- `--window-title-regex`
- `--config`

There is also a Windows launcher:

```powershell
.\launch-desktop-automation-agent.bat
```

## Using The UI

### Control Tab

Use the Control tab to:

- pick the target window
- enter the task instruction / operator goal
- start, pause, or stop the runtime
- inspect the latest screenshot preview
- review action reasoning, errors, and logs

### Settings Tab

Use the Settings tab to:

- choose `gemini` or `openai`
- set the model name
- enter provider API keys
- test provider connectivity
- tune confidence, interval, retries, backoff, and image sizing
- save and reset local settings
- import and export settings profiles

Profile import/export is non-secret by design. API keys are preserved separately in `.secrets.yaml`.

## Runtime Safety

Recommended operating pattern:

1. Start in dry-run mode.
2. Confirm the selected window and screenshot preview are correct.
3. Verify the model is producing reasonable actions and reasons.
4. Switch to live mode only for non-critical apps.

Live execution behavior today:

- the app tries to bring the target window to the foreground before input injection
- clicks and drags are bounded to the captured window area
- low-confidence decisions are not executed
- repeated `wait` decisions can trigger recovery prompts
- repeated stalled actions can push the model toward a safer alternative or a hotkey-based recovery step

## Action Schema

The model is currently expected to return one of:

- `wait`
- `click`
- `double_click`
- `drag`
- `type_text`
- `press_hotkey`

Pointer coordinates use a normalized `0-1000` scale in the model response and are converted into absolute window coordinates at execution time.

## Known Limitations

- The app is Windows-only.
- The UI currently supports only Gemini and OpenAI.
- `vision/element_detector.py` is still a placeholder seam, not an active detection system.
- `debug.enabled` and `debug.screenshot_dir` exist in config, but automatic debug artifact writing is not fully wired into the runtime yet.
- `interaction.mouse_speed_multiplier` and `interaction.enable_variance` exist in config, but they are not currently plumbed through as user-tunable runtime behavior.
- The `tests/` tree is present, but the committed test files are empty placeholders right now, so `pytest` currently collects `0` tests in this repo state.

## Project Layout

```text
actions/       Input execution and window activation
capture/       Window discovery and screenshot capture
interaction/   Mouse pathing, timing, hotkeys, variance helpers
llm/           Provider adapters, prompts, response normalization
ui/            PySide6 window, controller, and view models
vision/        Future vision helper seam
agent.py       Main cycle orchestration
main.py        CLI entry point and app bootstrap
settings.py    Typed configuration models
```

## Recommended First Run

1. Put an API key in `.secrets.yaml`.
2. Launch the app with `python main.py`.
3. Pick a simple target window such as Calculator or Notepad.
4. Keep Dry Run enabled.
5. Enter a short goal.
6. Click Start/Resume and watch the preview, reasoning, and result fields.
7. Only test live mode after the dry-run output looks correct.
