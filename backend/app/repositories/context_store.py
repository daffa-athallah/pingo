"""Additional application state. The existing LoopRepository agent protocol stays intact."""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ContextEvaluation:
    evaluation_id: str
    created_at: str
    payload: dict


@dataclass(frozen=True)
class Notification:
    notification_id: str
    loop_id: str
    created_at: str
    payload: dict


class ContextStore(Protocol):
    def save_context_evaluation(self, evaluation: ContextEvaluation) -> None: ...
    def get_context_evaluation(self, evaluation_id: str) -> ContextEvaluation | None: ...
    def save_notification(self, notification: Notification) -> None: ...
    def get_notification(self, notification_id: str) -> Notification | None: ...
    def list_notifications(self) -> list[Notification]: ...
