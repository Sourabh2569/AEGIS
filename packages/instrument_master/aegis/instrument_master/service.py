from __future__ import annotations

from aegis.domain.models import Instrument, InstrumentAlias


class InstrumentMasterService:
    def __init__(self) -> None:
        self.instruments: dict[str, Instrument] = {}
        self.aliases: dict[str, list[InstrumentAlias]] = {}

    def add_instrument(self, instrument: Instrument) -> Instrument:
        self.instruments[instrument.id] = instrument
        return instrument

    def add_alias(self, alias: InstrumentAlias) -> InstrumentAlias:
        if alias.instrument_id not in self.instruments:
            raise ValueError("Cannot add alias for unknown instrument.")
        self.aliases.setdefault(alias.instrument_id, []).append(alias)
        return alias

    def known_aegis_ids(self) -> set[str]:
        return {instrument.aegis_instrument_id for instrument in self.instruments.values()}
