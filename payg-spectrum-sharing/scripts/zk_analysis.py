#!/usr/bin/env python3
"""
Quick analysis script for zk smoke/scenario runs.

Reads a CSV (default: data/results/zk_scenarios.csv) and emits:
- Summary stats to stdout (mean/median/p90/p99 for prove/verify ms, proof size).
- PNG plots saved to figures/ (histograms and scatter).

Usage:
    source ../spec-venv/bin/activate
    python scripts/zk_analysis.py --input data/results/zk_scenarios.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import csv
import statistics
from typing import Dict, List

try:
    import matplotlib.pyplot as plt
except ImportError:
    plt = None

try:
    import pandas as pd
except ImportError:
    pd = None


def summarize_pandas(df: pd.DataFrame) -> pd.DataFrame:
    metrics = ["prove_ms", "verify_ms", "proof_size_bytes"]
    quantiles = df[metrics].quantile([0.5, 0.9, 0.99]).rename(
        {0.5: "p50", 0.9: "p90", 0.99: "p99"}
    )
    basics = df[metrics].agg(["mean", "std", "min", "max"])
    summary = pd.concat([basics, quantiles])
    return summary


def summarize_lists(rows: List[Dict[str, float]]) -> Dict[str, Dict[str, float]]:
    metrics = ["prove_ms", "verify_ms", "proof_size_bytes"]
    out: Dict[str, Dict[str, float]] = {}
    for m in metrics:
        vals = [float(r[m]) for r in rows if m in r]
        if not vals:
            continue
        out[m] = {
            "mean": statistics.fmean(vals),
            "std": statistics.pstdev(vals) if len(vals) > 1 else 0.0,
            "min": min(vals),
            "max": max(vals),
            "p50": statistics.quantiles(vals, n=100)[49],
            "p90": statistics.quantiles(vals, n=10)[8],
            "p99": statistics.quantiles(vals, n=100)[98],
        }
    return out


def mean_first_n_pandas(df: "pd.DataFrame", n: int = 100) -> Dict[str, float]:
    subset = df.head(n)
    return {
        "issue_a_ms": subset["issue_a_ms"].mean(),
        "issue_b_ms": subset["issue_b_ms"].mean(),
        "prove_ms": subset["prove_ms"].mean(),
        "verify_ms": subset["verify_ms"].mean(),
    }


def mean_first_n_lists(rows: List[Dict[str, float]], n: int = 100) -> Dict[str, float]:
    subset = rows[:n]
    def avg(key: str) -> float:
        vals = [float(r[key]) for r in subset if key in r]
        return statistics.fmean(vals) if vals else 0.0
    return {
        "issue_a_ms": avg("issue_a_ms"),
        "issue_b_ms": avg("issue_b_ms"),
        "prove_ms": avg("prove_ms"),
        "verify_ms": avg("verify_ms"),
    }


def save_table_pdf(means: Dict[str, float], out_dir: Path) -> None:
    if plt is None:
        return
    out_dir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6, 1.5))
    ax.axis("off")
    rows = [
        ["Metric", "Mean (ms)"],
        ["issue_a_ms", f"{means['issue_a_ms']:.2f}"],
        ["issue_b_ms", f"{means['issue_b_ms']:.2f}"],
        ["prove_ms", f"{means['prove_ms']:.2f}"],
        ["verify_ms", f"{means['verify_ms']:.2f}"],
    ]
    table = ax.table(cellText=rows, loc="center", cellLoc="center")
    table.scale(1, 1.4)
    out_path = out_dir / "zk_summary_table.pdf"
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


def plot_hist(series, metric: str, out_dir: Path) -> None:
    if plt is None:
        return
    plt.figure(figsize=(6, 4))
    plt.hist(series, bins=20, alpha=0.7)
    plt.xlabel(f"{metric} (ms)" if metric.endswith("_ms") else metric)
    plt.ylabel("count")
    plt.title(f"Distribution of {metric}")
    out_path = out_dir / f"{metric}_hist.png"
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()


def plot_scatter(x_vals, prove_vals, verify_vals, out_dir: Path) -> None:
    if plt is None:
        return
    plt.figure(figsize=(6, 4))
    plt.scatter(x_vals, prove_vals, label="prove_ms", alpha=0.7, marker="o")
    plt.scatter(x_vals, verify_vals, label="verify_ms", alpha=0.7, marker="x")
    plt.xlabel("message_count (vc_b if present)")
    plt.ylabel("ms")
    plt.title("Prove/Verify vs message count")
    plt.legend()
    out_path = out_dir / "prove_verify_vs_messages.png"
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze zk proof metrics CSV.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/results/zk_runs.csv"),
        help="Path to CSV file",
    )
    args = parser.parse_args()

    if not args.input.exists():
        raise SystemExit(f"Input CSV not found: {args.input}")

    expected_cols = {"proof_size_bytes", "prove_ms", "verify_ms"}

    if pd is not None:
        df = pd.read_csv(args.input)
        if not expected_cols.issubset(df.columns):
            raise SystemExit(f"CSV missing required columns: {expected_cols - set(df.columns)}")
        summary = summarize_pandas(df).round(3)
        print("Summary stats (pandas):")
        print(summary)

        means = mean_first_n_pandas(df)
        print("Mean over first 100 (or fewer) rows (ms):", {k: round(v, 3) for k, v in means.items()})

        figures_dir = Path("figures")
        figures_dir.mkdir(parents=True, exist_ok=True)
        plot_hist(df["prove_ms"], "prove_ms", figures_dir)
        plot_hist(df["verify_ms"], "verify_ms", figures_dir)
        plot_hist(df["proof_size_bytes"], "proof_size_bytes", figures_dir)
        x_vals = df["message_count_b"] if "message_count_b" in df.columns else df["message_count_a"]
        plot_scatter(x_vals, df["prove_ms"], df["verify_ms"], figures_dir)
        if plt is None:
            print("Matplotlib not installed; skipped plots.")
        else:
            print(f"Plots saved to {figures_dir}/")
            save_table_pdf(means, figures_dir)
    else:
        # Fallback: minimal CSV parsing without pandas/matplotlib.
        rows: List[Dict[str, float]] = []
        with args.input.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if not expected_cols.issubset(row):
                    continue
                parsed = {}
                for k in expected_cols | {"issue_a_ms", "issue_b_ms"}:
                    if k in row and row[k]:
                        try:
                            parsed[k] = float(row[k])
                        except ValueError:
                            continue
                rows.append(parsed)
        if not rows:
            raise SystemExit("No rows parsed for required metrics.")
        summary = summarize_lists(rows)
        print("Summary stats (fallback):")
        for metric, stats in summary.items():
            print(metric, {k: round(v, 3) for k, v in stats.items()})
        means = mean_first_n_lists(rows)
        print("Mean over first 100 (or fewer) rows (ms):", {k: round(v, 3) for k, v in means.items()})
        print("Plots skipped (matplotlib/pandas not available).")


if __name__ == "__main__":
    main()
