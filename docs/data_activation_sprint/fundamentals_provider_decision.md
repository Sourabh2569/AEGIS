# Fundamentals Provider Decision

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

## What was NOT verified, and is a real, separate action item

**NSE's Terms of Use for automated/bulk access to this public archive have
not been read and confirmed by the founder.** A page being technically
fetchable does not by itself establish that sustained, automated access is
permitted under the site's terms -- this needs the same real verification
already applied to Gate 6 (SEBI's retail algo-trading circular) in
`009_live_readiness_dossier.md`, not an assumption.

Until that review happens:
- `fundamentals_nse_provider_record`'s `ProviderLicense` in `apps/api/aegis_api/main.py`
  stays `PENDING` (`legal_review_status="PENDING_TOS_REVIEW"`).
- `ProviderLicenseGuard.assert_ingestion_allowed()` refuses
  `ProviderIngestionService.ingest_fundamentals()` for real while it's
  `PENDING` -- verified by test
  (`tests/integration/test_fundamentals_ingestion.py::test_ingest_fundamentals_is_blocked_while_license_is_pending`).
- `FUNDAMENTALS_NSE_ENABLED` (`.env`) also defaults `false` -- a second,
  independent off-switch, even though there's no credential to configure
  (the endpoints are public); this keeps the pipeline from running by
  accident before both the flag and the license are real, deliberate
  choices.

**Real action item for the founder**: read NSE's actual Terms of Use /
disclaimer covering its public data archives, and confirm whether sustained
automated access for this kind of research use is permitted, before ever
setting `FUNDAMENTALS_NSE_ENABLED=true` and flipping the license to
`APPROVED`.

## What this pilot deliberately does not cover

- **One company only** (`RELIANCE`, already in `CURATED_INSTRUMENT_METADATA`).
  Proving the pipeline is real and honest end-to-end mattered more than
  coverage for this pass -- see the adapter's module docstring for the exact
  "Known gaps."
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
