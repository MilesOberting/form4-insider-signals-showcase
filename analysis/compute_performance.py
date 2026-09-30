"""
Compute live signal-service performance vs. the Russell 2000 (IWM).

Reads the live service's public signal feed (timestamp, ticker, action, and
- once the schema added them - score, entry price) and reconstructs a 30-day
forward return per signal using the market close on the signal date as entry
price (not the filing's own reported price - see the note in
compute_signal_returns for why), benchmarked against IWM's return over the
identical window. Produces two aggregated artifacts:

  - summary_stats.csv   overall + monthly win rate / return / alpha
  - performance_chart.png   cumulative "took every signal" vs IWM buy-and-hold

No row-level signal data is written out - only the aggregates above.
"""

import argparse
from datetime import timedelta

import matplotlib
import pandas as pd
import requests
import yfinance as yf

matplotlib.use("Agg")
import matplotlib.pyplot as plt

DEFAULT_SIGNAL_LOG_URL = "https://qtester-production.up.railway.app/signal_log.csv"
BENCHMARK_TICKER = "IWM"
FORWARD_DAYS = 30
COLUMNS_4 = ["timestamp", "ticker", "action", "model"]
COLUMNS_6 = COLUMNS_4 + ["score", "insider_price"]


def load_signal_log(url: str | None, path: str | None) -> pd.DataFrame:
    if path:
        with open(path) as f:
            text = f.read()
    else:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        text = resp.text

    rows = []
    for line in text.strip().splitlines()[1:]:
        parts = line.split(",")
        row = dict(zip(COLUMNS_6, parts))
        rows.append(row)

    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["entry_date"] = df["timestamp"].dt.normalize()
    df["insider_price"] = pd.to_numeric(df.get("insider_price"), errors="coerce")
    df = df[df["action"] == "BUY"].reset_index(drop=True)
    return df


def fetch_price_histories(tickers: list[str], start, end) -> dict[str, pd.Series]:
    # auto_adjust=True: both entry and exit price for a signal always come
    # from this same series (never from the filing's own reported price -
    # see the note in compute_signal_returns), so a split-adjusted close is
    # the correct choice here - it makes a stock split *within* a signal's
    # 30-day holding window a non-event instead of a fake gain/loss, which
    # matters for the small/micro-cap names this dataset skews toward.
    data = yf.download(
        tickers,
        start=start - timedelta(days=5),
        end=end + timedelta(days=5),
        group_by="ticker",
        auto_adjust=True,
        threads=True,
        progress=False,
    )
    histories = {}
    for ticker in tickers:
        try:
            closes = data[ticker]["Close"].dropna()
        except (KeyError, TypeError):
            closes = data["Close"].dropna() if len(tickers) == 1 else pd.Series(dtype=float)
        if not closes.empty:
            histories[ticker] = closes
    return histories


def price_on_or_after(series: pd.Series, date) -> float | None:
    idx = series.index[series.index >= date]
    if len(idx) == 0:
        return None
    return float(series.loc[idx[0]])


def compute_signal_returns(df: pd.DataFrame, price_hist: dict, iwm: pd.Series, as_of) -> pd.DataFrame:
    records = []
    for _, row in df.iterrows():
        ticker = row["ticker"]
        entry_date = row["entry_date"]
        forward_date = entry_date + timedelta(days=FORWARD_DAYS)

        if forward_date > as_of:
            records.append({**row, "status": "too_recent_to_score"})
            continue

        # Entry price is always the market close on the signal date, not the
        # filing's own `insider_price`. For a handful of foreign-listed
        # issuers (e.g. Argentine ADRs) the filing reports the transaction in
        # a different share unit/currency than the US-listed ticker trades
        # in, which silently produces 10-25x "returns" if mixed with a
        # market close on exit. Using the same market-close basis for both
        # entry and exit avoids that mismatch entirely.
        series = price_hist.get(ticker)
        if series is None:
            records.append({**row, "status": "no_price_data"})
            continue
        entry_price = price_on_or_after(series, entry_date)
        if entry_price is None:
            records.append({**row, "status": "no_price_data"})
            continue

        exit_price = price_on_or_after(series, forward_date)
        if exit_price is None:
            records.append({**row, "status": "no_price_data"})
            continue

        iwm_entry = price_on_or_after(iwm, entry_date)
        iwm_exit = price_on_or_after(iwm, forward_date)
        if iwm_entry is None or iwm_exit is None:
            records.append({**row, "status": "no_benchmark_data"})
            continue

        signal_return = exit_price / entry_price - 1.0
        iwm_return = iwm_exit / iwm_entry - 1.0

        records.append(
            {
                **row,
                "status": "scored",
                "entry_price": entry_price,
                "exit_price": exit_price,
                "return_30d": signal_return,
                "iwm_return_30d": iwm_return,
                "alpha_30d": signal_return - iwm_return,
                "beat_iwm": signal_return > iwm_return,
            }
        )
    return pd.DataFrame(records)


def summarize(scored: pd.DataFrame) -> pd.DataFrame:
    overall = {
        "period": "overall",
        "signal_count": len(scored),
        "win_rate_vs_iwm": scored["beat_iwm"].mean(),
        "mean_return_30d": scored["return_30d"].mean(),
        "median_return_30d": scored["return_30d"].median(),
        "mean_iwm_return_30d": scored["iwm_return_30d"].mean(),
        "mean_alpha_30d": scored["alpha_30d"].mean(),
    }

    monthly = scored.copy()
    monthly["period"] = monthly["entry_date"].dt.to_period("M").astype(str)
    monthly_summary = (
        monthly.groupby("period")
        .agg(
            signal_count=("return_30d", "count"),
            win_rate_vs_iwm=("beat_iwm", "mean"),
            mean_return_30d=("return_30d", "mean"),
            mean_iwm_return_30d=("iwm_return_30d", "mean"),
            mean_alpha_30d=("alpha_30d", "mean"),
        )
        .reset_index()
    )

    return pd.concat([pd.DataFrame([overall]), monthly_summary], ignore_index=True)


def build_chart(scored: pd.DataFrame, iwm: pd.Series, out_path: str, burn_in: int = 10) -> None:
    """
    Two lines, both indexed to 100 at the entry date of the first plotted
    signal:
      - "Live signals (equal-weight, non-compounding)": the expanding mean of
        each signal's own realized 30d return, applied to a 100-start index.
        This assumes equal capital per signal and does not compound trade to
        trade - it tracks average signal performance over time, not a
        simulated brokerage account.
      - IWM buy-and-hold over the identical calendar span.

    The first `burn_in` scored signals are used to seed the expanding mean
    but excluded from the plot itself: an average over only 1-2 samples is
    dominated by whichever trade happened to come first, producing a sharp,
    meaningless spike/dip at the very start of the line. Full-sample stats
    in summary_stats.csv are unaffected by this - it only trims the chart.
    """
    ordered = scored.sort_values("entry_date").reset_index(drop=True)
    ordered["cum_avg_return"] = ordered["return_30d"].expanding().mean()
    plotted = ordered.iloc[burn_in:].copy()
    rebase = 1 + plotted["cum_avg_return"].iloc[0]
    signal_index = 100 * (1 + plotted["cum_avg_return"]) / rebase

    start_date = plotted["entry_date"].iloc[0]
    iwm_window = iwm[iwm.index >= start_date]
    iwm_index = 100 * (iwm_window / iwm_window.iloc[0])

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(plotted["entry_date"], signal_index, label="Live signals (equal-weight, non-compounding)", linewidth=2)
    ax.plot(iwm_index.index, iwm_index.values, label="IWM buy-and-hold", linewidth=2)
    ax.set_title("Live Form 4 Signal Performance vs. Russell 2000 (IWM)")
    ax.set_ylabel("Index (100 = start)")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signal-log-url", default=DEFAULT_SIGNAL_LOG_URL)
    parser.add_argument("--signal-log-file", default=None, help="local CSV override, skips the network fetch")
    parser.add_argument("--out-stats", default="analysis/summary_stats.csv")
    parser.add_argument("--out-chart", default="assets/performance_chart.png")
    args = parser.parse_args()

    df = load_signal_log(args.signal_log_url if not args.signal_log_file else None, args.signal_log_file)
    as_of = pd.Timestamp.now().normalize()

    tickers = sorted(df["ticker"].unique())
    price_hist = fetch_price_histories(tickers, df["entry_date"].min(), df["entry_date"].max())
    iwm_hist = fetch_price_histories([BENCHMARK_TICKER], df["entry_date"].min(), as_of)[BENCHMARK_TICKER]

    results = compute_signal_returns(df, price_hist, iwm_hist, as_of)
    scored = results[results["status"] == "scored"].copy()

    print(f"{len(df)} total BUY signals, {len(scored)} scored (30d window elapsed + price data available)")
    print(results["status"].value_counts())

    summary = summarize(scored)
    summary.to_csv(args.out_stats, index=False)
    print(f"Wrote {args.out_stats}")

    build_chart(scored, iwm_hist, args.out_chart)
    print(f"Wrote {args.out_chart}")


if __name__ == "__main__":
    main()
