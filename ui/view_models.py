from typing import Any

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field


class StatusViewModel(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    status_label: str
    last_action: str | None = None
    confidence: int | None = None
    mode_label: str
    reason_text: str | None = None
    preview_image: Any | None = None
    error_text: str | None = None
    log_lines: list[str] = Field(default_factory=list)
    result_text: str | None = None
    selected_hwnd: int | None = None
    inferred_goal: str | None = None
    completion_confidence_trend: list[int] = Field(default_factory=list)
    completion_reason_history: list[str] = Field(default_factory=list)


def build_status_view_model(
    agent_state: str,
    last_action: str | None,
    confidence: int | None,
    dry_run: bool,
    reason_text: str | None = None,
    preview_image: Any | None = None,
    error_text: str | None = None,
    log_lines: list[str] | None = None,
    result_text: str | None = None,
    selected_hwnd: int | None = None,
    inferred_goal: str | None = None,
    completion_confidence_trend: list[int] | None = None,
    completion_reason_history: list[str] | None = None,
) -> StatusViewModel:
    return StatusViewModel(
        status_label=agent_state.capitalize(),
        last_action=last_action,
        confidence=confidence,
        mode_label="Dry Run" if dry_run else "Live",
        reason_text=reason_text,
        preview_image=preview_image,
        error_text=error_text,
        log_lines=log_lines or [],
        result_text=result_text,
        selected_hwnd=selected_hwnd,
        inferred_goal=inferred_goal,
        completion_confidence_trend=completion_confidence_trend or [],
        completion_reason_history=completion_reason_history or [],
    )
