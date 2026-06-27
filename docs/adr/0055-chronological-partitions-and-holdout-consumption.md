# ADR 0055: Chronological Partitions And Holdout Consumption

Status: accepted.

Actual experiments must follow warmup, training, validation, and locked holdout order. First holdout inspection creates a usage record; reuse for tuning is blocked.
