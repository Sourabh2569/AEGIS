"""Real, verified instrument metadata for AEGIS's Sector Screener -- a second,
deliberately isolated universe (Pharmaceuticals / Solar & Renewable Energy /
Electronics Manufacturing), additive to the existing Nifty 50 momentum
universe in kite_connect_provider.py's CURATED_INSTRUMENT_METADATA, never
merged into it.

Two sectors originally requested (Semiconductors, Data Centres) are not
included -- real research this session found neither has a coherent set of
real NSE-listed pure-play peers today (no listed semiconductor fabricator;
major data-centre operators are unlisted). Revisit if that changes.

Every entry below was cross-verified against two independent real NSE
sources, matching CURATED_INSTRUMENT_METADATA's own documented discipline:
- Pharmaceuticals: the real, official NIFTY PHARMA index constituent list,
  pulled live from NSE's own index API.
- Solar & Renewable Energy / Electronics Manufacturing: no official NSE
  index exists for either: each symbol was individually confirmed real via
  NSE's corporates-financial-results discovery API (a real, live filing
  exists), then ISIN and listing date and company legal name were taken
  from NSE's own securities master (nsearchives.nseindia.com/content/equities/EQUITY_L.csv)
  as the authoritative source.

Real discrepancy found and resolved during that cross-check: 10 of the 35
symbols' ISINs, as reported by the discovery API's filing metadata, differ
from the securities master in their last two digits only (e.g. DRREDDY:
discovery API "INE089A01023" vs. securities master "INE089A01031") -- same
company, same first 10 characters, most likely the discovery API surfacing
an ISIN suffix that was valid at the time of an older filing before a
subsequent corporate action (e.g. a face-value change) reissued the suffix.
The securities master's value is used below as the current, authoritative
ISIN in every such case.

"sector" here is this deliberate 3-sector Screener grouping the user chose
-- not NSE's own broader GICS-style sector/industry taxonomy (which has no
official "Solar & Renewable Energy" or "Electronics Manufacturing" category
today). "industry" is set equal to "sector", matching
CURATED_INSTRUMENT_METADATA's own convention of not inventing a second
classification tier that hasn't been separately verified.

Real, expected overlap: CIPLA, DRREDDY, and SUNPHARMA are constituents of
*both* the main Nifty 50 universe (CURATED_INSTRUMENT_METADATA, under
"Healthcare") and the real NIFTY PHARMA index below -- they legitimately
appear in both dicts, each under its own distinct aegis_instrument_id. This
is not a bug; the two universes are deliberately independent and never
merged or deduplicated (see the Sector Screener isolation design).
"""

from __future__ import annotations

from datetime import date

from aegis.provider_adapters.kite_connect_provider import CuratedInstrumentMetadata

PHARMACEUTICALS = "Pharmaceuticals"
SOLAR_RENEWABLE_ENERGY = "Solar & Renewable Energy"
ELECTRONICS_MANUFACTURING = "Electronics Manufacturing"

SECTOR_SCREENER_INSTRUMENTS: dict[str, CuratedInstrumentMetadata] = {
    # Pharmaceuticals -- real, official NIFTY PHARMA index constituents
    # (20), pulled live from NSE's own index API this session.
    "DIVISLAB": CuratedInstrumentMetadata(
        isin="INE361B01024",
        company_legal_name="Divi's Laboratories Limited",
        security_type="EQUITY",
        listing_date=date(2003, 3, 12),
        sector=PHARMACEUTICALS,
        industry=PHARMACEUTICALS,
        aegis_instrument_id="AEGIS-IN-000051",
    ),
    "LAURUSLABS": CuratedInstrumentMetadata(
        isin="INE947Q01028",
        company_legal_name="Laurus Labs Limited",
        security_type="EQUITY",
        listing_date=date(2016, 12, 19),
        sector=PHARMACEUTICALS,
        industry=PHARMACEUTICALS,
        aegis_instrument_id="AEGIS-IN-000052",
    ),
    "DRREDDY": CuratedInstrumentMetadata(
        isin="INE089A01031",
        company_legal_name="Dr. Reddy's Laboratories Limited",
        security_type="EQUITY",
        listing_date=date(2003, 5, 30),
        sector=PHARMACEUTICALS,
        industry=PHARMACEUTICALS,
        aegis_instrument_id="AEGIS-IN-000053",
    ),
    "SUNPHARMA": CuratedInstrumentMetadata(
        isin="INE044A01036",
        company_legal_name="Sun Pharmaceutical Industries Limited",
        security_type="EQUITY",
        listing_date=date(1995, 2, 8),
        sector=PHARMACEUTICALS,
        industry=PHARMACEUTICALS,
        aegis_instrument_id="AEGIS-IN-000054",
    ),
    "WOCKPHARMA": CuratedInstrumentMetadata(
        isin="INE049B01025",
        company_legal_name="Wockhardt Limited",
        security_type="EQUITY",
        listing_date=date(2000, 2, 23),
        sector=PHARMACEUTICALS,
        industry=PHARMACEUTICALS,
        aegis_instrument_id="AEGIS-IN-000055",
    ),
    "CIPLA": CuratedInstrumentMetadata(
        isin="INE059A01026",
        company_legal_name="Cipla Limited",
        security_type="EQUITY",
        listing_date=date(1995, 2, 8),
        sector=PHARMACEUTICALS,
        industry=PHARMACEUTICALS,
        aegis_instrument_id="AEGIS-IN-000056",
    ),
    "SAILIFE": CuratedInstrumentMetadata(
        isin="INE570L01029",
        company_legal_name="Sai Life Sciences Limited",
        security_type="EQUITY",
        listing_date=date(2024, 12, 18),
        sector=PHARMACEUTICALS,
        industry=PHARMACEUTICALS,
        aegis_instrument_id="AEGIS-IN-000057",
    ),
    "BIOCON": CuratedInstrumentMetadata(
        isin="INE376G01013",
        company_legal_name="Biocon Limited",
        security_type="EQUITY",
        listing_date=date(2004, 4, 7),
        sector=PHARMACEUTICALS,
        industry=PHARMACEUTICALS,
        aegis_instrument_id="AEGIS-IN-000058",
    ),
    "TORNTPHARM": CuratedInstrumentMetadata(
        isin="INE685A01028",
        company_legal_name="Torrent Pharmaceuticals Limited",
        security_type="EQUITY",
        listing_date=date(2002, 11, 25),
        sector=PHARMACEUTICALS,
        industry=PHARMACEUTICALS,
        aegis_instrument_id="AEGIS-IN-000059",
    ),
    "LUPIN": CuratedInstrumentMetadata(
        isin="INE326A01037",
        company_legal_name="Lupin Limited",
        security_type="EQUITY",
        listing_date=date(2001, 9, 10),
        sector=PHARMACEUTICALS,
        industry=PHARMACEUTICALS,
        aegis_instrument_id="AEGIS-IN-000060",
    ),
    "ALKEM": CuratedInstrumentMetadata(
        isin="INE540L01014",
        company_legal_name="Alkem Laboratories Limited",
        security_type="EQUITY",
        listing_date=date(2015, 12, 23),
        sector=PHARMACEUTICALS,
        industry=PHARMACEUTICALS,
        aegis_instrument_id="AEGIS-IN-000061",
    ),
    "MANKIND": CuratedInstrumentMetadata(
        isin="INE634S01028",
        company_legal_name="Mankind Pharma Limited",
        security_type="EQUITY",
        listing_date=date(2023, 5, 9),
        sector=PHARMACEUTICALS,
        industry=PHARMACEUTICALS,
        aegis_instrument_id="AEGIS-IN-000062",
    ),
    "ZYDUSLIFE": CuratedInstrumentMetadata(
        isin="INE010B01027",
        company_legal_name="Zydus Lifesciences Limited",
        security_type="EQUITY",
        listing_date=date(2000, 4, 18),
        sector=PHARMACEUTICALS,
        industry=PHARMACEUTICALS,
        aegis_instrument_id="AEGIS-IN-000063",
    ),
    "GLAND": CuratedInstrumentMetadata(
        isin="INE068V01023",
        company_legal_name="Gland Pharma Limited",
        security_type="EQUITY",
        listing_date=date(2020, 11, 20),
        sector=PHARMACEUTICALS,
        industry=PHARMACEUTICALS,
        aegis_instrument_id="AEGIS-IN-000064",
    ),
    "GLENMARK": CuratedInstrumentMetadata(
        isin="INE935A01035",
        company_legal_name="Glenmark Pharmaceuticals Limited",
        security_type="EQUITY",
        listing_date=date(2000, 2, 7),
        sector=PHARMACEUTICALS,
        industry=PHARMACEUTICALS,
        aegis_instrument_id="AEGIS-IN-000065",
    ),
    "AUROPHARMA": CuratedInstrumentMetadata(
        isin="INE406A01037",
        company_legal_name="Aurobindo Pharma Limited",
        security_type="EQUITY",
        listing_date=date(2000, 7, 19),
        sector=PHARMACEUTICALS,
        industry=PHARMACEUTICALS,
        aegis_instrument_id="AEGIS-IN-000066",
    ),
    "PPLPHARMA": CuratedInstrumentMetadata(
        isin="INE0DK501011",
        company_legal_name="Piramal Pharma Limited",
        security_type="EQUITY",
        listing_date=date(2022, 10, 19),
        sector=PHARMACEUTICALS,
        industry=PHARMACEUTICALS,
        aegis_instrument_id="AEGIS-IN-000067",
    ),
    "IPCALAB": CuratedInstrumentMetadata(
        isin="INE571A01038",
        company_legal_name="IPCA Laboratories Limited",
        security_type="EQUITY",
        listing_date=date(1995, 2, 8),
        sector=PHARMACEUTICALS,
        industry=PHARMACEUTICALS,
        aegis_instrument_id="AEGIS-IN-000068",
    ),
    "ABBOTINDIA": CuratedInstrumentMetadata(
        isin="INE358A01014",
        company_legal_name="Abbott India Limited",
        security_type="EQUITY",
        listing_date=date(2010, 1, 8),
        sector=PHARMACEUTICALS,
        industry=PHARMACEUTICALS,
        aegis_instrument_id="AEGIS-IN-000069",
    ),
    "AJANTPHARM": CuratedInstrumentMetadata(
        isin="INE031B01049",
        company_legal_name="Ajanta Pharma Limited",
        security_type="EQUITY",
        listing_date=date(2000, 5, 29),
        sector=PHARMACEUTICALS,
        industry=PHARMACEUTICALS,
        aegis_instrument_id="AEGIS-IN-000070",
    ),
    # Solar & Renewable Energy -- no official NSE index; each individually
    # verified real via a live filing this session (10).
    "WAAREEENER": CuratedInstrumentMetadata(
        isin="INE377N01017",
        company_legal_name="Waaree Energies Limited",
        security_type="EQUITY",
        listing_date=date(2024, 10, 28),
        sector=SOLAR_RENEWABLE_ENERGY,
        industry=SOLAR_RENEWABLE_ENERGY,
        aegis_instrument_id="AEGIS-IN-000071",
    ),
    "PREMIERENE": CuratedInstrumentMetadata(
        isin="INE0BS701011",
        company_legal_name="Premier Energies Limited",
        security_type="EQUITY",
        listing_date=date(2024, 9, 3),
        sector=SOLAR_RENEWABLE_ENERGY,
        industry=SOLAR_RENEWABLE_ENERGY,
        aegis_instrument_id="AEGIS-IN-000072",
    ),
    "BORORENEW": CuratedInstrumentMetadata(
        isin="INE666D01022",
        company_legal_name="Borosil Renewables Limited",
        security_type="EQUITY",
        listing_date=date(2018, 5, 25),
        sector=SOLAR_RENEWABLE_ENERGY,
        industry=SOLAR_RENEWABLE_ENERGY,
        aegis_instrument_id="AEGIS-IN-000073",
    ),
    "KPIGREEN": CuratedInstrumentMetadata(
        isin="INE542W01025",
        company_legal_name="KPI Green Energy Limited",
        security_type="EQUITY",
        listing_date=date(2021, 7, 27),
        sector=SOLAR_RENEWABLE_ENERGY,
        industry=SOLAR_RENEWABLE_ENERGY,
        aegis_instrument_id="AEGIS-IN-000074",
    ),
    "ADANIGREEN": CuratedInstrumentMetadata(
        isin="INE364U01010",
        company_legal_name="Adani Green Energy Limited",
        security_type="EQUITY",
        listing_date=date(2018, 6, 18),
        sector=SOLAR_RENEWABLE_ENERGY,
        industry=SOLAR_RENEWABLE_ENERGY,
        aegis_instrument_id="AEGIS-IN-000075",
    ),
    "NTPCGREEN": CuratedInstrumentMetadata(
        isin="INE0ONG01011",
        company_legal_name="NTPC Green Energy Limited",
        security_type="EQUITY",
        listing_date=date(2024, 11, 27),
        sector=SOLAR_RENEWABLE_ENERGY,
        industry=SOLAR_RENEWABLE_ENERGY,
        aegis_instrument_id="AEGIS-IN-000076",
    ),
    "JSWENERGY": CuratedInstrumentMetadata(
        isin="INE121E01018",
        company_legal_name="JSW Energy Limited",
        security_type="EQUITY",
        listing_date=date(2010, 1, 4),
        sector=SOLAR_RENEWABLE_ENERGY,
        industry=SOLAR_RENEWABLE_ENERGY,
        aegis_instrument_id="AEGIS-IN-000077",
    ),
    "TATAPOWER": CuratedInstrumentMetadata(
        isin="INE245A01021",
        company_legal_name="Tata Power Company Limited",
        security_type="EQUITY",
        listing_date=date(1996, 4, 3),
        sector=SOLAR_RENEWABLE_ENERGY,
        industry=SOLAR_RENEWABLE_ENERGY,
        aegis_instrument_id="AEGIS-IN-000078",
    ),
    "SJVN": CuratedInstrumentMetadata(
        isin="INE002L01015",
        company_legal_name="SJVN Limited",
        security_type="EQUITY",
        listing_date=date(2010, 5, 20),
        sector=SOLAR_RENEWABLE_ENERGY,
        industry=SOLAR_RENEWABLE_ENERGY,
        aegis_instrument_id="AEGIS-IN-000079",
    ),
    "NHPC": CuratedInstrumentMetadata(
        isin="INE848E01016",
        company_legal_name="NHPC Limited",
        security_type="EQUITY",
        listing_date=date(2009, 9, 1),
        sector=SOLAR_RENEWABLE_ENERGY,
        industry=SOLAR_RENEWABLE_ENERGY,
        aegis_instrument_id="AEGIS-IN-000080",
    ),
    # Electronics Manufacturing (EMS) -- no official NSE index; each
    # individually verified real via a live filing this session (5).
    "DIXON": CuratedInstrumentMetadata(
        isin="INE935N01020",
        company_legal_name="Dixon Technologies (India) Limited",
        security_type="EQUITY",
        listing_date=date(2017, 9, 18),
        sector=ELECTRONICS_MANUFACTURING,
        industry=ELECTRONICS_MANUFACTURING,
        aegis_instrument_id="AEGIS-IN-000081",
    ),
    "KAYNES": CuratedInstrumentMetadata(
        isin="INE918Z01012",
        company_legal_name="Kaynes Technology India Limited",
        security_type="EQUITY",
        listing_date=date(2022, 11, 22),
        sector=ELECTRONICS_MANUFACTURING,
        industry=ELECTRONICS_MANUFACTURING,
        aegis_instrument_id="AEGIS-IN-000082",
    ),
    "AMBER": CuratedInstrumentMetadata(
        isin="INE371P01015",
        company_legal_name="Amber Enterprises India Limited",
        security_type="EQUITY",
        listing_date=date(2018, 1, 30),
        sector=ELECTRONICS_MANUFACTURING,
        industry=ELECTRONICS_MANUFACTURING,
        aegis_instrument_id="AEGIS-IN-000083",
    ),
    "SYRMA": CuratedInstrumentMetadata(
        isin="INE0DYJ01015",
        company_legal_name="Syrma SGS Technology Limited",
        security_type="EQUITY",
        listing_date=date(2022, 8, 26),
        sector=ELECTRONICS_MANUFACTURING,
        industry=ELECTRONICS_MANUFACTURING,
        aegis_instrument_id="AEGIS-IN-000084",
    ),
    "PGEL": CuratedInstrumentMetadata(
        isin="INE457L01029",
        company_legal_name="PG Electroplast Limited",
        security_type="EQUITY",
        listing_date=date(2011, 9, 26),
        sector=ELECTRONICS_MANUFACTURING,
        industry=ELECTRONICS_MANUFACTURING,
        aegis_instrument_id="AEGIS-IN-000085",
    ),
}
