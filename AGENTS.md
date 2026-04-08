# AGENTS.md
Guidance for agentic coding tools working in this repository.

## 1) Repository Purpose
- Windows desktop automation app with a native PySide6 UI.
- Captures a target window, asks an LLM for the next step, and executes actions.
- Supports `wait`, `click`, `double_click`, `drag`, `type_text`, `press_hotkey`.
- Uses dry-run-first execution and confidence gating for safety.
- Tracks goal completion and can auto-stop when the model reports completion.

## 2) Quick Context Before You Edit
- Read `README.md` first for expected runtime behavior.
- Read `main.py` for app startup and wiring.
- Read `agent.py` for cycle orchestration and recovery logic.
- Read `ui/controller.py` and `ui/main_window.py` for UI state flow.
- Read relevant tests in `tests/` before changing behavior.

## 3) Build / Lint / Test Commands
### Install dependencies
```powershell
python -m pip install -r requirements.txt
```

### Run the app
```powershell
python main.py
```

### Useful run override
```powershell
python main.py --provider gemini --dry-run --window-title-regex "Calculator"
```

### Windows launcher
```powershell
.\launch-desktop-automation-agent.bat
```

### Test suite (primary quality gate)
Run all tests:
```powershell
pytest -q
```

Run a single test file:
```powershell
pytest -q tests/test_agent.py
```

Run a single test case:
```powershell
pytest -q tests/test_agent.py::test_run_cycle_executes_when_confidence_is_high_enough
```

Run tests by keyword:
```powershell
pytest -q -k "goal_complete and runtime_controller"
```

Fast failure loop:
```powershell
pytest -q -x
```

Re-run last failures:
```powershell
pytest -q --lf
```

### Lint / format status
- No committed linter/formatter config currently (`pyproject.toml`, `ruff.toml`, etc. are absent).
- Required gate: tests pass and code follows existing project conventions.
- Optional syntax sanity check:
```powershell
python -m compileall .
```

## 4) Architecture Map
- `main.py`: CLI + desktop app bootstrap + settings I/O.
- `agent.py`: one-cycle logic, retries, recovery, completion checks.
- `capture/`: window lookup and screenshot capture.
- `llm/`: prompts, provider adapters, payload normalization, response models.
- `actions/`: input execution, coordinate resolution, window activation.
- `ui/`: controller, view-model mapping, Qt main window.
- `settings.py`: typed app configuration (Pydantic).
- `tests/`: regression contract for behavior.

## 5) Code Style Guidelines
### Imports
- Order imports as stdlib -> third-party -> local modules.
- Use explicit imports; do not use wildcard imports.
- Keep import lists stable and readable.

### Formatting
- Follow existing style (PEP-8-like, 4-space indentation).
- Prefer clarity over compact clever expressions.
- Keep conditionals explicit for safety-critical paths.

### Types
- Add type hints to function parameters and return values.
- Use `| None` for optional types.
- Use concrete generics (`dict[str, Any]`, `list[str]`, etc.).
- Keep `Any` for true dynamic boundaries (LLM payloads, runtime imports, Qt callbacks).

### Naming
- `snake_case` for functions/variables.
- `PascalCase` for classes.
- `UPPER_SNAKE_CASE` for constants.
- Tests should be named `test_<behavior>` and describe expected outcome.

### Models and payloads
- Use Pydantic models for settings and LLM response contracts.
- Enforce numeric bounds with `Field(...)` constraints.
- Keep provider payload cleanup in `llm/client.py`.
- Keep action schema aligned with executor expectations.

### Error handling
- For expected runtime blocks, return structured non-executed results:
  - Example: `{"executed": False, "blocked_reason": "..."}`
- Raise explicit exceptions for unrecoverable setup/provider failures.
- Avoid silent exception swallowing unless intentionally converting to a safe path.

### UI/controller rules
- Keep `RuntimeController` as the state coordinator.
- Update UI through view-model publication, not ad-hoc side effects.
- Keep background work off the UI thread.

### Automation safety rules
- Never bypass confidence threshold checks.
- Keep coordinate bounds checks and activation checks before live input.
- Preserve dry-run behavior.
- Prefer safe no-op/blocking behavior over speculative risky actions.

## 6) Testing Conventions
- Add/update tests for every non-trivial behavior change.
- Use lightweight stubs/fakes in tests (pattern used across `tests/`).
- Assert user-visible outcomes (result text, status labels, blocked reasons, logs).
- Run targeted tests first, then full `pytest -q`.

Qt test note:
- Use offscreen mode where needed (`QT_QPA_PLATFORM=offscreen`).

## 7) Config and Secrets
- Non-secret settings: `config.yaml`.
- Secrets: `.secrets.yaml`.
- Do not commit API keys or embed them in tests/docs.
- Keep profile import/export non-secret by design.

## 8) Cursor / Copilot Rules
Checked in this repo:
- `.cursor/rules/`: not present
- `.cursorrules`: not present
- `.github/copilot-instructions.md`: not present

If these files are added later, treat them as higher-priority local instructions.

## 9) Completion Checklist For Agents
- Relevant tests updated.
- Targeted tests pass.
- Full suite passes (`pytest -q`).
- No secret leakage in diffs.
- Behavior remains consistent with dry-run-first safety model.

## 10) Instruction Priority
- Follow explicit user instructions first.
- Then follow repository-local rules (this file and any future Cursor/Copilot rules).
- Then follow inferred project conventions.
