"""Build 수도권 (Seoul/Incheon/Gyeonggi) 행정동 mapping table from KT code definition CSV."""

from pathlib import Path

import polars as pl

SRC = Path("/data_ssd/KT_data_2025/전국_누적_행정동코드_정의서_KT_20251205_code_converted.csv")
OUT = Path("/data_ssd/hwcho/projects/kt_mobility/data/mapping/sudogwon_admdong.parquet")
SUDOGWON = ["11", "28", "41"]  # 서울, 인천, 경기
SIDO_NAME = {"11": "서울", "28": "인천", "41": "경기"}

COLS = ["sido_cd", "sido_nm", "sgg_cd", "sgg_nm", "admdong_cd", "admdong_nm"]


def main() -> None:
    df = pl.read_csv(SRC, schema_overrides={c: pl.String for c in COLS})
    df = df.select(COLS)

    total_nationwide = df.height
    sudo = df.filter(pl.col("sido_cd").is_in(SUDOGWON))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    sudo.write_parquet(OUT, compression="snappy")

    print(f"전국 행정동 총 개수: {total_nationwide:,}")
    print()
    print("수도권 행정동 개수:")
    total_dong = 0
    for code in SUDOGWON:
        n = sudo.filter(pl.col("sido_cd") == code).height
        total_dong += n
        print(f"  {SIDO_NAME[code]} ({code}): {n:,}")
    print(f"  합계: {total_dong:,}")
    print()
    print("수도권 시군구 개수 (unique sgg_cd):")
    total_sgg = 0
    for code in SUDOGWON:
        n = sudo.filter(pl.col("sido_cd") == code).select("sgg_cd").n_unique()
        total_sgg += n
        print(f"  {SIDO_NAME[code]} ({code}): {n:,}")
    print(f"  합계: {total_sgg:,}")
    print()
    print("첫 5행 샘플:")
    with pl.Config(tbl_width_chars=200, fmt_str_lengths=50):
        print(sudo.head(5))
    print()
    size_bytes = OUT.stat().st_size
    print(f"출력 파일: {OUT}")
    print(f"파일 크기: {size_bytes:,} bytes ({size_bytes / 1024:.1f} KiB)")


if __name__ == "__main__":
    main()
