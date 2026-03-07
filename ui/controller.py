from dataclasses import dataclass, field
from collections.abc import Callable
import threading
from typing import Any, cast

from PySide6.QtCore import QObject, QTimer, Signal

from ui.view_models import StatusViewModel
from ui.view_models import build_status_view_model


@dataclass
class RuntimeState:
    agent_state: str = "idle"
    last_action: str | None = None
    confidence: int | None = None
    reason_text: str | None = None
    dry_run: bool = True
    available_windows: list[str] = field(default_factory=list)
    available_window_items: list[dict[str, Any]] = field(default_factory=list)
    selected_window: str | None = None
    selected_hwnd: int | None = None
    provider: str = "gemini"
    preview_image: object | None = None
    error_text: str | None = None
    log_lines: list[str] = field(default_factory=list)
    result_text: str | None = None
    inferred_goal: str | None = None
    completion_confidence_trend: list[int] = field(default_factory=list)
    completion_reason_history: list[str] = field(default_factory=list)


class QtScheduler:
    def __init__(self) -> None:
        self.timer = QTimer()
        self._callback = None
        self.timer.timeout.connect(self._on_timeout)

    def _on_timeout(self) -> None:
        if self._callback is not None:
            self._callback()

    def start(self, interval_ms, callback) -> None:
        self._callback = callback
        self.timer.start(interval_ms)

    def stop(self) -> None:
        self.timer.stop()


class BackgroundRunner(QObject):
    result_ready = Signal(object)
    error_ready = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.busy = False
        self._on_success: Callable[[object], None] | None = None
        self._on_error: Callable[[str], None] | None = None
        self.result_ready.connect(self._handle_result)
        self.error_ready.connect(self._handle_error)

    def submit(
        self,
        task: Callable[[], object],
        on_success: Callable[[object], None],
        on_error: Callable[[str], None],
    ) -> bool:
        if self.busy:
            return False
        self.busy = True
        self._on_success = on_success
        self._on_error = on_error
        threading.Thread(target=self._execute, args=(task,), daemon=True).start()
        return True

    def _execute(self, task: Callable[[], object]) -> None:
        try:
            result = task()
        except Exception as exc:
            self.error_ready.emit(str(exc))
            return
        self.result_ready.emit(result)

    def _handle_result(self, result: object) -> None:
        self.busy = False
        callback = self._on_success
        self._on_success = None
        self._on_error = None
        if callback is not None:
            callback(result)

    def _handle_error(self, message: str) -> None:
        self.busy = False
        callback = self._on_error
        self._on_success = None
        self._on_error = None
        if callback is not None:
            callback(message)


class RuntimeController:
    def __init__(
        self,
        dry_run: bool = True,
        agent: Any = None,
        scheduler: Any = None,
        runner: Any = None,
        interval_ms: int = 1000,
    ) -> None:
        self.state = RuntimeState(dry_run=dry_run)
        self._listeners: list[Callable[[StatusViewModel], None]] = []
        self.agent = agent
        self.scheduler = scheduler or QtScheduler()
        self.runner = runner or BackgroundRunner()
        self.interval_ms = interval_ms

    def subscribe(self, listener) -> None:
        self._listeners.append(listener)
        listener(self.current_view_model())

    def current_view_model(self) -> StatusViewModel:
        return build_status_view_model(
            agent_state=self.state.agent_state,
            last_action=self.state.last_action,
            confidence=self.state.confidence,
            dry_run=self.state.dry_run,
            reason_text=self.state.reason_text,
            preview_image=self.state.preview_image,
            error_text=self.state.error_text,
            log_lines=self.state.log_lines,
            result_text=self.state.result_text,
            selected_hwnd=self.state.selected_hwnd,
            inferred_goal=self.state.inferred_goal,
            completion_confidence_trend=self.state.completion_confidence_trend,
            completion_reason_history=self.state.completion_reason_history,
        )

    def _publish(self) -> None:
        view_model = self.current_view_model()
        for listener in self._listeners:
            listener(view_model)

    def start(self) -> None:
        if self.agent is not None and hasattr(self.agent, "reset_cycle_state"):
            self.agent.reset_cycle_state()
        self.state.completion_confidence_trend = []
        self.state.completion_reason_history = []
        self.state.inferred_goal = self._current_operator_goal()
        self.state.agent_state = "running"
        self._publish()
        self.scheduler.start(self.interval_ms, self.request_cycle)
        self.request_cycle()

    def pause(self) -> None:
        self.scheduler.stop()
        self.state.agent_state = "paused"
        self._publish()

    def stop(self) -> None:
        self.scheduler.stop()
        self.state.agent_state = "stopped"
        self._publish()

    def record_decision(
        self,
        last_action: str,
        confidence: int,
        reason_text: str | None = None,
        preview_image: object | None = None,
        result_text: str | None = None,
    ) -> None:
        self.state.last_action = last_action
        self.state.confidence = confidence
        self.state.reason_text = reason_text
        self.state.preview_image = preview_image
        self.state.error_text = None
        self.state.result_text = result_text
        line = f"{last_action} ({confidence}%): {reason_text or 'No reason provided'}"
        if result_text:
            line = f"{line} -> {result_text}"
        self.state.log_lines.append(line)
        self._publish()

    def set_available_windows(self, window_titles: list[str]) -> None:
        self.state.available_windows = window_titles
        self.state.available_window_items = [{"title": title, "hwnd": None} for title in window_titles]
        if window_titles and self.state.selected_window is None:
            self.state.selected_window = window_titles[0]
            self._refresh_selected_hwnd()
        self._publish()

    def set_selected_window(self, window_title: str, hwnd: int | None = None) -> None:
        self.state.selected_window = window_title or None
        if hwnd is not None:
            self.state.selected_hwnd = hwnd
        else:
            self._refresh_selected_hwnd()
        self._publish()

    def set_provider(self, provider: str) -> None:
        self.state.provider = provider
        if self.agent is not None and hasattr(self.agent, "settings"):
            self.agent.settings.provider.name = provider

    def set_model(self, model: str) -> None:
        self.state.error_text = None
        if self.agent is not None and hasattr(self.agent, "settings"):
            self.agent.settings.provider.model = model

    def set_openai_api_key(self, api_key: str) -> None:
        if self.agent is not None and hasattr(self.agent, "settings"):
            self.agent.settings.provider.openai_api_key = api_key or None

    def set_gemini_api_key(self, api_key: str) -> None:
        if self.agent is not None and hasattr(self.agent, "settings"):
            self.agent.settings.provider.gemini_api_key = api_key or None

    def set_confidence_threshold(self, threshold: int) -> None:
        if self.agent is not None and hasattr(self.agent, "settings"):
            self.agent.settings.runtime.confidence_threshold = threshold

    def set_max_retries(self, retries: int) -> None:
        if self.agent is not None and hasattr(self.agent, "settings"):
            self.agent.settings.runtime.max_retries = retries

    def set_retry_backoff_seconds(self, seconds: float) -> None:
        if self.agent is not None and hasattr(self.agent, "settings"):
            self.agent.settings.runtime.retry_backoff_seconds = seconds

    def set_llm_max_width(self, width: int) -> None:
        if self.agent is not None and hasattr(self.agent, "settings"):
            self.agent.settings.runtime.llm_max_width = width

    def set_llm_max_height(self, height: int) -> None:
        if self.agent is not None and hasattr(self.agent, "settings"):
            self.agent.settings.runtime.llm_max_height = height

    def set_llm_jpeg_quality(self, quality: int) -> None:
        if self.agent is not None and hasattr(self.agent, "settings"):
            self.agent.settings.runtime.llm_jpeg_quality = quality

    def set_cycle_interval_seconds(self, seconds: float) -> None:
        self.interval_ms = int(seconds * 1000)
        if self.agent is not None and hasattr(self.agent, "settings"):
            self.agent.settings.runtime.cycle_interval_seconds = seconds
        if self.state.agent_state == "running":
            self.scheduler.stop()
            self.scheduler.start(self.interval_ms, self.request_cycle)

    def set_operator_goal(self, goal: str) -> None:
        if self.agent is not None and hasattr(self.agent, "settings"):
            self.agent.settings.prompt.operator_goal = goal

    def set_dry_run(self, dry_run: bool) -> None:
        self.state.dry_run = dry_run
        if self.agent is not None and hasattr(self.agent, "settings"):
            self.agent.settings.runtime.dry_run = dry_run
        self._publish()

    def _build_cycle_task(self) -> Callable[[], object]:
        agent = cast(Any, self.agent)
        return lambda: agent.run_once(
            provider=self.state.provider,
            title_regex=self.state.selected_window,
            preferred_hwnd=self.state.selected_hwnd,
        )

    def request_cycle(self) -> None:
        self.refresh_available_windows()
        if self.agent is None or not self.state.selected_window:
            return
        self.runner.submit(self._build_cycle_task(), self._handle_cycle_result, self._handle_cycle_error)

    def _handle_cycle_result(self, result: object) -> None:
        metadata = getattr(result, "metadata", {})
        if isinstance(metadata, dict):
            self.state.selected_hwnd = metadata.get("hwnd", self.state.selected_hwnd)
        execution_result = getattr(result, "execution_result", None)
        self._update_goal_progress(execution_result)
        if isinstance(execution_result, dict) and execution_result.get("goal_complete"):
            self.scheduler.stop()
            self.state.agent_state = "completed"
        self.record_decision(
            getattr(result, "action"),
            getattr(result, "confidence"),
            getattr(result, "reason"),
            getattr(result, "image", None),
            self._format_result_text(execution_result),
        )

    def _update_goal_progress(self, execution_result: object | None) -> None:
        if not isinstance(execution_result, dict):
            return

        inferred_goal = execution_result.get("inferred_goal")
        if isinstance(inferred_goal, str) and inferred_goal.strip():
            self.state.inferred_goal = inferred_goal.strip()

        completion_confidence = execution_result.get("goal_completion_confidence")
        if isinstance(completion_confidence, int):
            bounded = max(0, min(100, completion_confidence))
            self.state.completion_confidence_trend.append(bounded)
            self.state.completion_confidence_trend = self.state.completion_confidence_trend[-20:]

        if execution_result.get("goal_complete"):
            reason = execution_result.get("goal_completion_reason")
            if isinstance(reason, str) and reason.strip():
                text = reason.strip()
                if not self.state.completion_reason_history or self.state.completion_reason_history[-1] != text:
                    self.state.completion_reason_history.append(text)
                    self.state.completion_reason_history = self.state.completion_reason_history[-20:]

    def _current_operator_goal(self) -> str | None:
        if self.agent is None or not hasattr(self.agent, "settings"):
            return None
        prompt = getattr(getattr(self.agent, "settings"), "prompt", None)
        goal = getattr(prompt, "operator_goal", None)
        if isinstance(goal, str) and goal.strip():
            return goal.strip()
        return None

    def _handle_cycle_error(self, message: str) -> None:
        self.state.error_text = message
        self.state.log_lines.append(f"ERROR: {message}")
        self._publish()

    def _format_result_text(self, execution_result: object | None) -> str | None:
        if not isinstance(execution_result, dict):
            return None
        action = execution_result.get("action")
        if execution_result.get("goal_complete"):
            reason = execution_result.get("goal_completion_reason")
            if isinstance(reason, str) and reason.strip():
                return f"goal complete: {reason}"
            return "goal complete"
        if "coordinates" in execution_result:
            text = f"{action} at {execution_result['coordinates']}"
            mode = execution_result.get("coordinate_mode")
            raw = execution_result.get("raw_coordinates")
            if mode:
                text = f"{text} [{mode}]"
            if raw is not None:
                text = f"{text} raw={raw}"
            return text
        if "start" in execution_result and "end" in execution_result:
            text = f"{action} from {execution_result['start']} to {execution_result['end']}"
            start_mode = execution_result.get("start_mode")
            end_mode = execution_result.get("end_mode")
            if start_mode or end_mode:
                text = f"{text} [{start_mode or '?'}->{end_mode or '?'}]"
            start_raw = execution_result.get("start_raw")
            end_raw = execution_result.get("end_raw")
            if start_raw is not None and end_raw is not None:
                text = f"{text} raw={start_raw}->{end_raw}"
            return text
        blocked_reason = execution_result.get("blocked_reason")
        if action is not None and blocked_reason:
            return f"{action} blocked: {blocked_reason}"
        executed = execution_result.get("executed")
        if action is not None:
            return f"{action} ({'executed' if executed else 'not executed'})"
        return None

    def _refresh_selected_hwnd(self) -> None:
        if self.agent is None or not hasattr(self.agent, "capture_service") or not self.state.selected_window:
            self.state.selected_hwnd = None
            return
        capture_service = getattr(self.agent, "capture_service")
        if not hasattr(capture_service, "find_window"):
            self.state.selected_hwnd = None
            return
        try:
            window = capture_service.find_window(self.state.selected_window)
            self.state.selected_hwnd = getattr(window, "_hWnd", None)
        except Exception:
            self.state.selected_hwnd = None

    def refresh_available_windows(self) -> list[dict[str, Any]]:
        if self.agent is None or not hasattr(self.agent, "capture_service"):
            return []

        capture_service = getattr(self.agent, "capture_service")
        window_items: list[dict[str, Any]] = []
        try:
            if hasattr(capture_service, "list_window_infos"):
                window_items = capture_service.list_window_infos()
            elif hasattr(capture_service, "list_windows"):
                window_items = [{"title": title, "hwnd": None} for title in capture_service.list_windows()]
        except Exception:
            return []

        self.state.available_window_items = window_items
        self.state.available_windows = [item["title"] for item in window_items]

        if self.state.selected_hwnd is not None:
            for item in window_items:
                if item.get("hwnd") == self.state.selected_hwnd:
                    self.state.selected_window = item["title"]
                    self._publish()
                    return window_items

        if self.state.selected_window:
            for item in window_items:
                if item["title"] == self.state.selected_window:
                    self.state.selected_hwnd = item.get("hwnd")
                    self._publish()
                    return window_items

        if window_items:
            self.state.selected_window = window_items[0]["title"]
            self.state.selected_hwnd = window_items[0].get("hwnd")
        else:
            self.state.selected_window = None
            self.state.selected_hwnd = None

        self._publish()
        return window_items
