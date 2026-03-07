# Local LLM Vision Desktop Automation Agent Design

## Goal

Build a Windows-only Python MVP with a native desktop control panel that watches a single target application window, sends normalized screenshots to a selected vision-capable LLM, receives a strictly structured decision, and safely executes mouse and keyboard actions against that window.

## Scope

- MVP-first, not the full long-term framework
- Single target window at a time
- Moderately dynamic desktop UI
- Native desktop panel included in MVP
- LLM-first decision making with lightweight local validation
- Local debug artifacts and dry-run support
- Extensible seams for later multi-window, OpenCV assist, Ollama fallback, and a remote web dashboard

## Non-Goals For MVP

- Full multi-window orchestration
- Heavy classical-vision control logic
- Production-grade anti-detection behavior
- Zero-cost local vision inference
- Remote dashboard access in MVP
- Complex planner/state-machine definitions for every application state

## Recommended Approach

Use an LLM-first architecture with small local helpers around it.

The LLM remains the primary visual analyst because the target UI is moderately dynamic and likely to contain dialogs, overlays, or layout shifts that make pure template matching brittle. Local code should stabilize the workflow by validating coordinate bounds, exposing optional named capture regions, normalizing screenshots, and enforcing safety rules before any action is executed.

This gives the MVP the best trade-off between flexibility, implementation speed, and future extensibility.

## UI Direction

The MVP should include a small native desktop panel rather than only a CLI. This panel should act as the local operator console for the agent.

Recommended MVP UI features:

- Start, pause, and stop controls
- Target window selection and refresh
- Provider selection
- Dry-run toggle
- Current status and last action summary
- Latest screenshot preview
- Confidence and reasoning preview
- Scrollable local logs

This should remain a local control surface, not a second automation engine. The automation loop still lives in the service layer, and the UI only configures, starts, observes, and stops it.

The later remote-access web dashboard should be treated as a separate presentation layer that connects to the same agent services through a clean application state boundary. That keeps the MVP native and simple while preserving a path to remote observability and control in a future version.

## Architecture

The core system is split into three stages:

1. Observe: locate the configured window, capture its client area, normalize the image, and derive metadata such as window bounds and named regions.
2. Decide: call the selected LLM provider with a strict response schema and application-specific prompt template.
3. Act: validate the returned action and execute it through a humanized interaction layer.

The main loop should remain small and orchestrational. Capture, LLM, and execution logic should live behind narrow interfaces so the project can later add fallback providers, optional OpenCV helpers, or local model backends without rewriting the loop.

## Project Layout

The initial repository layout should follow the user's proposed structure with a few MVP expectations:

- `main.py`: CLI entrypoint, config loading, hotkey registration
- `agent.py`: main runtime state machine and loop
- `config.yaml`: operator-controlled settings and prompt customization
- `ui/main_window.py`: native desktop control panel
- `ui/view_models.py`: UI-safe state mapping for agent status and artifacts
- `capture/window_capture.py`: window discovery, focus management, client-area screenshots
- `llm/client.py`: unified provider wrapper
- `llm/prompts.py`: prompt assembly from config and runtime metadata
- `llm/response_models.py`: Pydantic schemas for structured decisions
- `actions/executor.py`: convert validated decisions into concrete interactions
- `interaction/mouse_dynamics.py`: movement path generation
- `interaction/timing_engine.py`: variable delays
- `interaction/variance_injector.py`: small, bounded randomness
- `vision/element_detector.py`: optional MVP helper seam, not primary logic
- `utils/helpers.py`: image encoding, coordinate transforms, artifact naming
- `tests/`: unit tests around seams and pure logic

## Components And Responsibilities

### `main.py`

- Starts the native desktop app and parses optional CLI overrides
- Loads settings from `config.yaml`
- Creates service objects
- Registers global hotkeys for start, pause, and emergency stop
- Hands control to the UI shell and shared agent runtime

### `ui/main_window.py`

- Renders the native operator panel
- Exposes controls for start, pause, stop, dry-run, provider, and target window selection
- Displays the latest screenshot preview, confidence, reason, and log output
- Subscribes to agent state changes without owning automation logic

### `ui/view_models.py`

- Translates raw runtime state into UI-friendly models
- Keeps widget code simple and avoids passing service internals directly into the window layer

### `agent.py`

- Owns runtime states: `idle`, `running`, `paused`, `stopped`
- Runs the cycle timer
- Requests a capture
- Calls the LLM analyzer
- Validates threshold and safety rules
- Dispatches actions or waits
- Persists debug artifacts when enabled

### `capture/window_capture.py`

- Finds the target window by title regex or class hints
- Resolves client-area bounds instead of full window bounds
- Detects monitor placement for multi-monitor correctness
- Captures screenshots with `mss`
- Returns image bytes plus metadata needed by later stages

### `llm/client.py`

- Exposes one `analyze_screen()` entrypoint
- Supports provider adapters for Gemini, OpenAI, and Anthropic
- Builds a provider-agnostic request envelope
- Parses the model output into the response schema
- Leaves room for future fallback chains and provider-specific tuning

### `llm/prompts.py`

- Builds the system prompt and user prompt from config
- Includes task instructions, named region hints, and prior cycle context when safe
- Keeps prompts deterministic and easy to inspect in debug mode

### `llm/response_models.py`

- Defines action enums and parameter models
- Keeps schema narrow so automation remains controllable
- Includes `action`, `parameters`, `reason`, and `confidence`

### `actions/executor.py`

- Translates relative percentages into absolute screen coordinates
- Rejects out-of-bounds or malformed instructions
- Routes all actions through the interaction layer
- Supports click, double-click, drag, type text, press key, and wait

### `interaction/*`

- Encapsulates humanization logic so action execution stays deterministic at the interface level
- Provides cursor path generation, timing variance, and small bounded coordinate offsets
- Must allow strict mode or dry-run mode for safe debugging

### `vision/element_detector.py`

- Exists as an extension seam only
- MVP usage should be limited to lightweight helpers such as region extraction or future button verification hooks
- Should not become a second decision engine in the first milestone

## Data Flow

1. Load config and CLI overrides
2. Start the native control panel and bind it to shared runtime state
3. Resolve target window
4. Capture client-area screenshot and metadata
5. Resize/compress image and encode for provider transport
6. Build prompt with screen context and task instructions
7. Request structured decision from the selected LLM
8. Validate schema, confidence, and coordinate safety
9. Execute action or record a no-op/wait
10. Save artifacts, publish the latest state to the UI, and sleep until the next cycle

## Decision Schema

The MVP should use a narrow structured response format similar to:

```json
{
  "action": "click",
  "parameters": {
    "x_percent": 72.5,
    "y_percent": 85.3,
    "text": null,
    "keys": []
  },
  "reason": "Confirm button is visible in the lower-right dialog area.",
  "confidence": 94
}
```

Recommended action set:

- `wait`
- `click`
- `double_click`
- `drag`
- `type_text`
- `press_hotkey`

Each action should use window-relative coordinates where relevant so resizing and monitor changes do not break the execution path.

## Safety Model

The MVP should default to conservative execution.

- Only act against the configured target window
- Re-resolve window bounds before action execution if geometry has changed
- Reject coordinates outside the client area
- Require a configurable confidence threshold
- Support dry-run mode where actions are logged but never executed
- Support an immediate emergency stop that cancels input injection and the main loop
- Keep remote control out of scope for MVP so all control remains local to the Windows machine

If the target window disappears, loses focus unexpectedly, or moves in a way that invalidates coordinates, the agent should pause or recover rather than issuing blind input.

## Error Handling

Different failure classes should recover differently:

- Capture failures: short retry, then pause if repeated
- Provider failures: retry with backoff, later extensible to fallback provider chain
- Parse failures: log raw response and skip the action
- Execution failures: stop the current action, refresh window metadata, and pause if the target is no longer safe to control

## Debugging And Observability

Debug mode should save per-cycle artifacts locally:

- Processed screenshot
- Capture metadata
- Prompt payload summary
- Raw provider response
- Parsed decision
- Final translated coordinates and execution outcome

This makes prompt tuning and failure analysis possible without adding remote dependencies.

## Testing Strategy

The MVP should prioritize unit tests around pure logic and interfaces.

Primary automated targets:

- Config parsing and defaults
- UI view-model mapping and state transitions
- Coordinate conversion and bounds checking
- Prompt assembly
- Response schema validation
- Loop branching behavior with mocked services
- Artifact naming and storage helpers

Manual verification should cover real-window capture, native panel controls, hotkeys, dry-run sessions, and a small number of end-to-end actions against a non-critical application.

## Future Extensions

The architecture intentionally leaves room for:

- Multi-window cycling
- OpenCV template matching for high-confidence local assists
- Ollama or local vision backends
- Local web dashboard for remote access and monitoring
- Provider fallback chains
- Application-specific state plugins
- More advanced recovery heuristics

## Delivery Notes

This design was approved interactively in-session.

I did not create a git commit for this design document because the workspace is not an initialized git repository and you did not ask for a commit.
