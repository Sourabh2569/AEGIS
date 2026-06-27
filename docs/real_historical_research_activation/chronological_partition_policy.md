# Chronological Partition Policy

Required order:

```text
Warmup -> Training -> Validation -> Locked Holdout
```

No future partition may affect prior decisions. Holdout usage must be recorded on first inspection. Holdout reuse for tuning is blocked.

If dates are missing, the manifest stays draft.
