# ADR 0043: Immutable Raw Object Capture

Every provider payload must be stored as a hashed raw object before normalization. Corrections create new objects and new dataset versions; raw objects are not overwritten.
