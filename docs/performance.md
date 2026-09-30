# Live Performance vs. the Russell 2000

This page has two comparisons. The first — **real executed trades** — is the
one that matters: what actually happened, sized and timed exactly as it
really was, compared to buying IWM at those same times and sizes. The second
— **raw signal quality** — measures the pre-filter signal feed itself, before
any of the real trading system's execution constraints are applied. They're
kept separate on purpose: the raw feed emits far more signals than ever
become real trades, and blending the two would overstate what the live
system actually does. See [methodology.md](methodology.md) for how both of
these differ from the offline research/backtest numbers.

## Real executed trades

Reconstructed from the trading system's own real fills — real entry dates,
real exit dates, real position sizes — filtered to trades the system placed
specifically because of a Form 4 signal (its unrelated second strategy,
mentioned in [architecture.md](architecture.md), is excluded). Round trips
are completed buy-then-sell pairs; a handful of positions still open as of
this writing aren't included, since they don't have a real exit yet.

| Metric | Value |
|---|---|
| Round trips completed | **116** (out of 636 raw signals emitted — most signals never become a trade; see below) |
| Unique tickers traded | 92 |
| Win rate vs. IWM (same dates) | **57.8%** |
| Cumulative return, capital reused across all 116 trades | **+17.8%** |
| Same, for IWM at the same dates & sizes | +7.4% |
| Dollar-weighted mean return *per trade* | +3.7% |
| Dollar-weighted mean IWM return *per trade* (same dates, same amounts) | +1.5% |

Two different, both-honest numbers: the **cumulative** figure reflects that
the same capital gets reused as positions close and new ones open — 116
times across 92 tickers over ~7 months — so it's the closer match to "how
much did this actually add up to." The **per-trade average** answers a
narrower question (was the typical trade good?) and is naturally smaller,
since it doesn't give credit for capital being reused many times over. The
IWM comparison uses the *same* dollar amount and the *same* entry/exit dates
as the real trade it's matched against either way, so the only variable that
differs is which asset was bought.

![Real trades vs IWM](../assets/real_trades_chart.png)

Both lines are a genuine day-by-day equity curve, not an average of returns:
a capital pool sized to the peak amount ever committed at once (the smallest
base that could actually run this trade sequence) opens a position by
debiting its cost, marks every open position to market daily using its real
price path, and — this is the part that makes it cumulative — credits a
closed position's *actual ending value*, gain or loss included, back to cash
so it's available to fund the next trade. An earlier version of this chart
returned only a closed trade's original cost to cash, which silently
discarded every realized gain from the running total and made the chart
converge on the per-trade average instead of the real compounding effect.
Both lines necessarily start at exactly 100 (before the first trade, the
whole pool is cash) and move smoothly from there.

Only percentage returns are published here. No dollar amounts, account
balances, or individual trade records (tickers, dates, position sizes) are
shown — this reconstruction was built from real brokerage data that isn't
part of this repo and can't be independently re-run without access to that
account.

### Why only 116 of 636 signals became real trades

This is the number that actually matters, and it's a small fraction of the
raw feed. The live trading system applies real constraints the raw signal
feed doesn't: available cash, an aggregate-exposure cap, per-ticker dedup (no
buying something already held), and rejection/ban handling when a broker
declines an order. Most emitted signals don't survive all of that — which is
exactly why the "raw signal quality" numbers below shouldn't be read as "what
the account did."

### How this relates to the account's overall gain

The account runs two strategies (see [architecture.md](architecture.md)):
this one, and an unrelated second strategy trading a completely different
universe of tickers. Comparing realized profit between the two, **this
strategy accounts for roughly 86% of the account's total realized trading
profit** over the same period — it's the dominant driver, not a minor
contributor, which the +17.8% cumulative figure above is now consistent
with (the two won't match exactly — this repo's reconstruction is one
strategy in isolation with its own capital-reuse assumption, not a
full account replica, and it excludes the handful of still-open positions'
unrealized P&L).

## Raw signal quality (for context)

**What this measures, precisely:** the raw signal feed itself, before
execution. It's "take every emitted signal, weight them equally, hold each
for exactly 30 days" — a diagnostic of signal quality, not a reconstruction
of any real trading activity.

| Metric | Value |
|---|---|
| Live signal history | 2026-02-17 – present |
| Total signals emitted | 636 |
| Signals scored (30-day window elapsed) | 569 |
| Peak signals open at once | 163 |
| Win rate vs. IWM (30d) | 57.6% |
| Cumulative return, capital reused across all scored signals | +12.3% |
| Same, for IWM at the same dates | +3.1% |
| Mean return *per signal* | +3.5% |
| Mean IWM return *per signal* (same windows) | +0.9% |

(These figures shift slightly each time the analysis is re-run, since more
signals cross the 30-day scoring threshold every day — see
[`analysis/summary_stats.csv`](../analysis/summary_stats.csv), which has the
per-signal figures; the cumulative figures are only in this doc and the
chart.)

![Live signals vs IWM](../assets/performance_chart.png)

Same day-by-day, capital-reuse method as the real-trades chart above, but
equal-weighted rather than dollar-weighted (there's no real position size to
weight by for a signal that was never traded), and every signal held for a
fixed 30 days rather than a real, variable exit date. The chart stops about a
month before today, since recent signals don't have a resolved 30-day window
yet.

This is close to the real-trades numbers above, which is a reasonable
consistency check, but it isn't the same measurement — see the previous
section for why the executed-trade count is so much smaller than the signal
count.

## Limitations

- **Short history.** ~7 months, 116 real round trips, is enough to see a
  real, positive edge but not enough to rule out a lucky stretch.
- **Signal-definition changes.** The live service's exact signal-emission
  logic changed more than once during this window (see
  [architecture.md](architecture.md)); early signals don't reflect the
  current rule exactly.
- **Entry price basis.** Realized-return figures (the table, and the
  real-trades section's per-trade stats) use the real fill price where one
  exists. The day-by-day *charts* for both sections instead anchor to the
  price-data provider's own close on the entry date, even for real trades —
  a handful of tickers have had a real corporate action (e.g. a reverse
  split) between the trade date and today that the data provider's history
  retroactively restates, which would otherwise silently mismatch a real
  fill price against today's adjusted series and distort the chart. This
  doesn't change the realized-return table, only how the chart is drawn.
- **Survivorship.** Price data (both sections) is sourced from a public
  market-data provider, which can silently exclude delisted tickers from
  history — a real but typically small upward bias.
- **Still-open positions excluded.** A handful of real positions were still
  held as of this writing and aren't in the round-trip count, since they
  don't have a real exit yet.

The raw-signal analysis script is in
[`analysis/compute_performance.py`](../analysis/compute_performance.py) and
is re-runnable by anyone against the live public signal feed. The
real-trades reconstruction depends on private brokerage account access and
isn't published as a script for that reason — the numbers above are the full
output of that analysis.
