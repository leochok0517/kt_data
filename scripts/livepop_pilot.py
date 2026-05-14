"""LivePOP 2023-01 pilot: filter to 수도권, aggregate by (date, hour, admdong, age_10)."""

import resource
import time
from pathlib import Path

import polars as pl

SRC = Path("/data_ssd/KT_data_2025/LivePOP/MSL_NATIE_LIVEPOP_202301.csv")
MAPPING = Path("/data_ssd/hwcho/projects/kt_mobility/data/mapping/sudogwon_admdong.parquet")
OUT = Path("/data_ssd/hwcho/projects/kt_mobility/data/livepop/livepop_sudogwon_202301.parquet")


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)

    mapping = pl.read_parquet(MAPPING).select(["admdong_cd", "admdong_nm"])
    sudo_codes = mapping.get_column("admdong_cd").to_list()

    t0 = time.perf_counter()

    # Raw row count via streaming scan (cheap aggregation)
    raw_rows = (
        pl.scan_csv(SRC, schema_overrides={"ADMDONG_CD": pl.String, "TIMEZN_CD": pl.String})
        .select(pl.len())
        .collect(engine="streaming")
        .item()
    )

    lf = pl.scan_csv(
        SRC,
        schema_overrides={"ADMDONG_CD": pl.String, "TIMEZN_CD": pl.String},
    ).filter(pl.col("ADMDONG_CD").is_in(sudo_codes))

    filtered = lf.collect(engine="streaming")
    filter_rows = filtered.height
    filter_pop_sum = filtered.get_column("POP").sum()

    # Parse SEX_AGE_CD: last 2 chars → age code → age_10 = (int // 10) * 10
    aged = filtered.with_columns(
        (pl.col("SEX_AGE_CD").str.slice(1, 2).cast(pl.Int16) // 10 * 10)
        .cast(pl.Int8)
        .alias("age_10"),
        pl.col("TIMEZN_CD").cast(pl.Int8).alias("hour"),
        pl.col("ETL_YMD").cast(pl.Int32).alias("date"),
        pl.col("ADMDONG_CD").alias("admdong_cd"),
    )

    agg = (
        aged.group_by(["date", "hour", "admdong_cd", "age_10"])
        .agg(pl.col("POP").sum().alias("pop"))
        .join(mapping, on="admdong_cd", how="left")
        .select(["date", "hour", "admdong_cd", "admdong_nm", "age_10", "pop"])
        .sort(["date", "hour", "admdong_cd", "age_10"])
    )

    agg.write_parquet(OUT, compression="snappy")
    elapsed = time.perf_counter() - t0

    # ============ stats ============
    print("[입력 통계]")
    print(f"  원본 행 수: {raw_rows:,}")
    print(f"  처리 시간: {elapsed:.1f}초")
    print()
    print("[필터 통계]")
    print(f"  수도권 필터 후 행 수: {filter_rows:,}")
    print(f"  절감률: {(1 - filter_rows / raw_rows) * 100:.2f}%")
    print()
    out_size_mb = OUT.stat().st_size / 1024 / 1024
    print("[집계 통계]")
    print(f"  최종 출력 행 수: {agg.height:,}")
    print(f"  출력 parquet 크기: {out_size_mb:.2f} MB")
    print()

    print("[무결성 체크]")
    n_dong = agg.select("admdong_cd").n_unique()
    mapping_codes = set(sudo_codes)
    agg_codes = set(agg.get_column("admdong_cd").unique().to_list())
    print(f"  unique 행정동 수: {n_dong:,} (기대값 1,314) → {'PASS' if n_dong == 1314 else 'FAIL'}")
    if n_dong != 1314:
        missing = list(mapping_codes - agg_codes)[:5]
        extra = list(agg_codes - mapping_codes)[:5]
        print(f"    매핑에 있고 결과에 없음(처음5): {missing}")
        print(f"    결과에 있고 매핑에 없음(처음5): {extra}")

    n_date = agg.select("date").n_unique()
    print(f"  unique date 수: {n_date} (기대값 31) → {'PASS' if n_date == 31 else 'FAIL'}")

    n_hour = agg.select("hour").n_unique()
    print(f"  unique hour 수: {n_hour} (기대값 24) → {'PASS' if n_hour == 24 else 'FAIL'}")

    ages = sorted(agg.get_column("age_10").unique().to_list())
    expected_ages = [0, 10, 20, 30, 40, 50, 60, 70]
    print(f"  unique age_10: {ages} → {'PASS' if ages == expected_ages else 'FAIL'}")

    agg_pop_sum = agg.get_column("pop").sum()
    diff = abs(filter_pop_sum - agg_pop_sum)
    print(f"  POP 합계 필터직후: {filter_pop_sum:,.2f}")
    print(f"  POP 합계 집계후:   {agg_pop_sum:,.2f}")
    print(f"  차이: {diff:.4f} → {'PASS' if diff < 0.01 else 'FAIL'}")

    null_counts = agg.null_count().row(0)
    print(f"  NULL 개수 (컬럼별): {dict(zip(agg.columns, null_counts))}")
    print(f"    → {'PASS' if sum(null_counts) == 0 else 'FAIL'}")

    neg_count = agg.filter(pl.col("pop") < 0).height
    print(f"  POP 음수 개수: {neg_count} → {'PASS' if neg_count == 0 else 'FAIL'}")
    print()

    print("[샘플 — 첫 10행]")
    with pl.Config(tbl_width_chars=200, fmt_str_lengths=30, tbl_rows=10):
        print(agg.head(10))
    print()

    print("[샘플 — admdong_cd=11110515, 2023-01-01 00시, 모든 age_10]")
    sample = agg.filter(
        (pl.col("admdong_cd") == "11110515") & (pl.col("date") == 20230101) & (pl.col("hour") == 0)
    )
    with pl.Config(tbl_width_chars=200, fmt_str_lengths=30):
        print(sample)
    print(f"  행 수: {sample.height} (기대값 8)")
    print()

    max_rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # On Linux ru_maxrss is in KB
    print(f"[메모리] 최대 RSS: {max_rss_kb / 1024:.1f} MB")
    print(f"[출력 파일] {OUT}")


if __name__ == "__main__":
    main()
