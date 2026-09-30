# Form 4 Insider-Signal Pipeline

An automated pipeline that watches SEC Form 4 filings for insider open-market
purchases, filters them by the filing insider's own historical track record,
and surfaces the ones worth paying attention to via a small live service.

This repo showcases the **general architecture, data pipeline, and research
methodology** behind that service, plus **real performance data** for the
live service since launch. It's intentionally general — the specific filter
thresholds, scoring weights, and model parameters that make the strategy work
are not included.

## Headline result

Since launch (2026-02-17), the live service's signals have beaten the Russell
2000 (IWM) on a matched 30-day-return basis **57.6% of the time**, with a
mean per-signal return of **+3.5%** vs. IWM's **+0.9%** over the same windows
— computed independently from 569 scored live signals, not a backtest
projection. See [`docs/performance.md`](docs/performance.md) for the full
writeup, methodology, and limitations.

**Scope note:** this measures the raw signal itself — take every emitted
signal, equal-weighted, hold 30 days, don't compound. It is not a
reconstruction of any real trading account, which would also involve
position sizing, compounding, and (in this case) an entirely separate
strategy this repo doesn't cover at all. It's a measure of signal quality,
not account P&L.

## Read more

- [**Architecture**](docs/architecture.md) — how filings are ingested, parsed,
  and filtered into a live signal, the deployment shape of the service, and
  how the signal reaches the downstream trading system.
- [**Methodology**](docs/methodology.md) — the research/training pipeline
  behind the live rule: data, feature engineering, model, backtesting, and a
  research-integrity note about a bug that was caught and fixed.
- [**Performance**](docs/performance.md) — the full live performance
  write-up vs. the Russell 2000, with a chart and stated limitations.

## What this repo does NOT include

- The exact filter thresholds, scoring weights, or model hyperparameters —
  these are the tuned, proprietary part of the strategy.
- Raw signal logs or transaction-level data — only aggregated, derived
  results are published (see [`analysis/summary_stats.csv`](analysis/summary_stats.csv)).
- The trading system's own logic (position sizing, order execution, exits) or
  its unrelated second strategy — only how it *receives* signals is described,
  generally, in [architecture.md](docs/architecture.md).
- Any live service endpoints/URLs — the transport mechanism is described,
  but the actual addresses are withheld since those endpoints currently have
  no authentication layer.

## Repo contents

```
docs/                    architecture, methodology, and performance write-ups
assets/performance_chart.png   live-signal vs. IWM cumulative performance chart
analysis/compute_performance.py   re-runnable script that produces the above
analysis/summary_stats.csv        the aggregated output of that script
```

`compute_performance.py` doesn't hardcode the live service's real endpoint
(see the note above on withheld URLs). Point it at a signal-log CSV yourself
to reproduce the analysis:

```bash
python3 analysis/compute_performance.py --signal-log-url <your-signal-log-url>
# or, against a local file:
python3 analysis/compute_performance.py --signal-log-file path/to/signal_log.csv
```

## License

MIT — see [LICENSE](LICENSE).
