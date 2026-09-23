from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ClassName = Literal[
    "person",
    "vehicle",
    "drone",
    "helicopter",
]


class TrackState(str, Enum):
    ACTIVE = "ACTIVE"
    LOST = "LOST"
    REACQUIRED = "REACQUIRED"


CLASS_ID_BY_NAME: dict[ClassName, int] = {
    "person": 0,
    "vehicle": 1,
    "drone": 2,
    "helicopter": 3,
}


class Track(BaseModel):
    """
    Frozen SHIBLI v1.1 tracking contract.

    The provider is responsible for detection/tracking and for
    normalizing source classes to the four canonical SHIBLI classes.
    """

    model_config = ConfigDict(extra="forbid")

    track_id: int
    class_id: int = Field(ge=0, le=3)
    class_name: ClassName
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: list[float] = Field(min_length=4, max_length=4)
    center: list[float] = Field(min_length=2, max_length=2)
    state: TrackState

    @model_validator(mode="after")
    def validate_class_mapping(self) -> "Track":
        expected_id = CLASS_ID_BY_NAME[self.class_name]

        if self.class_id != expected_id:
            raise ValueError(
                f"class_id {self.class_id} does not match "
                f"class_name '{self.class_name}' "
                f"(expected {expected_id})"
            )

        return self