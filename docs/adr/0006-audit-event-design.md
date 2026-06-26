# ADR 0006: Audit Event Design

Audit events are append-only. Critical mutations emit events with actor, correlation ID, before state, after state, and metadata sufficient to reconstruct the change.
