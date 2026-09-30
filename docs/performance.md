# Live Performance vs. the Russell 2000

**These are real results from the live signal service since launch,
independently computed from the service's own public signal history — not a
backtest projection.** See [methodology.md](methodology.md) for how that
differs from the offline research numbers.

**What this measures, precisely:** the raw signal itself, not any real
trading account. It's "take every emitted signal, weight them equally, hold
each for exactly 30 days, don't compound." The trading system that actually
acts on this feed does more than that — real position sizing, compounding,
and (per [architecture.md](architecture.md)) an entirely separate second
strategy unrelated to Form 4 signals — so a real account's overall
performance is expected to diverge from this number, in either direction. This
page is a measure of signal quality, not a substitute for account P&L.

## Summary

| Metric | Value |
|---|---|
| Live signal history | 2026-02-17 – present |
| Total signals emitted | 636 |
| Signals scored (30-day window elapsed) | 569 |
| Win rate vs. IWM (30d) | **57.6%** |
| Mean 30-day return per signal | **+3.5%** |
| Median 30-day return per signal | +2.6% |
| Mean IWM 30-day return over the same windows | +0.9% |
| Mean alpha vs. IWM per signal | **+2.6pp** |

(These figures shift slightly each time the analysis is re-run, since more
signals cross the 30-day scoring threshold every day — see
[`analysis/summary_stats.csv`](../analysis/summary_stats.csv) for the
current numbers.)

"Win" is defined the same way the live service's own gate defines it: a
signal beats IWM over the identical 30-day window, not merely a positive
absolute return.

## Cumulative performance

![Live signals vs IWM](../assets/performance_chart.png)

Two lines, both indexed to 100 and both ending on the same date:
- **Live signals** — the expanding average return across every scored signal
  to date, equal-weighted and non-compounding. This tracks *average signal
  quality over time*, not a simulated brokerage account.
- **IWM buy-and-hold** — simply holding the Russell 2000 ETF over the
  identical calendar span.

The chart intentionally stops about a month before today: any signal from the
last 30 days doesn't have a resolved 30-day return yet, so it isn't part of
the scored comparison, and extending the benchmark line past that point would
show it running through a stretch with no corresponding signal data to
compare it against.

Because the Russell 2000 held a strong rally for much of the summer, IWM's
buy-and-hold line pulled ahead of the signal-quality line in cumulative terms
even though the per-trade win rate and alpha stayed positive throughout — a
reminder that a positive per-trade edge doesn't automatically translate into
beating a rising benchmark's raw beta exposure over any given stretch.

## Limitations

- **Short live history.** ~7 months and 569 scored signals is enough to see a
  real, positive per-trade edge, but not enough to rule out a lucky stretch.
- **Signal-definition changes.** The live service's exact signal-emission
  logic changed more than once during this window (see
  [architecture.md](architecture.md)); early signals in this history don't
  reflect the current rule exactly.
- **Simplified trade simulation.** Every signal is treated as an equal-size,
  non-compounding, independent 30-day position. Real execution would involve
  overlapping capital constraints, slippage, and liquidity limits not modeled
  here.
- **Entry price basis.** Entry price is the market close on the day the
  signal was emitted, not the insider's own historical execution price — the
  filing's reported price turned out to be an unreliable basis for a handful
  of foreign-listed issuers (unit/currency mismatches between the filing and
  the US-listed ticker), so a consistent market-close basis is used for every
  signal instead.
- **Survivorship.** Price data is sourced from a live market-data provider,
  which can silently exclude delisted tickers from history — a real but
  typically small upward bias in aggregate results.

The analysis script that produced these numbers is in
[`analysis/compute_performance.py`](../analysis/compute_performance.py) and
can be re-run at any time against the live signal feed.
