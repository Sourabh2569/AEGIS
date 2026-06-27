# Actual Feature Activation

Required feature runs must carry dataset version, data origin, instrument-master version, universe version, corporate-action version, feature definitions, calculation time, source cutoff, validation status, coverage, software commit, and creator.

Point-in-time rule:

```text
feature_available_time <= decision_time
```

EOD features become available after market close and may execute no earlier than the next eligible market session.

Current local state: blocked until actual research readiness passes.
