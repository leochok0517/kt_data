"""Movement 2023-01 pilot: filter to 수도권 internal OD, aggregate per (date, hour, O dong, D dong, age, purpose).

Streaming pipeline so the 44GB CSV (~676M rows) never has to be fully materialized.
"""

import resource
import time
from datetime import datetime
from pathlib import Path

import polars as pl

PROJECT = Path("/data_ssd/hwcho/projects/kt_mobility")
SRC = Path("/data_ssd/KT_data_2025/Movement/MSL_202301.csv")
MAPPING = PROJECT / "data" / "mapping" / "cell_to_admdong.parquet"
OUT = PROJECT / "data" / "movement" / "movement_sudogwon_202301.parquet"

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


def log(msg: str) -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()

    log(f"start movement_pilot 2023-01")
    log(f"input:  {SRC} ({SRC.stat().st_size / 1024**3:.2f} GB)")
    log(f"output: {OUT}")

    # ---- mapping ----
    log("loading cell→admdong mapping...")
    mapping = pl.read_parquet(MAPPING).select(["cell_id", "admdong_cd", "admdong_nm"])
    log(f"  mapping rows: {mapping.height:,}")
    sudo_cells = mapping.get_column("cell_id")  # Series — used for is_in

    # Two views for the two joins (rename to avoid column collision)
    o_map = mapping.rename({"cell_id": "O_CELL_ID", "admdong_cd": "o_admdong_cd", "admdong_nm": "o_admdong_nm"})
    d_map = mapping.rename({"cell_id": "D_CELL_ID", "admdong_cd": "d_admdong_cd", "admdong_nm": "d_admdong_nm"})

    # ---- streaming pipeline ----
    log("building lazy pipeline...")
    lf = (
        pl.scan_csv(SRC, schema_overrides=SCHEMA)
        .filter(pl.col("O_CELL_ID").is_in(sudo_cells) & pl.col("D_CELL_ID").is_in(sudo_cells))
        .join(o_map.lazy(), on="O_CELL_ID", how="inner")
        .join(d_map.lazy(), on="D_CELL_ID", how="inner")
        .with_columns(
            pl.col("ETL_YMD").alias("date"),
            pl.col("TIME_CD").str.slice(0, 2).cast(pl.Int8).alias("hour"),
            pl.col("AGE_CD").cast(pl.Int8).alias("age_10"),
            pl.col("PURPOSE").alias("purpose"),
        )
        .group_by(
            ["date", "hour", "o_admdong_cd", "d_admdong_cd", "age_10", "purpose"],
        )
        .agg(
            pl.col("TOTAL").sum().alias("total"),
            (pl.col("AVG_DIST") * pl.col("TOTAL")).sum().alias("_wd"),
            (pl.col("AVG_TIME") * pl.col("TOTAL")).sum().alias("_wt"),
            pl.col("o_admdong_nm").first().alias("o_admdong_nm"),
            pl.col("d_admdong_nm").first().alias("d_admdong_nm"),
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
                "purpose",
                "total",
                "avg_dist",
                "avg_time",
            ]
        )
        .sort(["date", "hour", "o_admdong_cd", "d_admdong_cd", "age_10", "purpose"])
    )

    log("collecting (streaming)...")
    t_collect = time.perf_counter()
    df = lf.collect(engine="streaming")
    log(f"  collect done in {time.perf_counter() - t_collect:.1f}s, rows: {df.height:,}")

    log(f"writing parquet → {OUT}")
    t_write = time.perf_counter()
    df.write_parquet(OUT, compression="snappy")
    log(f"  write done in {time.perf_counter() - t_write:.1f}s")

    out_mb = OUT.stat().st_size / 1024 / 1024
    elapsed = time.perf_counter() - t0
    max_rss_gb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 / 1024
    log(f"file size: {out_mb:,.1f} MB")
    log(f"total elapsed: {elapsed/60:.1f} min ({elapsed:.0f}s)")
    log(f"max RSS: {max_rss_gb:.2f} GB")

    # ---- 검증 ----
    log("=" * 60)
    log("VALIDATION")
    log("=" * 60)
    sudo_codes = set(mapping.get_column("admdong_cd").unique().to_list())

    n_o_bad = df.filter(~pl.col("o_admdong_cd").is_in(sudo_codes)).height
    n_d_bad = df.filter(~pl.col("d_admdong_cd").is_in(sudo_codes)).height
    log(f"o_admdong_cd 수도권 밖: {n_o_bad}  ({'PASS' if n_o_bad == 0 else 'FAIL'})")
    log(f"d_admdong_cd 수도권 밖: {n_d_bad}  ({'PASS' if n_d_bad == 0 else 'FAIL'})")

    hours = sorted(df.get_column("hour").unique().to_list())
    log(f"hour values: {hours}")
    log(f"  hour 0..23 within range: {'PASS' if min(hours) >= 0 and max(hours) <= 23 else 'FAIL'}")

    dmin = df.get_column("date").min()
    dmax = df.get_column("date").max()
    log(f"date range: {dmin} ~ {dmax}  ({'PASS' if dmin == 20230101 and dmax == 20230131 else 'WARN'})")

    nulls = df.null_count().row(0)
    log(f"NULL counts: {dict(zip(df.columns, nulls))}")
    log(f"  → {'PASS' if sum(nulls) == 0 else 'FAIL'}")

    neg = df.filter(pl.col("total") < 0).height
    log(f"total 음수 개수: {neg}  ({'PASS' if neg == 0 else 'FAIL'})")

    age_vals = sorted(df.get_column("age_10").unique().to_list())
    log(f"age_10 unique: {age_vals}")
    purpose_vals = sorted(df.get_column("purpose").unique().to_list())
    log(f"purpose unique: {purpose_vals}")

    total_sum = float(df.get_column("total").sum())
    log(f"sum(total) 최종 집계: {total_sum:,.2f}")

    log("=" * 60)
    log("SAMPLE (head 10)")
    log("=" * 60)
    with pl.Config(tbl_width_chars=200, fmt_str_lengths=20, tbl_rows=10):
        print(df.head(10))

    log("Done")


if __name__ == "__main__":
    main()
