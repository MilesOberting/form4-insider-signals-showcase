"""
Compute live signal-service performance vs. the Russell 2000 (IWM).

Reads the live service's public signal feed (timestamp, ticker, action, and
- once the schema added them - score, entry price) and reconstructs a 30-day
forward return per signal using the market close on the signal date as entry
price (not the filing's own reported price - see the note in
compute_signal_returns for why), benchmarked against IWM's return over the
identical window. Produces two aggregated artifacts:

  - summary_stats.csv   overall + monthly win rate / return / alpha
  - performance_chart.png   daily mark-to-market equity curve vs. IWM at the
    same entry dates (see build_chart)

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
                "iwm_entry_price": iwm_entry,
                "return_30d": signal_return,
                "iwm_return_30d": iwm_return,
                "alpha_30d": signal_return - iwm_return,
                "beat_iwm": signal_return > iwm_return,
            }
        )
    return pd.DataFrame(records)


def summarize(scored: pd.DataFrame, cumulative_return: float = None, cumulative_iwm_return: float = None) -> pd.DataFrame:
    overall = {
        "period": "overall",
        "signal_count": len(scored),
        "win_rate_vs_iwm": scored["beat_iwm"].mean(),
        "mean_return_30d": scored["return_30d"].mean(),
        "median_return_30d": scored["return_30d"].median(),
        "mean_iwm_return_30d": scored["iwm_return_30d"].mean(),
        "mean_alpha_30d": scored["alpha_30d"].mean(),
        "cumulative_return": cumulative_return,
        "cumulative_iwm_return": cumulative_iwm_return,
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


def peak_concurrent_notional(legs: list[tuple], date_index: pd.DatetimeIndex) -> float:
    """
    The smallest capital base that could actually run this exact sequence of
    trades at once, at any point in time - i.e. real, reused capital, not a
    pool large enough to take every trade simultaneously without ever
    freeing any of it up.
    """
    committed = pd.Series(0.0, index=date_index)
    for entry_date, exit_date, notional, _, _ in legs:
        window = date_index[(date_index >= entry_date) & (date_index <= exit_date)]
        committed.loc[window] += notional
    return float(committed.max())


def build_daily_index(
    legs: list[tuple],  # (entry_date, exit_date, notional, entry_price, price_series)
    total_notional: float,
    date_index: pd.DatetimeIndex,
) -> pd.Series:
    """
    Daily mark-to-market equity curve, 100 = fully in cash, with real
    capital reuse: opening a position debits its notional from cash; every
    open position is marked to market daily; when a position's exit date
    arrives, its CURRENT mark-to-market value - not its original notional -
    is credited back to cash, so a realized gain or loss actually changes
    how much capital is available for the next trade. An earlier version
    returned only the original notional to cash on exit, which silently
    discarded every closed trade's P&L from the running total and made the
    chart converge on the simple average return instead of the real
    compounding effect of reusing the same capital many times over.
    """
    series_cache: dict[int, pd.Series] = {}

    def reindexed(series: pd.Series) -> pd.Series:
        key = id(series)
        if key not in series_cache:
            series_cache[key] = series.reindex(date_index).ffill()
        return series_cache[key]

    entries_by_date: dict = {}
    for leg in legs:
        entries_by_date.setdefault(leg[0], []).append(leg)

    cash = total_notional
    open_positions = []
    index_values = []
    for day in date_index:
        for entry_date, exit_date, notional, entry_price, series in entries_by_date.get(day, []):
            cash -= notional
            open_positions.append(
                {"notional": notional, "entry_price": entry_price, "series": series, "exit_date": exit_date}
            )

        day_value = 0.0
        still_open = []
        for pos in open_positions:
            price = None
            if pos["series"] is not None:
                rs = reindexed(pos["series"])
                if day in rs.index:
                    price = rs.loc[day]
            value = pos["notional"] * (price / pos["entry_price"]) if (price and pos["entry_price"]) else pos["notional"]
            if day >= pos["exit_date"]:
                cash += value
            else:
                day_value += value
                still_open.append(pos)
        open_positions = still_open
        index_values.append(100 * (cash + day_value) / total_notional)

    return pd.Series(index_values, index=date_index)


def build_chart(scored: pd.DataFrame, price_hist: dict, iwm: pd.Series, out_path: str) -> None:
    """
    Two lines, both a daily mark-to-market equity curve with capital reused
    across signals as positions close (see build_daily_index), so the only
    difference between them is which asset each slice of capital is
    invested in while a signal is open:
      - "Live signals": each signal's own ticker, its actual daily price
        path from entry to a 30-day exit.
      - "IWM at the same entry dates": the same capital, same entry dates,
        same 30-day windows, invested in IWM instead. Deliberately not IWM
        buy-and-hold, which would mix in market-timing luck from a single
        start date rather than isolating "same money, same timing, different
        asset."

    The capital base is sized to the peak number of signals ever open at
    once (equal-weighted, so "notional" is just a count here) - the
    smallest base that could have actually run this exact sequence - not
    the total number of signals ever emitted, which would imply capital is
    never reused and understate the real compounding effect.
    """
    legs = [
        (row.entry_date, row.entry_date + timedelta(days=FORWARD_DAYS), 1.0, row.entry_price, price_hist.get(row.ticker))
        for row in scored.itertuples()
    ]
    iwm_legs = [
        (row.entry_date, row.entry_date + timedelta(days=FORWARD_DAYS), 1.0, row.iwm_entry_price, iwm)
        for row in scored.itertuples()
    ]

    start = scored["entry_date"].min()
    end = (scored["entry_date"] + timedelta(days=FORWARD_DAYS)).max()
    date_index = pd.bdate_range(start, end)
    total_notional = peak_concurrent_notional(legs, date_index)

    signal_index = build_daily_index(legs, total_notional, date_index)
    iwm_index = build_daily_index(iwm_legs, total_notional, date_index)

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(date_index, signal_index, label="Live signals (capital reused as it frees up)", linewidth=2)
    ax.plot(date_index, iwm_index, label="IWM at the same entry dates", linewidth=2)
    ax.set_title("Live Form 4 Signal Performance vs. IWM, Matched by Entry Date")
    ax.set_ylabel("Index (100 = start)")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)

    return signal_index.iloc[-1] / 100 - 1, iwm_index.iloc[-1] / 100 - 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--signal-log-url",
        default=None,
        help="URL of the live service's signal_log.csv endpoint (no default - "
        "this repo doesn't publish the real one; see architecture.md)",
    )
    parser.add_argument("--signal-log-file", default=None, help="local CSV override, skips the network fetch")
    parser.add_argument("--out-stats", default="analysis/summary_stats.csv")
    parser.add_argument("--out-chart", default="assets/performance_chart.png")
    args = parser.parse_args()

    if not args.signal_log_url and not args.signal_log_file:
        parser.error("pass --signal-log-url or --signal-log-file")

    df = load_signal_log(args.signal_log_url if not args.signal_log_file else None, args.signal_log_file)
    as_of = pd.Timestamp.now().normalize()

    tickers = sorted(df["ticker"].unique())
    price_hist = fetch_price_histories(tickers, df["entry_date"].min(), df["entry_date"].max())
    iwm_hist = fetch_price_histories([BENCHMARK_TICKER], df["entry_date"].min(), as_of)[BENCHMARK_TICKER]

    results = compute_signal_returns(df, price_hist, iwm_hist, as_of)
    scored = results[results["status"] == "scored"].copy()

    print(f"{len(df)} total BUY signals, {len(scored)} scored (30d window elapsed + price data available)")
    print(results["status"].value_counts())

    cumulative_return, cumulative_iwm_return = build_chart(scored, price_hist, iwm_hist, args.out_chart)
    print(f"Wrote {args.out_chart}")
    print(f"Cumulative return (capital reused): {cumulative_return:.1%} vs IWM {cumulative_iwm_return:.1%}")

    summary = summarize(scored, cumulative_return, cumulative_iwm_return)
    summary.to_csv(args.out_stats, index=False)
    print(f"Wrote {args.out_stats}")


if __name__ == "__main__":
    main()
