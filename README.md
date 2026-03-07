# Desktop Automation Agent

Local Windows desktop automation agent with a native control panel, screenshot-based LLM decisions, and safe dry-run support.

## Current MVP Status

This repository currently includes the MVP scaffold, typed settings, decision schema, shared helpers, a basic agent loop, and a native PySide6 control panel shell.

## Requirements

- Windows 10 or 11
- Python 3.11+
- A target desktop application window
- An API key for a supported provider (`gemini` or `openai`)

## Install

```bash
python -m pip install -r requirements.txt
```

## Configuration

Edit `config.yaml` to set:

- target window title regex
- provider name and model
- dry-run behavior
- confidence threshold
- LLM image size and JPEG quality (controls API image cost)
- debug screenshot directory
- local hotkeys

## Run

```bash
python main.py --provider gemini --dry-run --window-title-regex "Calculator"
```

## Native Panel

The MVP launches a native desktop panel intended to provide:

- start, pause, and stop controls
- target window selection
- provider selection
- runtime status display
- latest capture preview
- recent logs and decision summary

## Safety Notes

- Prefer dry-run mode until the capture and execution paths are fully validated.
- Only test live input injection against a non-critical application.
- Keep emergency stop behavior available through the configured hotkeys.

## Smoke-Test Checklist

- Start in dry-run mode and confirm no mouse or keyboard events are injected.
- Confirm the native control panel updates status, last action, and confidence after each cycle.
- Confirm debug screenshots and parsed decisions are saved locally.
- Switch to live mode only on a non-critical application window.
