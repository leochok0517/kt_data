"""Sanity check across all 72 LivePOP monthly parquets."""

from pathlib import Path

import polars as pl

PROJECT = Path("/data_ssd/hwcho/projects/kt_mobility")
OUT_DIR = PROJECT / "data" / "livepop"
SUMMARY_CSV = PROJECT / "logs" / "livepop_full_summary.csv"


def months() -> list[str]:
    return [f"{y}{m:02d}" for y in range(2018, 2024) for m in range(1, 13)]


def main() -> None:
    expected = months()

    # ---- 파일 존재 / 크기 ----
    print("[파일 존재 / 크기]")
    file_info = []
    missing = []
    for ym in expected:
        p = OUT_DIR / f"livepop_sudogwon_{ym}.parquet"
        if not p.exists():
            missing.append(ym)
            continue
        file_info.append((ym, p.stat().st_size))

    print(f"  기대: {len(expected)}개, 실제: {len(file_info)}개")
    if missing:
        print(f"  누락 월: {missing}")
    else:
        print("  누락 없음 → PASS")
    total_bytes = sum(s for _, s in file_info)
    print(f"  전체 용량: {total_bytes / 1024 / 1024:.1f} MB ({total_bytes / 1024**3:.2f} GB)")
    print()

    # ---- summary CSV 로딩 ----
    summary = pl.read_csv(SUMMARY_CSV, schema_overrides={"yyyymm": pl.String})
    # SKIPPED 행은 stats가 비어있을 수 있음 — 실제 parquet 다시 읽어서 보강
    print("[요약 CSV 상태 분포]")
    status_count = summary.group_by("status").len().sort("status")
    print(status_count)
    print()

    # SKIPPED 행 보강 (202301)
    skipped = summary.filter(pl.col("status") == "SKIPPED").get_column("yyyymm").to_list()
    fill_rows = []
    for ym in skipped:
        p = OUT_DIR / f"livepop_sudogwon_{ym}.parquet"
        df = pl.read_parquet(p)
        fill_rows.append(
            {
                "yyyymm": ym,
                "output_rows": df.height,
                "unique_admdongs": df.select("admdong_cd").n_unique(),
                "pop_sum_after": float(df.get_column("pop").sum()),
            }
        )

    # 통합 시계열 테이블
    base = summary.filter(pl.col("status") == "OK").select(
        [
            "yyyymm",
            pl.col("output_rows").cast(pl.Int64),
            pl.col("unique_admdongs").cast(pl.Int64),
            pl.col("pop_sum_after").cast(pl.Float64),
            pl.col("elapsed_sec").cast(pl.Float64),
        ]
    )
    if fill_rows:
        fill_df = pl.DataFrame(fill_rows).with_columns(
            pl.lit(None, dtype=pl.Float64).alias("elapsed_sec")
        )
        base = pl.concat([base, fill_df.select(base.columns)], how="vertical")
    ts = base.sort("yyyymm")

    # 파일 크기 합치기
    size_df = pl.DataFrame(
        {"yyyymm": [ym for ym, _ in file_info], "size_mb": [s / 1024 / 1024 for _, s in file_info]}
    )
    ts = ts.join(size_df, on="yyyymm", how="left")

    print("[월별 시계열 (72개월)]")
    with pl.Config(tbl_rows=80, tbl_width_chars=200, float_precision=2):
        print(ts)
    print()

    # ---- 추세 통계 ----
    print("[unique_admdongs 추세]")
    print(f"  min: {ts['unique_admdongs'].min()} @ {ts.filter(pl.col('unique_admdongs') == ts['unique_admdongs'].min()).get_column('yyyymm')[0]}")
    print(f"  max: {ts['unique_admdongs'].max()} @ {ts.filter(pl.col('unique_admdongs') == ts['unique_admdongs'].max()).get_column('yyyymm')[0]}")
    print(f"  first(201801): {ts.filter(pl.col('yyyymm') == '201801').get_column('unique_admdongs')[0]}")
    print(f"  last(202312):  {ts.filter(pl.col('yyyymm') == '202312').get_column('unique_admdongs')[0]}")
    print()

    print("[pop_sum 추세 (월별 총 POP 합계, 단위: 십억)]")
    pop_ts = ts.with_columns((pl.col("pop_sum_after") / 1e9).alias("pop_bil"))
    yearly = pop_ts.with_columns(pl.col("yyyymm").str.slice(0, 4).alias("year")).group_by("year").agg(
        pl.col("pop_bil").mean().alias("avg_pop_bil"),
        pl.col("pop_bil").min().alias("min_pop_bil"),
        pl.col("pop_bil").max().alias("max_pop_bil"),
    ).sort("year")
    print(yearly)
    print()

    # ---- 이상치 ----
    median_pop = ts["pop_sum_after"].median()
    threshold = median_pop * 0.5
    outliers = ts.filter(pl.col("pop_sum_after") < threshold).select(
        ["yyyymm", "pop_sum_after", "output_rows"]
    )
    print(f"[이상치 체크: pop_sum < median*0.5 = {threshold:,.0f}]")
    if outliers.height == 0:
        print("  이상치 없음 → PASS")
    else:
        print(outliers)
    print()

    # 월대월 큰 변동
    print("[월대월 POP 변동률 (절대값 > 15%)]")
    chg = ts.with_columns(
        ((pl.col("pop_sum_after") - pl.col("pop_sum_after").shift(1)) / pl.col("pop_sum_after").shift(1) * 100).alias("pct")
    ).filter(pl.col("pct").abs() > 15).select(["yyyymm", "pop_sum_after", "pct"])
    if chg.height == 0:
        print("  큰 변동 없음")
    else:
        with pl.Config(tbl_rows=30, float_precision=2):
            print(chg)


if __name__ == "__main__":
    main()
