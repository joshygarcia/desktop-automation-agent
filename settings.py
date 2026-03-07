from pydantic import BaseModel, ConfigDict, Field


class WindowSettings(BaseModel):
    title_regex: str


class RuntimeSettings(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    confidence_threshold: int = Field(default=80, ge=0, le=100)
    dry_run: bool = True
    cycle_interval_seconds: float = Field(default=1.0, ge=0.1, le=60.0)
    llm_max_width: int = Field(default=1024, ge=256, le=4096)
    llm_max_height: int = Field(default=1024, ge=256, le=4096)
    llm_jpeg_quality: int = Field(default=70, ge=30, le=95)
    max_retries: int = Field(default=2, ge=1, le=10)
    retry_backoff_seconds: float = Field(default=0.5, ge=0.0, le=30.0)


class ProviderSettings(BaseModel):
    name: str = "gemini"
    model: str = "gemini-2.5-flash"
    openai_api_key: str | None = Field(default=None, exclude=True)
    gemini_api_key: str | None = Field(default=None, exclude=True)


class PromptSettings(BaseModel):
    operator_goal: str = "Observe the target window and return the safest next action."


class DebugSettings(BaseModel):
    enabled: bool = True
    screenshot_dir: str = "debug_screenshots"


class InteractionSettings(BaseModel):
    mouse_speed_multiplier: float = 1.0
    enable_variance: bool = True


class HotkeySettings(BaseModel):
    start: str = "F8"
    pause: str = "F9"
    stop: str = "F10"


class AppSettings(BaseModel):
    window: WindowSettings
    runtime: RuntimeSettings = Field(default_factory=RuntimeSettings)
    provider: ProviderSettings = Field(default_factory=ProviderSettings)
    prompt: PromptSettings = Field(default_factory=PromptSettings)
    debug: DebugSettings = Field(default_factory=DebugSettings)
    interaction: InteractionSettings = Field(default_factory=InteractionSettings)
    hotkeys: HotkeySettings = Field(default_factory=HotkeySettings)
