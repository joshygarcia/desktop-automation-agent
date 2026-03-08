from main import apply_form_values_to_settings
from settings import AppSettings


def test_apply_form_values_does_not_persist_window_title_by_default() -> None:
    settings = AppSettings.model_validate(
        {
            "window": {"title_regex": "Original Window"},
            "runtime": {},
            "provider": {"name": "gemini", "model": "gemini-2.5-flash"},
            "prompt": {"operator_goal": "Goal"},
            "debug": {},
            "interaction": {},
            "hotkeys": {},
        }
    )

    apply_form_values_to_settings(
        settings,
        window_title="Transient App Window",
        provider_name="openai",
        provider_model="gpt-4.1-mini",
        confidence_threshold=90,
        cycle_interval_seconds=2.0,
        max_retries=3,
        retry_backoff_seconds=1.0,
        llm_max_width=1280,
        llm_max_height=720,
        llm_jpeg_quality=80,
        dry_run=False,
        operator_goal="Updated Goal",
    )

    assert settings.window.title_regex == "Original Window"
    assert settings.provider.name == "openai"
    assert settings.provider.model == "gpt-4.1-mini"
    assert settings.prompt.operator_goal == "Updated Goal"
