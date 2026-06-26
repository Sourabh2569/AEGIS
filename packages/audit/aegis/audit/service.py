from __future__ import annotations

from dataclasses import asdict
from typing import Any

from aegis.domain.models import AuditEvent


class AuditLog:
    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def record(
        self,
        *,
        event_type: str,
        entity_type: str,
        entity_id: str,
        actor_type: str,
        actor_id: str,
        action: str,
        correlation_id: str,
        before_state: dict[str, Any] | None = None,
        after_state: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            before_state_json=before_state,
            after_state_json=after_state,
            metadata_json=metadata or {},
            correlation_id=correlation_id,
        )
        self._events.append(event)
        return event

    def list_events(self) -> list[AuditEvent]:
        return list(self._events)

    def get_event(self, event_id: str) -> AuditEvent | None:
        return next((event for event in self._events if event.id == event_id), None)

    def as_dicts(self) -> list[dict[str, Any]]:
        return [asdict(event) for event in self._events]
