"""Structured agent trace events for the future demo panel. Not chat; no model reasoning."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TraceEvent:
    agent: str
    action: str
    reason: str
    input_refs: list[str] = field(default_factory=list)
    next_step: str | None = None
    output_ref: str | None = None
    run_id: str | None = None
    timestamp: str | None = None
    receipt: dict | None = None  # sanitized routing evidence for model-backed steps

    def to_dict(self) -> dict:
        return {'run_id': self.run_id, 'timestamp': self.timestamp, 'agent': self.agent, 'action': self.action,
                'reason': self.reason, 'input_refs': list(self.input_refs), 'next_step': self.next_step,
                'output_ref': self.output_ref, 'receipt': self.receipt}
