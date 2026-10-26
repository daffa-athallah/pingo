"""HTTP context inputs adapt to the existing ContextEvent, without a second agent model."""
from __future__ import annotations

from enum import Enum
import json
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from backend.app.domain.models import ContextEvent, ContextType


class ContextSource(str, Enum):
    SIMULATED = 'SIMULATED'
    BROWSER = 'BROWSER'
    CALENDAR = 'CALENDAR'


class LocationInput(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    accuracy_meters: float | None = Field(default=None, ge=0, le=100000)
    name: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=100)
    country: str | None = Field(default=None, max_length=100)

    @model_validator(mode='after')
    def paired(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError('Latitude and longitude must be supplied together.')
        return self


class ContextInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    context_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,100}$')
    source: ContextSource
    type: Literal['LOCATION', 'CALENDAR', 'TIME']
    timestamp: AwareDatetime
    title: str = Field(default='', max_length=200)
    location: LocationInput | None = None
    start_time: AwareDatetime | None = None
    end_time: AwareDatetime | None = None
    description: str = Field(default='', max_length=1000)
    timezone: str = Field(default='Australia/Melbourne', max_length=80)
    metadata: dict[str, str] = Field(default_factory=dict, max_length=20)

    @model_validator(mode='after')
    def valid_event(self):
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError('Use an IANA timezone such as Australia/Melbourne.') from None
        if any(len(k) > 80 or len(v) > 1000 for k, v in self.metadata.items()):
            raise ValueError('Context metadata is too large.')
        if self.type == 'LOCATION' and (not self.location or self.location.latitude is None):
            raise ValueError('Location events require coordinates.')
        if self.type == 'CALENDAR' and (not self.title.strip() or not self.start_time or not self.end_time):
            raise ValueError('Calendar events require a title, start and end.')
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValueError('Calendar end must be after start.')
        if self.source == ContextSource.BROWSER and self.type != 'LOCATION':
            raise ValueError('Browser input currently supports location only.')
        if self.source == ContextSource.CALENDAR and self.type != 'CALENDAR':
            raise ValueError('Calendar source requires a calendar event.')
        return self

    def to_event(self) -> ContextEvent:
        # Reserved metadata always wins over supplied custom fields.
        metadata = {**self.metadata, 'source': self.source.value, 'timestamp': self.timestamp.isoformat(),
                    'timezone': self.timezone, 'description': self.description}
        if self.start_time:
            metadata['start_time'] = self.start_time.isoformat()
        if self.end_time:
            metadata['end_time'] = self.end_time.isoformat()
        if self.location:
            for key in ('latitude', 'longitude', 'accuracy_meters'):
                value = getattr(self.location, key)
                if value is not None:
                    metadata[key] = str(value)
        place = self.location or LocationInput()
        return ContextEvent(self.context_id, ContextType(self.type), self.title.strip() or self.type.title(),
                            (self.start_time or self.timestamp).isoformat(), place.name, place.city, place.country, metadata)


class EvaluationInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    now: AwareDatetime
    events: list[ContextInput] = Field(min_length=1, max_length=20)

    @model_validator(mode='after')
    def unique(self):
        if len({e.context_id for e in self.events}) != len(self.events):
            raise ValueError('Context IDs must be unique within an evaluation.')
        if any(e.source == ContextSource.SIMULATED for e in self.events) and any(e.source != ContextSource.SIMULATED for e in self.events):
            raise ValueError('Evaluate simulated and live observations separately.')
        return self

    def fingerprint(self) -> str:
        import hashlib
        return 'eval_' + hashlib.sha256(json.dumps(self.model_dump(mode='json'), sort_keys=True).encode()).hexdigest()[:32]


class NotificationAction(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['DELIVERED', 'READ', 'DISMISS', 'DONE', 'SNOOZE', 'NOT_RELEVANT', 'JUST_INSPIRATION']
