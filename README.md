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

## Read more

- [**Architecture**](docs/architecture.md) — how filings are ingested, parsed,
  and filtered into a live signal, and the deployment shape of the service.
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
- The order-execution/trading system that consumes these signals — this repo
  covers signal generation and research only.

## Repo contents

```
docs/                    architecture, methodology, and performance write-ups
assets/performance_chart.png   live-signal vs. IWM cumulative performance chart
analysis/compute_performance.py   re-runnable script that produces the above from
                                    the live service's public signal feed
analysis/summary_stats.csv        the aggregated output of that script
```

## License

MIT — see [LICENSE](LICENSE).
