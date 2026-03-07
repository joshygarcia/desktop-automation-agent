from typing import Literal

from pydantic import BaseModel, Field


ActionName = Literal[
    "wait",
    "click",
    "double_click",
    "drag",
    "type_text",
    "press_hotkey",
]


class ActionParameters(BaseModel):
    x_loc: float | None = None
    y_loc: float | None = None
    end_x_loc: float | None = None
    end_y_loc: float | None = None
    text: str | None = None
    keys: list[str] = Field(default_factory=list)


class TaskAssessment(BaseModel):
    inferred_goal: str | None = None
    success_criteria: str | None = None
    is_complete: bool = False
    completion_confidence: int = Field(default=0, ge=0, le=100)
    completion_reason: str | None = None


class Decision(BaseModel):
    action: ActionName
    parameters: ActionParameters = Field(default_factory=ActionParameters)
    reason: str
    confidence: int = Field(ge=0, le=100)
    task: TaskAssessment = Field(default_factory=TaskAssessment)
