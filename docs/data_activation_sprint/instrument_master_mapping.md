# Instrument Master Mapping

AEGIS identity remains authoritative through `aegis_instrument_id`.

Mapping priority:

1. ISIN.
2. Exchange and exchange instrument code.
3. Exchange and symbol.
4. Alias or historical symbol with explicit validity window.

Only verified mappings may enter research-eligible datasets.
