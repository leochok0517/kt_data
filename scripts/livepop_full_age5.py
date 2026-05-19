"""LivePOP full pipeline 2018-01 ~ 2023-12 — 5-year age bands.

Differs from livepop_full.py only in:
  - age_5 (Int8) = raw last-2-digit code (00,10,15,20,25,...,75) instead of //10*10
  - outputs go to data/livepop_age5/  (does not touch data/livepop/)
  - summary CSV: logs/livepop_full_age5_summary.csv

Idempotent: skips months whose output parquet already exists.
"""

import csv
import time
import traceback
from datetime import datetime
from pathlib import Path

import polars as pl

PROJECT = Path("/data_ssd/hwcho/projects/kt_mobility")
SRC_DIR = Path("/data_ssd/KT_data_2025/LivePOP")
OUT_DIR = PROJECT / "data" / "livepop_age5"
LOG_DIR = PROJECT / "logs"
MAPPING = PROJECT / "data" / "mapping" / "sudogwon_admdong.parquet"
SUMMARY_CSV = LOG_DIR / "livepop_full_age5_summary.csv"

SUMMARY_FIELDS = [
    "yyyymm",
    "status",
    "input_rows",
    "filtered_rows",
    "output_rows",
    "unique_admdongs",
    "pop_sum_before",
    "pop_sum_after",
    "pop_diff",
    "elapsed_sec",
    "error",
]


def months() -> list[str]:
    return [f"{y}{m:02d}" for y in range(2018, 2024) for m in range(1, 13)]


def append_summary(row: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    write_header = not SUMMARY_CSV.exists()
    with SUMMARY_CSV.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SUMMARY_FIELDS)
        if write_header:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in SUMMARY_FIELDS})


def process_month(yyyymm: str, mapping: pl.DataFrame, sudo_codes: list[str]) -> dict:
    src = SRC_DIR / f"MSL_NATIE_LIVEPOP_{yyyymm}.csv"
    out = OUT_DIR / f"livepop_age5_sudogwon_{yyyymm}.parquet"
    row: dict = {"yyyymm": yyyymm}

    if out.exists():
        row["status"] = "SKIPPED"
        return row

    if not src.exists():
        row["status"] = "MISSING_INPUT"
        row["error"] = str(src)
        return row

    t0 = time.perf_counter()

    input_rows = (
        pl.scan_csv(src, schema_overrides={"ADMDONG_CD": pl.String, "TIMEZN_CD": pl.String})
        .select(pl.len())
        .collect(engine="streaming")
        .item()
    )

    filtered = (
        pl.scan_csv(src, schema_overrides={"ADMDONG_CD": pl.String, "TIMEZN_CD": pl.String})
        .filter(pl.col("ADMDONG_CD").is_in(sudo_codes))
        .collect(engine="streaming")
    )
    filter_rows = filtered.height
    pop_sum_before = float(filtered.get_column("POP").sum())

    aged = filtered.with_columns(
        pl.col("SEX_AGE_CD").str.slice(1, 2).cast(pl.Int8).alias("age_5"),
        pl.col("TIMEZN_CD").cast(pl.Int8).alias("hour"),
        pl.col("ETL_YMD").cast(pl.Int32).alias("date"),
        pl.col("ADMDONG_CD").alias("admdong_cd"),
    )

    agg = (
        aged.group_by(["date", "hour", "admdong_cd", "age_5"])
        .agg(pl.col("POP").sum().alias("pop"))
        .join(mapping, on="admdong_cd", how="left")
        .select(["date", "hour", "admdong_cd", "admdong_nm", "age_5", "pop"])
        .sort(["date", "hour", "admdong_cd", "age_5"])
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    agg.write_parquet(out, compression="snappy")

    pop_sum_after = float(agg.get_column("pop").sum())
    elapsed = time.perf_counter() - t0

    row.update(
        {
            "status": "OK",
            "input_rows": input_rows,
            "filtered_rows": filter_rows,
            "output_rows": agg.height,
            "unique_admdongs": agg.select("admdong_cd").n_unique(),
            "pop_sum_before": f"{pop_sum_before:.4f}",
            "pop_sum_after": f"{pop_sum_after:.4f}",
            "pop_diff": f"{abs(pop_sum_before - pop_sum_after):.6f}",
            "elapsed_sec": f"{elapsed:.2f}",
        }
    )
    return row


def main() -> None:
    mapping = pl.read_parquet(MAPPING).select(["admdong_cd", "admdong_nm"])
    sudo_codes = mapping.get_column("admdong_cd").to_list()

    all_months = months()
    print("=== LivePOP age-5 full pipeline ===")
    print(f"start: {datetime.now().isoformat(timespec='seconds')}")
    print(f"months to process: {len(all_months)} (2018-01 ~ 2023-12)")
    print(f"output dir: {OUT_DIR}")
    print(f"summary:    {SUMMARY_CSV}")
    print()

    t_all = time.perf_counter()
    for i, ym in enumerate(all_months, 1):
        print(
            f"[{i:>2}/{len(all_months)}] {ym} start @ {datetime.now().isoformat(timespec='seconds')}",
            flush=True,
        )
        try:
            row = process_month(ym, mapping, sudo_codes)
        except Exception as e:
            row = {"yyyymm": ym, "status": "FAILED", "error": f"{type(e).__name__}: {e}"}
            traceback.print_exc()
        append_summary(row)
        print(
            f"[{i:>2}/{len(all_months)}] {ym} {row.get('status')} "
            f"elapsed={row.get('elapsed_sec', '-')}s "
            f"rows={row.get('output_rows', '-')} "
            f"diff={row.get('pop_diff', '-')}",
            flush=True,
        )

    print()
    print(f"=== ALL DONE in {(time.perf_counter() - t_all) / 60:.1f} min ===")
    print(f"finish: {datetime.now().isoformat(timespec='seconds')}")


if __name__ == "__main__":
    main()
