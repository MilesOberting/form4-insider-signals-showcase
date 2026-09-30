# Data Ingestion & Live Signal Architecture

## Pipeline

```
SEC EDGAR full-text search (new Form 4 filings, filed today)
        │
        ▼
SEC EDGAR submissions API (per-insider filing history, paginated)
        │
        ▼
SEC EDGAR raw filing XML (parsed for transaction details)
        │
        ▼
Structural filter — keep only open-market purchases
        │
        ▼
Market-cap / listing-age gate (via public market data)
        │
        ▼
Insider historical win-rate gate
        │
        ▼
Signal emitted
        │
        ▼
Trading system (separate, not part of this repo)
```

Every price, market-cap, and benchmark figure used anywhere in this
pipeline — the market-cap/listing-age gate above, the IWM win-rate
comparison below, and the backtesting/research pipeline in
[methodology.md](methodology.md) — comes from **Yahoo Finance** (via the
`yfinance` library), a free public market-data source. There's no separate
paid data vendor and no distinct "test data" set: research and live
filtering both pull from the same public source, and the backtests are
validated by re-running them against fresh data rather than a dedicated CI
harness.

Every SEC insider (an officer, director, or 10%+ owner) must file a **Form 4**
within two business days of buying or selling their own company's stock. This
pipeline watches that filing stream in near-real-time, looking specifically
for **open-market purchases** — an insider using their own money to buy shares
on the open market, as opposed to option exercises, awards, or other
transaction types that don't reflect a discretionary bet.

For every qualifying purchase, the pipeline looks up that specific insider's
**own filing history**: every open-market purchase they've made before, and
what happened to the stock 30 days after each one. That historical track
record is the core signal — not the purchase itself, but whether *this
particular insider's past purchases* have tended to be followed by gains.

## Live gating logic

A purchase only counts as a win in an insider's track record if it **beat the
Russell 2000 (via the IWM ETF) over the same 30-day window** — not merely if
it was profitable in absolute terms. In a rising market almost anything looks
like a "win"; requiring outperformance against a small/mid-cap benchmark
strips out the free wins that come from broad market drift and leaves a
cleaner read on whether this insider's buying specifically has been
informative.

Insiders who clear a minimum sample size and a high historical win rate by
this definition trigger a live signal. The exact sample-size and win-rate
thresholds are intentionally not published here — they're part of what makes
the filter useful.

## Deployment

The service runs as a small, always-on web application with a background
poller that checks EDGAR on a fixed interval during market hours. It exposes
a lightweight signal feed so the emitted signals — and a running log of every
signal ever emitted — are queryable at any time. That log is the data source
for the [performance analysis](performance.md) in this repo.

## How signals reach the trading system

An automated trading system — a separate project, not part of this repo —
consumes this feed and actually places orders. The transport between them is
deliberately simple:

- The "current signal" feed is plain CSV over HTTPS, polled by the trading
  system on a short, fixed interval during market hours.
- It behaves as a **single-slot mailbox, not a queue**: each new signal
  overwrites whatever was there before. The full history isn't lost, though —
  every signal is separately appended to a running log first, and that log is
  exactly what this repo's [performance analysis](performance.md) is built
  from.
- There's currently no authentication layer beyond HTTPS on this transport.
  That's a known, deliberate simplicity tradeoff for a small personal system,
  not a design recommendation — a good reason the exact endpoints aren't
  published here.

## A separate positions/portfolio service

The trading system also depends on a second small service — also separate
from this repo, with its own codebase not covered here — that reports which
positions the trading system currently holds. The trading system polls it to
avoid re-buying a ticker it already owns, and to know when a position has
been held long enough that it should be automatically exited. Beyond that
role in the overall system, this repo doesn't document that service's
internals.

## Engineering rigor

A few real bugs were caught and fixed during development, each worth
mentioning because they're the kind of thing that fails silently:

- **A URL-construction bug** in the historical-filing lookup meant every
  attempt to fetch an insider's past Form 4 filings 404'd — silently, with no
  error — so for a period, every insider's win-rate history looked empty. A
  data-completeness check (an insider's track record should almost never be
  fully empty at scale) surfaced the gap.
- **A transaction-type filter gap** let option exercises and stock awards
  slip into what was supposed to be a purely open-market-purchase history,
  quietly contaminating win-rate calculations with transactions that don't
  represent a real discretionary buy decision.
- **A pagination bug** meant only the ~40 most recent filings per insider were
  ever considered; prolific filers with longer histories had their older
  purchases silently truncated from their own track record.

All three are fixed in the current pipeline. They're listed here because a
research pipeline that quietly produces wrong numbers is worse than one that
errors loudly, and catching these required building explicit data-sanity
checks rather than trusting that "no exception was raised" meant "the data is
right."
