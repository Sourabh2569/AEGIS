# ADR 0042: Instrument Identity And Mapping Priority

`aegis_instrument_id` remains authoritative. Mapping prefers ISIN, then exchange code, then exchange symbol, while preserving aliases and blocking ambiguity.
