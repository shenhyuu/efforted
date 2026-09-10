from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Energy = Literal["low", "mid", "enough"]
DaySlot = Literal["morning", "afternoon", "evening", "night"]


class PasswordInput(BaseModel):
    password: str = Field(min_length=6, max_length=128)


class CheckinCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    client_uuid: str | None = Field(default=None, min_length=1, max_length=80)
    energy: Energy | None = None
    note: str | None = Field(default=None, max_length=500)


class BatchCheckinItem(CheckinCreate):
    client_created_at: datetime | None = None

    @field_validator("client_created_at")
    @classmethod
    def validate_client_created_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("client_created_at must include a timezone")
        normalized = value.astimezone(timezone.utc)
        if normalized > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError("client_created_at cannot be in the future")
        return normalized


class BatchCheckinCreate(BaseModel):
    items: list[BatchCheckinItem] = Field(max_length=100)


class BackfillCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    day: date | None = None
    day_slot: DaySlot | None = None
    energy: Energy | None = None
    note: str | None = Field(default=None, max_length=500)


class RecordUpdate(BaseModel):
    day: date | None = None
    day_slot: DaySlot | None = None
    energy: Energy | None = None
    content: str | None = Field(default=None, max_length=500)


class LampCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    message: str = Field(min_length=1, max_length=1000)
    energy_at_write: Energy | None = None


class SettingsUpdate(BaseModel):
    low_energy_mode: bool | None = None
    hide_all_numbers: bool | None = None
    nothing_mode: bool | None = None
    privacy_mode: bool | None = None


class PurgeInput(BaseModel):
    confirm: bool


class ExportInput(BaseModel):
    format: Literal["json", "png"] = "json"
