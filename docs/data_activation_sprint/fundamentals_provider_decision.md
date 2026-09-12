# Fundamentals Provider Decision

**Status: reviewed 2026-09-12. NSE's Terms of Use prohibit this, so the
provider's real license is `REJECTED`, not `PENDING`. This pipeline must
not be pointed at NSE for real, sustained use.**

NSE's Terms of Use (`https://www.nseindia.com/static/nse-terms-of-use`,
read in full this session) state, verbatim:

> "User is prohibited to conduct any systematic or automated data
> collection activities (including scraping, data mining, data extraction
> and data harvesting) on or in relation to our Website / Mobile
> Application."

The same page also restricts reuse of downloaded content more broadly
("shall not be copied, modified, reverse engineer, reproduced, uploaded,
transmitted, posted, stored ... without prior written permission of NSE").
This is unambiguous and directly on point -- the adapter's real HTTP calls
to NSE's discovery API and XBRL archive are exactly the kind of automated
collection this clause names. Technical feasibility (confirmed real and
working, see below) does not establish permission; the terms say no.

**What this means concretely**: both `fundamentals_nse_provider.py`'s
default `ProviderLicense` and the one registered in `apps/api/aegis_api/main.py`
are now `ProviderLicenseStatus.REJECTED` (was `PENDING`).
`ProviderLicenseGuard.assert_ingestion_allowed()` refuses
`ProviderIngestionService.ingest_fundamentals()` unconditionally as a
result -- this is a real, structural, permanent block, not a "review later"
placeholder. The parsing/adapter code itself stays in the repo, tested and
working, as a reference for a genuinely licensed source in the future --
but it must never be pointed at NSE's real endpoints for sustained use.

**A real compliant path, if this is worth pursuing further**: NSE does sell
historical/bulk market data commercially (contact `marketdata@nse.co.in`,
per NSE's own EOD/historical-data subscription page) -- but that channel is
documented for EOD price/order/trade data (bhavcopy), not corporate-filings
fundamentals specifically, and using it would mean a real commercial
license agreement, not a config flag. Whether NSE (or another vendor) sells
a licensed fundamentals/XBRL feed at all wasn't checked -- that's real,
separate research for the founder to decide is worth pursuing, not
something to build against speculatively.

---

AEGIS's `fundamentals_nse` adapter
(`packages/provider_adapters/aegis/provider_adapters/fundamentals_nse_provider.py`)
implements the `MarketDataProvider` protocol's `fetch_fundamentals()` for real,
against NSE's own public corporate-filings XBRL archive. Every prior adapter
(Kite Connect, mock, CSV, live-readonly) had this method declared but only as
an honest empty "unsupported" stub -- this is the first real implementation.

## Why NSE's public archive, not a paid vendor or Screener.in

The originating brief (`aegis_sector_screener_decision_engine.md`) explicitly
ruled out Screener.in ("data isn't reusable programmatically -- ToS") and
specified building on AEGIS's "own pipeline (filings/XBRL/MCA)". Before
committing engineering time to that direction, its feasibility was actually
tested this session, not assumed:

- `GET https://www.nseindia.com/api/corporates-financial-results?index=equities&period=Quarterly&symbol=RELIANCE`
  is a real, public, unauthenticated JSON API returning real per-company
  filing metadata (company name, ISIN, period, filing date) with a direct
  link to that filing's XBRL instance document. Confirmed reachable via a
  plain `curl` with only a standard browser User-Agent header -- no session
  cookies, no login, no bot-challenge encountered.
- The linked document (e.g.
  `https://nsearchives.nseindia.com/corporate/xbrl/INDAS_117298_1348254_16012025082021.xml`)
  is a real, valid, publicly downloadable XBRL instance document. Downloaded
  and inspected directly -- real tagged financial facts (`RevenueFromOperations`,
  `ProfitLossForPeriod`, etc.) with real XBRL `<xbrli:context>` period scoping.
- A captured real filing (Reliance Industries, standalone, Q3 FY2024-25) is
  checked into `tests/fixtures/xbrl/reliance_q3_fy2025_standalone.xml` and is
  what the adapter's tests parse against -- CI never depends on NSE being
  reachable.

This is meaningfully better-grounded than assuming XBRL scraping would be
blocked (an initial automated fetch attempt via a non-browser tool did time
out, which could have been mistaken for proof of blocking) or defaulting to
a paid vendor without first checking the free, public, regulatory-disclosure
path the brief itself preferred.

## The ToS review, and why this stays blocked regardless of the enable flag

This is the same real verification already applied to Gate 6 (SEBI's
retail algo-trading circular) in `009_live_readiness_dossier.md` --
technical feasibility was confirmed real, and then the terms governing
that access were actually read, not assumed. The answer here is negative,
unlike Gate 6.

- `fundamentals_nse_provider_record`'s `ProviderLicense` in
  `apps/api/aegis_api/main.py` is now `REJECTED`
  (`legal_review_status="REJECTED_TOS_PROHIBITS_AUTOMATION"`).
- `ProviderLicenseGuard.assert_ingestion_allowed()` refuses
  `ProviderIngestionService.ingest_fundamentals()` unconditionally as a
  result -- verified by test
  (`tests/integration/test_fundamentals_ingestion.py::test_ingest_fundamentals_is_blocked_because_nse_tos_rejects_automation`).
- `FUNDAMENTALS_NSE_ENABLED` (`.env`) still defaults `false` too, but note
  this is now academic: even setting it `true` cannot make real ingestion
  succeed, since `REJECTED` is a hard block in `ProviderLicenseGuard`
  regardless of that flag. The flag was originally meant as an interim
  off-switch pending review; the review is done, and its answer stands
  independently of it now.

## Update: scaled from one company to one real sector (Information Technology)

The initial pilot covered `RELIANCE` only. Scaling it up surfaced a real,
important finding: **fundamentals filings are not one uniform format across
sectors.** A real HDFCBANK filing was fetched and inspected -- banks file
under a materially different XBRL taxonomy (`BANKING_*.xml`, tags like
`InterestEarned`/`ProfitLossForThePeriod`) than the generic Ind-AS taxonomy
(`INDAS_*.xml`, `RevenueFromOperations`/`ProfitBeforeTax`/
`ProfitLossForPeriod`) Reliance's filing uses. "Financial Services" is
AEGIS's largest real sector (11 companies: banks, NBFCs, insurers) but
would need separate, real tag-mapping work per sub-industry to support
honestly -- not attempted in this pass.

**Information Technology was chosen instead**: 5 real companies already in
`CURATED_INSTRUMENT_METADATA` (TCS, HCLTECH, INFY, TECHM, WIPRO), confirmed
homogeneous -- every one of them files under the same generic Ind-AS
taxonomy as Reliance. Verified by fetching all 5 real Q3 FY2024-25
standalone filings live and confirming the existing parser (unchanged)
correctly extracts real, plausible revenue/profit figures from each --
checked into `tests/fixtures/xbrl/` alongside the original Reliance one and
exercised by `test_fetch_fundamentals_across_a_real_multi_company_sector`.

Two real adapter changes came out of scaling past one company:
- **Per-company failure isolation**: one company's fetch failing (network
  error, malformed response) no longer aborts the whole batch -- the real
  reason is recorded per-symbol in `skipped_symbols` instead.
- **Real request throttling**: a real minimum interval between HTTP
  requests (`min_request_interval_seconds`, default 1s), mirroring
  `kite_connect_provider.py`'s identical pattern -- basic politeness toward
  a public archive that wasn't built for bulk automated traffic, now that
  this fetches ~12 real requests instead of 2.

`FUNDAMENTALS_PILOT_SECTOR`/`FUNDAMENTALS_PILOT_SYMBOLS` in
`apps/api/aegis_api/main.py` derive the symbol list from the same real,
NSE-verified `CURATED_INSTRUMENT_METADATA` sector data already used
elsewhere (`sector_by_instrument_id`) -- not a separately maintained list.

## What this pilot deliberately does not cover

- **One sector only** (Information Technology, 5 companies). Financial
  Services, and every other sector, needs its own real tag-mapping
  verification before being added -- see "Known gaps" in the adapter's
  module docstring.
- **Only quarterly results, standalone, P&L-shaped fields** (revenue, profit
  before tax, profit for the period). No balance sheet (total assets, total
  equity) -- those live in a different filing type (annual report XBRL),
  not read here.
- **No fundamentals-specific data-quality validation** (the equivalent of
  `validate_eod_ohlcv` for price data) exists yet -- `ingest_fundamentals()`
  captures a real, hashed, provenance-tagged payload but doesn't yet check
  the fundamentals-domain-specific correctness rules a real quality gate
  would need. Real future work, not attempted here.
- **No sector-wide screener, no qualitative/event scoring layer, no
  composite Decision Engine, no systematic-deployment staging** -- all
  explicitly out of scope until real fundamentals data exists for more than
  one company, per the brief's own Section 5.
