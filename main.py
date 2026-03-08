import os
import ctypes
from pathlib import Path
from typing import Any

import typer
import yaml
from PySide6.QtWidgets import QFileDialog
from PySide6.QtWidgets import QApplication

from actions.executor import ActionExecutor
from agent import DesktopAutomationAgent
from capture.window_capture import WindowCapture
from interaction.hotkeys import GlobalHotkeyManager
from llm.client import LlmClient
from llm.client import build_gemini_adapter
from llm.client import build_openai_adapter
from llm.client import normalize_provider_name
from settings import AppSettings
from ui.controller import RuntimeController
from ui.main_window import MainWindow


app = typer.Typer(add_completion=False)


def enable_dpi_awareness(user32: Any | None = None, shcore: Any | None = None) -> None:
    runtime_user32 = user32 or ctypes.windll.user32
    runtime_shcore = shcore
    if runtime_shcore is None:
        runtime_shcore = getattr(ctypes.windll, "shcore", None)

    try:
        if hasattr(runtime_user32, "SetProcessDpiAwarenessContext"):
            per_monitor_v2 = -4
            if runtime_user32.SetProcessDpiAwarenessContext(per_monitor_v2):
                return
    except Exception:
        pass

    try:
        if runtime_shcore is not None and hasattr(runtime_shcore, "SetProcessDpiAwareness"):
            runtime_shcore.SetProcessDpiAwareness(2)
            return
    except Exception:
        pass

    try:
        if hasattr(runtime_user32, "SetProcessDPIAware"):
            runtime_user32.SetProcessDPIAware()
    except Exception:
        return


def load_settings(config_path: Path) -> AppSettings:
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return AppSettings.model_validate(data)


def get_secrets_path(config_path: Path) -> Path:
    return config_path.with_name(".secrets.yaml")


def load_settings_with_secrets(config_path: Path) -> AppSettings:
    settings = load_settings(config_path)
    secrets_path = get_secrets_path(config_path)
    if not secrets_path.exists():
        return settings

    secret_data = yaml.safe_load(secrets_path.read_text(encoding="utf-8")) or {}
    provider_data = secret_data.get("provider", {})
    settings.provider.openai_api_key = provider_data.get("openai_api_key")
    settings.provider.gemini_api_key = provider_data.get("gemini_api_key")
    return settings


def save_settings(config_path: Path, settings: AppSettings) -> None:
    config_path.write_text(
        yaml.safe_dump(settings.model_dump(mode="python"), sort_keys=False),
        encoding="utf-8",
    )


def save_secrets(settings: AppSettings, secrets_path: Path) -> None:
    payload = {
        "provider": {
            "openai_api_key": settings.provider.openai_api_key,
            "gemini_api_key": settings.provider.gemini_api_key,
        }
    }
    secrets_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def export_settings_profile(profile_path: Path, settings: AppSettings) -> None:
    save_settings(profile_path, settings)


def import_settings_profile(profile_path: Path) -> AppSettings:
    return load_settings(profile_path)


def apply_form_values_to_settings(
    settings: AppSettings,
    *,
    window_title: str,
    provider_name: str,
    provider_model: str,
    confidence_threshold: int,
    cycle_interval_seconds: float,
    max_retries: int,
    retry_backoff_seconds: float,
    llm_max_width: int,
    llm_max_height: int,
    llm_jpeg_quality: int,
    dry_run: bool,
    operator_goal: str,
    persist_window_title: bool = False,
) -> None:
    if persist_window_title:
        settings.window.title_regex = window_title
    settings.provider.name = provider_name
    settings.provider.model = provider_model
    settings.runtime.confidence_threshold = confidence_threshold
    settings.runtime.cycle_interval_seconds = cycle_interval_seconds
    settings.runtime.max_retries = max_retries
    settings.runtime.retry_backoff_seconds = retry_backoff_seconds
    settings.runtime.llm_max_width = llm_max_width
    settings.runtime.llm_max_height = llm_max_height
    settings.runtime.llm_jpeg_quality = llm_jpeg_quality
    settings.runtime.dry_run = dry_run
    settings.prompt.operator_goal = operator_goal


def apply_settings_to_window(window: MainWindow, settings: AppSettings) -> None:
    window.provider_selector.setCurrentText(settings.provider.name)
    window.model_input.setText(settings.provider.model)
    window.confidence_spinbox.setValue(settings.runtime.confidence_threshold)
    window.cycle_interval_spinbox.setValue(settings.runtime.cycle_interval_seconds)
    window.retry_spinbox.setValue(settings.runtime.max_retries)
    window.backoff_spinbox.setValue(settings.runtime.retry_backoff_seconds)
    window.llm_max_width_spinbox.setValue(settings.runtime.llm_max_width)
    window.llm_max_height_spinbox.setValue(settings.runtime.llm_max_height)
    window.llm_jpeg_quality_spinbox.setValue(settings.runtime.llm_jpeg_quality)
    window.operator_goal_input.setText(settings.prompt.operator_goal)
    window.task_instructions_input.setText(settings.prompt.operator_goal)
    window.openai_api_key_input.setText(settings.provider.openai_api_key or "")
    window.gemini_api_key_input.setText(settings.provider.gemini_api_key or "")
    window.dry_run_checkbox.setChecked(settings.runtime.dry_run)
    window.reset_validation_state()


def check_provider_connection(
    provider: str,
    model: str,
    api_key: str | None,
    openai_client: Any | None = None,
    gemini_client: Any | None = None,
) -> str:
    if not api_key:
        raise ValueError(f"No API key configured for {provider}")

    provider_name = normalize_provider_name(provider)
    if provider_name == "openai":
        client = openai_client
        if client is None:
            openai_module = __import__("openai")
            client = openai_module.OpenAI(api_key=api_key)
        client.models.list()
        return "OpenAI connection OK"

    if provider_name == "gemini":
        client = gemini_client
        if client is None:
            genai_module = __import__("google.genai", fromlist=["Client"])
            client = genai_module.Client(api_key=api_key)
        next(iter(client.models.list()), None)
        return "Gemini connection OK"

    raise ValueError(f"Unsupported provider: {provider_name}")


def present_main_window(window) -> None:
    window.show()
    window.raise_()
    window.activateWindow()


def bring_window_to_foreground(window, user32=None) -> None:
    runtime_user32 = user32 or ctypes.windll.user32
    hwnd = int(window.winId())
    swp_nomove = 0x0002
    swp_nosize = 0x0001
    swp_showwindow = 0x0040
    flags = swp_nomove | swp_nosize | swp_showwindow
    runtime_user32.ShowWindow(hwnd, 9)
    runtime_user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, flags)
    runtime_user32.SetForegroundWindow(hwnd)
    runtime_user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, flags)


def build_llm_client(settings: AppSettings) -> LlmClient:
    llm_client = LlmClient()
    openai_adapter = None
    openai_signature: tuple[str, str | None] | None = None

    def lazy_openai_adapter(**payload):
        nonlocal openai_adapter, openai_signature
        signature = (settings.provider.model, settings.provider.openai_api_key)
        if normalize_provider_name(settings.provider.name) != "openai":
            signature = (payload.get("model") or "gpt-4.1-mini", settings.provider.openai_api_key)
        if openai_adapter is None or openai_signature != signature:
            openai_adapter = build_openai_adapter(model=signature[0], api_key=signature[1])
            openai_signature = signature
        return openai_adapter(**payload)

    gemini_adapter = None
    gemini_signature: tuple[str, str | None] | None = None

    def lazy_gemini_adapter(**payload):
        nonlocal gemini_adapter, gemini_signature
        signature = (settings.provider.model, settings.provider.gemini_api_key)
        if normalize_provider_name(settings.provider.name) != "gemini":
            signature = (payload.get("model") or "gemini-2.5-flash", settings.provider.gemini_api_key)
        if gemini_adapter is None or gemini_signature != signature:
            gemini_adapter = build_gemini_adapter(model=signature[0], api_key=signature[1])
            gemini_signature = signature
        return gemini_adapter(**payload)

    llm_client.register_adapter("openai", lazy_openai_adapter)
    llm_client.register_adapter("gemini", lazy_gemini_adapter)
    return llm_client


def build_main_window(
    settings: AppSettings,
    capture_service=None,
    llm_client=None,
    executor=None,
    config_path: Path | None = None,
    scheduler=None,
    runner=None,
    connection_tester=None,
    connection_runner=None,
    export_profile_picker=None,
    import_profile_picker=None,
) -> MainWindow:
    capture = capture_service or WindowCapture()
    runtime_llm_client = llm_client or build_llm_client(settings)
    runtime_executor = executor or ActionExecutor()
    secrets_path = get_secrets_path(config_path) if config_path is not None else None
    agent = DesktopAutomationAgent(
        capture_service=capture,
        llm_client=runtime_llm_client,
        executor=runtime_executor,
        settings=settings,
    )
    controller = RuntimeController(
        dry_run=settings.runtime.dry_run,
        agent=agent,
        scheduler=scheduler,
        runner=runner,
        interval_ms=int(settings.runtime.cycle_interval_seconds * 1000),
    )
    window = MainWindow(controller=controller)
    controller.set_provider(settings.provider.name)
    apply_settings_to_window(window, settings)
    window.set_settings_dirty(False)

    try:
        window_items = controller.refresh_available_windows()
        if window_items:
            window.set_available_windows(window_items)
        if settings.window.title_regex:
            controller.set_selected_window(settings.window.title_regex)
            window.window_selector.setCurrentText(settings.window.title_regex)
    except Exception as exc:
        window.append_log(f"Window enumeration unavailable: {exc}")

    window.set_settings_dirty(False)
    window.reset_validation_state()

    runtime_connection_tester = connection_tester or check_provider_connection
    runtime_connection_runner = connection_runner

    def collect_form_settings() -> None:
        apply_form_values_to_settings(
            settings,
            window_title=window.window_selector.currentText(),
            provider_name=window.provider_selector.currentText(),
            provider_model=window.model_input.text(),
            confidence_threshold=window.confidence_spinbox.value(),
            cycle_interval_seconds=window.cycle_interval_spinbox.value(),
            max_retries=window.retry_spinbox.value(),
            retry_backoff_seconds=window.backoff_spinbox.value(),
            llm_max_width=window.llm_max_width_spinbox.value(),
            llm_max_height=window.llm_max_height_spinbox.value(),
            llm_jpeg_quality=window.llm_jpeg_quality_spinbox.value(),
            dry_run=window.dry_run_checkbox.isChecked(),
            operator_goal=window.operator_goal_input.text(),
        )

    def choose_export_profile_path() -> Path | None:
        if export_profile_picker is not None:
            return export_profile_picker()
        file_name, _ = QFileDialog.getSaveFileName(window, "Export Settings Profile", "settings-profile.yaml", "YAML Files (*.yaml *.yml)")
        return Path(file_name) if file_name else None

    def choose_import_profile_path() -> Path | None:
        if import_profile_picker is not None:
            return import_profile_picker()
        file_name, _ = QFileDialog.getOpenFileName(window, "Import Settings Profile", "", "YAML Files (*.yaml *.yml)")
        return Path(file_name) if file_name else None

    def handle_connection_success(message: str) -> None:
        window.set_connection_testing(False)
        window.set_settings_feedback(message)
        window.set_error_details("")
        window.append_log(message)

    def handle_connection_error(message: str) -> None:
        window.set_connection_testing(False)
        window.error_label.setText(f"Error: {message}")
        window.set_error_details(message)
        window.append_log(f"ERROR: {message}")
        window.set_settings_feedback(message)

    def run_connection_test() -> None:
        provider = window.provider_selector.currentText()
        api_key = window.openai_api_key_input.text() if normalize_provider_name(provider) == "openai" else window.gemini_api_key_input.text()
        task = lambda: runtime_connection_tester(provider, window.model_input.text(), api_key)
        window.set_connection_testing(True)
        if runtime_connection_runner is not None:
            runtime_connection_runner.submit(task, handle_connection_success, handle_connection_error)
            return
        try:
            handle_connection_success(task())
        except Exception as exc:
            handle_connection_error(str(exc))

    window.test_connection_button.clicked.connect(run_connection_test)

    def export_profile() -> None:
        profile_path = choose_export_profile_path()
        if profile_path is None:
            return
        collect_form_settings()
        export_settings_profile(profile_path, settings)
        window.set_settings_feedback(f"Exported profile to {profile_path.name}")

    def import_profile() -> None:
        profile_path = choose_import_profile_path()
        if profile_path is None:
            return
        loaded = import_settings_profile(profile_path)
        openai_api_key = settings.provider.openai_api_key
        gemini_api_key = settings.provider.gemini_api_key
        settings.window = loaded.window
        settings.runtime = loaded.runtime
        settings.provider.name = loaded.provider.name
        settings.provider.model = loaded.provider.model
        settings.prompt = loaded.prompt
        settings.debug = loaded.debug
        settings.interaction = loaded.interaction
        settings.hotkeys = loaded.hotkeys
        settings.provider.openai_api_key = openai_api_key
        settings.provider.gemini_api_key = gemini_api_key
        apply_settings_to_window(window, settings)
        if settings.window.title_regex:
            window.window_selector.setCurrentText(settings.window.title_regex)
        window.set_settings_dirty(True)
        window.set_settings_feedback(f"Imported profile from {profile_path.name}")

    window.export_profile_button.clicked.connect(export_profile)
    window.import_profile_button.clicked.connect(import_profile)

    if config_path is not None:
        def save_from_form() -> None:
            collect_form_settings()
            settings.provider.openai_api_key = window.openai_api_key_input.text() or None
            settings.provider.gemini_api_key = window.gemini_api_key_input.text() or None
            save_settings(config_path, settings)
            if secrets_path is not None:
                save_secrets(settings, secrets_path)
            window.set_settings_dirty(False)
            window.set_settings_feedback(f"Saved to {config_path.name}")

        def reset_from_disk() -> None:
            loaded = load_settings_with_secrets(config_path)
            settings.window = loaded.window
            settings.runtime = loaded.runtime
            settings.provider.name = loaded.provider.name
            settings.provider.model = loaded.provider.model
            settings.prompt = loaded.prompt
            settings.debug = loaded.debug
            settings.interaction = loaded.interaction
            settings.hotkeys = loaded.hotkeys
            settings.provider.openai_api_key = loaded.provider.openai_api_key
            settings.provider.gemini_api_key = loaded.provider.gemini_api_key
            apply_settings_to_window(window, settings)
            if settings.window.title_regex:
                window.window_selector.setCurrentText(settings.window.title_regex)
            window.set_settings_dirty(False)
            window.set_settings_feedback(f"Reset from {config_path.name}")

        window.save_settings_button.clicked.connect(save_from_form)
        window.reset_settings_button.clicked.connect(reset_from_disk)

    return window


def wire_global_hotkeys(controller: Any, settings: AppSettings, hotkey_manager: Any) -> None:
    hotkey_manager.start(
        {
            settings.hotkeys.start: controller.start,
            settings.hotkeys.pause: controller.pause,
            settings.hotkeys.stop: controller.stop,
        }
    )


def launch_native_panel(settings: AppSettings, config_path: Path | None = None) -> int:
    enable_dpi_awareness()
    qt_app = QApplication.instance() or QApplication([])
    window = build_main_window(settings, config_path=config_path)
    hotkey_manager = GlobalHotkeyManager()
    wire_global_hotkeys(window.controller, settings, hotkey_manager)
    qt_app.aboutToQuit.connect(hotkey_manager.stop)
    if window.controller is not None:
        qt_app.aboutToQuit.connect(window.controller.stop)
    present_main_window(window)
    bring_window_to_foreground(window)
    return qt_app.exec()


def _running_under_pytest() -> bool:
    return "PYTEST_CURRENT_TEST" in os.environ


@app.callback(invoke_without_command=True)
def main(
    provider: str = typer.Option("gemini", "--provider"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    window_title_regex: str | None = typer.Option(None, "--window-title-regex"),
    config_path: Path = typer.Option(Path("config.yaml"), "--config"),
) -> None:
    settings = load_settings_with_secrets(config_path)
    settings.provider.name = provider
    if dry_run:
        settings.runtime.dry_run = True
    if window_title_regex is not None:
        settings.window.title_regex = window_title_regex

    if _running_under_pytest():
        return

    launch_native_panel(settings, config_path=config_path)


if __name__ == "__main__":
    app()
