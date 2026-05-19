"""Movement full pipeline 2018-01 ~ 2023-12 (72 months, skips months already present).

Aggregates each monthly CSV to (date, hour, O dong, D dong, age_10) — purpose is summed away.
Idempotent: skips months whose output parquet already exists (2023-01 pilot stays untouched).
Per-month progress + summary CSV.
"""

import csv
import resource
import time
import traceback
from datetime import datetime
from pathlib import Path

import polars as pl

PROJECT = Path("/data_ssd/hwcho/projects/kt_mobility")
SRC_DIR = Path("/data_ssd/KT_data_2025/Movement")
OUT_DIR = PROJECT / "data" / "movement"
LOG_DIR = PROJECT / "logs"
MAPPING = PROJECT / "data" / "mapping" / "cell_to_admdong.parquet"
SUMMARY_CSV = LOG_DIR / "movement_full_summary.csv"

SCHEMA = {
    "ETL_YMD": pl.Int32,
    "TIME_CD": pl.String,
    "O_CELL_ID": pl.String,
    "D_CELL_ID": pl.String,
    "SEX_CD": pl.String,
    "AGE_CD": pl.String,
    "PURPOSE": pl.Int8,
    "TOTAL": pl.Float64,
    "AVG_DIST": pl.Float64,
    "AVG_TIME": pl.Float64,
}

SUMMARY_FIELDS = [
    "yyyymm",
    "status",
    "output_rows",
    "total_sum",
    "elapsed_sec",
    "max_rss_gb",
    "out_mb",
    "error",
]


def log(msg: str) -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


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


def process_month(yyyymm: str, sudo_cells: list[str], o_map: pl.DataFrame, d_map: pl.DataFrame) -> dict:
    src = SRC_DIR / f"MSL_{yyyymm}.csv"
    out = OUT_DIR / f"movement_sudogwon_{yyyymm}.parquet"
    row: dict = {"yyyymm": yyyymm}

    if out.exists():
        row["status"] = "SKIPPED"
        return row
    if not src.exists():
        row["status"] = "MISSING_INPUT"
        row["error"] = str(src)
        return row

    t0 = time.perf_counter()
    log(f"  {yyyymm}: input {src.stat().st_size / 1024**3:.2f} GB — building pipeline")

    lf = (
        pl.scan_csv(src, schema_overrides=SCHEMA)
        .filter(pl.col("O_CELL_ID").is_in(sudo_cells) & pl.col("D_CELL_ID").is_in(sudo_cells))
        .join(o_map.lazy(), on="O_CELL_ID", how="inner")
        .join(d_map.lazy(), on="D_CELL_ID", how="inner")
        .with_columns(
            pl.col("ETL_YMD").alias("date"),
            pl.col("TIME_CD").str.slice(0, 2).cast(pl.Int8).alias("hour"),
            pl.col("AGE_CD").cast(pl.Int8).alias("age_10"),
        )
        .group_by(
            ["date", "hour", "o_admdong_cd", "o_admdong_nm", "d_admdong_cd", "d_admdong_nm", "age_10"]
        )
        .agg(
            pl.col("TOTAL").sum().alias("total"),
            (pl.col("AVG_DIST") * pl.col("TOTAL")).sum().alias("_wd"),
            (pl.col("AVG_TIME") * pl.col("TOTAL")).sum().alias("_wt"),
        )
        .with_columns(
            (pl.col("_wd") / pl.col("total")).alias("avg_dist"),
            (pl.col("_wt") / pl.col("total")).alias("avg_time"),
        )
        .select(
            [
                "date",
                "hour",
                "o_admdong_cd",
                "o_admdong_nm",
                "d_admdong_cd",
                "d_admdong_nm",
                "age_10",
                "total",
                "avg_dist",
                "avg_time",
            ]
        )
        .sort(["date", "hour", "o_admdong_cd", "d_admdong_cd", "age_10"])
    )

    df = lf.collect(engine="streaming")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.write_parquet(out, compression="snappy")

    elapsed = time.perf_counter() - t0
    out_mb = out.stat().st_size / 1024 / 1024
    max_rss_gb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 / 1024

    row.update(
        {
            "status": "OK",
            "output_rows": df.height,
            "total_sum": f"{float(df.get_column('total').sum()):.4f}",
            "elapsed_sec": f"{elapsed:.2f}",
            "max_rss_gb": f"{max_rss_gb:.2f}",
            "out_mb": f"{out_mb:.2f}",
        }
    )
    return row


def validate_one(path: Path, label: str) -> None:
    """Spot-check integrity of a single parquet."""
    df = pl.read_parquet(path)
    log(f"  [{label}] {path.name}: rows={df.height:,}")
    nulls = df.null_count().row(0)
    if sum(nulls) > 0:
        log(f"    NULL counts: {dict(zip(df.columns, nulls))}  ← FAIL")
    neg = df.filter(pl.col("total") < 0).height
    if neg:
        log(f"    total<0: {neg}  ← FAIL")
    hours = df.get_column("hour").unique().to_list()
    if min(hours) < 0 or max(hours) > 23:
        log(f"    hour out of range: {sorted(hours)}  ← FAIL")
    log(f"    sum(total)={float(df.get_column('total').sum()):,.0f}, hours={sorted(hours)}")


def main() -> None:
    log("=== Movement full pipeline 2018-01 ~ 2023-12 ===")
    mapping = pl.read_parquet(MAPPING).select(["cell_id", "admdong_cd", "admdong_nm"])
    sudo_cells = mapping.get_column("cell_id").to_list()
    o_map = mapping.rename(
        {"cell_id": "O_CELL_ID", "admdong_cd": "o_admdong_cd", "admdong_nm": "o_admdong_nm"}
    )
    d_map = mapping.rename(
        {"cell_id": "D_CELL_ID", "admdong_cd": "d_admdong_cd", "admdong_nm": "d_admdong_nm"}
    )
    log(f"loaded mapping: {len(sudo_cells):,} sudogwon cells")

    all_months = months()
    log(f"will iterate {len(all_months)} months (skips outputs that already exist)")
    log(f"output dir: {OUT_DIR}")
    log(f"summary:    {SUMMARY_CSV}")

    t_all = time.perf_counter()
    ok_count = 0
    skip_count = 0
    fail_count = 0
    for i, ym in enumerate(all_months, 1):
        log(f"[{i:>2}/{len(all_months)}] {ym} start")
        try:
            row = process_month(ym, sudo_cells, o_map, d_map)
        except Exception as e:
            row = {"yyyymm": ym, "status": "FAILED", "error": f"{type(e).__name__}: {e}"}
            traceback.print_exc()
        append_summary(row)
        status = row.get("status", "?")
        if status == "OK":
            ok_count += 1
        elif status == "SKIPPED":
            skip_count += 1
        else:
            fail_count += 1
        log(
            f"[{i:>2}/{len(all_months)}] {ym} {status} "
            f"elapsed={row.get('elapsed_sec', '-')}s rows={row.get('output_rows', '-')} "
            f"rss={row.get('max_rss_gb', '-')}GB size={row.get('out_mb', '-')}MB"
        )

    total_min = (time.perf_counter() - t_all) / 60
    log("")
    log(f"=== ALL DONE in {total_min:.1f} min ===")
    log(f"  OK={ok_count}  SKIPPED={skip_count}  FAILED={fail_count}")
    if ok_count:
        log(f"  avg per OK month: {total_min / max(ok_count, 1):.2f} min")

    # ---- 검증 ----
    log("")
    log("=== VALIDATION ===")
    files = sorted(OUT_DIR.glob("movement_sudogwon_*.parquet"))
    log(f"output files: {len(files)} (expected 72)")
    total_size_gb = sum(p.stat().st_size for p in files) / 1024**3
    log(f"total disk: {total_size_gb:.2f} GB")

    if files:
        validate_one(files[0], "first")
        if len(files) > 1:
            validate_one(files[-1], "last")

    log("")
    log("=== MONTHLY TIME SERIES (sum total) ===")
    series = []
    for p in files:
        ym = p.stem.replace("movement_sudogwon_", "")
        s = float(pl.read_parquet(p, columns=["total"]).get_column("total").sum())
        series.append((ym, s))
    for ym, s in series:
        log(f"  {ym}: total={s:,.0f}")

    if series:
        med = sorted(s for _, s in series)[len(series) // 2]
        outliers = [(ym, s) for ym, s in series if s < med * 0.5 or s > med * 1.8]
        if outliers:
            log("  ⚠ outlier months (vs median):")
            for ym, s in outliers:
                log(f"    {ym}: {s:,.0f} ({s / med:.2f}× median)")
        else:
            log("  no outlier months (all within 0.5×~1.8× median)")

    log("Done")


if __name__ == "__main__":
    main()
