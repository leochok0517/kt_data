"""
Merge MOIS (행정안전부) 주민등록 연령별 인구 CSVs into one parquet.

Input  : data/raw/주민등록/{서울,경기도,인천}/202301_202301_연령별인구현황_월간_*.csv (CP949)
Output : data/mapping/mois_population_202301.parquet           (5세 단위, long)
         data/mapping/mois_population_202301_age10.parquet     (10세 단위, KT 매칭용)

Per-file structure
------------------
- 첫 행: 시군구 합계  (제외)
- 나머지 행: 행정동
- "행정구역" 컬럼은 두 가지 형식
    합계행:   "서울특별시 강남구 (1168000000)"          ← 행정동 명 없음 + 공백 + 괄호
    행정동:   "서울특별시 강남구 신사동(1168051000)"     ← 공백 없이 괄호
"""

from __future__ import annotations

import re
from pathlib import Path

import polars as pl


ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "data" / "raw" / "주민등록"
OUT_DIR = ROOT / "data" / "mapping"
OUT_5 = OUT_DIR / "mois_population_202301.parquet"
OUT_10 = OUT_DIR / "mois_population_202301_age10.parquet"
KT_MAPPING = OUT_DIR / "sudogwon_admdong.parquet"

PROVINCES = ["서울", "경기도", "인천"]

# Summary rows have a space *before* the "(", e.g.
#   "경기도 고양시 덕양구 (4128100000)"
# Non-summary (행정동) rows do not:
#   "경기도 고양시 덕양구 주교동(4128151000)"
# Files like 고양시.csv contain multiple summary rows (시 자체 + 구별), so
# the "drop first row" trick does not work.
SUMMARY_PAT = r"\s\(\d{10}\)$"

# After dropping summaries, extract address and code separately.
ADMDONG_PAT = r"^(?P<addr>.+?)\((?P<code>\d{10})\)$"

# Five-year bin column names → start age.  100세 이상 → 100.
AGE_COL_PAT = re.compile(r"^2023년01월_계_(\d+)(?:[~](\d+)세|세 이상)$")


def discover_age_columns(header: list[str]) -> list[tuple[str, int]]:
    """Return [(col_name, age_5_start), ...] for the 23 age bins."""
    out: list[tuple[str, int]] = []
    for col in header:
        m = AGE_COL_PAT.match(col)
        if not m:
            continue
        start = int(m.group(1))
        out.append((col, start))
    return out


def read_one(csv_path: Path) -> pl.DataFrame:
    """Read one MOIS CSV → long DataFrame with columns
    [admdong_cd, admdong_cd_10digit, sido_nm, sgg_nm, admdong_nm, age_5_start, pop_5]."""

    raw = pl.read_csv(
        csv_path,
        encoding="cp949",
        infer_schema_length=0,   # everything as Utf8
        has_header=True,
    )

    age_cols = discover_age_columns(raw.columns)
    if len(age_cols) != 21:
        raise RuntimeError(
            f"{csv_path.name}: expected 21 5yr bins, got {len(age_cols)}"
        )

    # Drop ALL summary rows (시 자체 + 구별 합계).  In multi-구 시들
    # (고양/성남/수원/안산/안양/용인) the file contains several of these.
    wide = raw.filter(~pl.col("행정구역").str.contains(SUMMARY_PAT))

    parsed = (
        wide.select(
            pl.col("행정구역").str.extract_groups(ADMDONG_PAT).alias("g"),
            *[pl.col(c).alias(c) for c, _ in age_cols],
        )
        .with_columns(
            pl.col("g").struct.field("addr").alias("addr"),
            pl.col("g").struct.field("code").alias("admdong_cd_10digit"),
        )
        .drop("g")
    )

    n_null = parsed["admdong_cd_10digit"].null_count()
    if n_null:
        raise RuntimeError(
            f"{csv_path.name}: {n_null} rows failed admdong parse — sample: "
            f"{wide['행정구역'].head(3).to_list()}"
        )

    # Split "<sido> <sgg [구]> <admdong_nm>" by spaces.  Anything between
    # first and last token is the 시군구 (1 token for 구, 2 for 시+구).
    parsed = parsed.with_columns(
        pl.col("addr").str.split(" ").alias("_parts")
    ).with_columns(
        pl.col("_parts").list.get(0).alias("sido_nm"),
        pl.col("_parts").list.get(-1).alias("admdong_nm"),
        pl.col("_parts")
        .list.slice(1, pl.col("_parts").list.len() - 2)
        .list.join(" ")
        .alias("sgg_nm"),
    ).drop(["addr", "_parts"])

    # Strip thousand separators, cast to Int64.
    age_col_names = [c for c, _ in age_cols]
    parsed = parsed.with_columns(
        [
            pl.col(c).str.replace_all(",", "").cast(pl.Int64).alias(c)
            for c in age_col_names
        ]
    )

    # Melt into long.
    long = parsed.unpivot(
        on=age_col_names,
        index=["admdong_cd_10digit", "sido_nm", "sgg_nm", "admdong_nm"],
        variable_name="age_col",
        value_name="pop_5",
    )

    age_map = {c: start for c, start in age_cols}
    long = long.with_columns(
        pl.col("age_col")
        .replace_strict(age_map, return_dtype=pl.Int8)
        .alias("age_5_start"),
        pl.col("admdong_cd_10digit").str.slice(0, 8).alias("admdong_cd"),
    ).drop("age_col")

    return long.select(
        [
            "admdong_cd",
            "admdong_cd_10digit",
            "sido_nm",
            "sgg_nm",
            "admdong_nm",
            "age_5_start",
            "pop_5",
        ]
    )


def age5_to_age10(age_5_start: int) -> int:
    """0,5→0; 10,15→10; ...; 70,75→70; 80~100+→80."""
    if age_5_start >= 80:
        return 80
    return (age_5_start // 10) * 10


def main() -> None:
    if not SRC_ROOT.exists():
        raise SystemExit(f"missing input dir: {SRC_ROOT}")

    csv_paths: list[Path] = []
    per_province: dict[str, int] = {}
    for prov in PROVINCES:
        prov_dir = SRC_ROOT / prov
        # NB: macOS stores Korean filenames in NFD; matching with the precomposed
        # (NFC) literal in source code fails. Use a simple ASCII-only glob.
        files = sorted(prov_dir.glob("202301_202301_*.csv"))
        per_province[prov] = len(files)
        csv_paths.extend(files)

    print(f"Found {len(csv_paths)} CSVs:")
    for prov, n in per_province.items():
        print(f"  {prov}: {n}")
    print()

    frames = [read_one(p) for p in csv_paths]
    df5 = pl.concat(frames, how="vertical")
    print(f"Total rows (5yr long): {df5.height:,}")
    print(f"Distinct admdongs    : {df5['admdong_cd'].n_unique():,}")
    print()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df5_out = df5.select(
        [
            pl.col("admdong_cd").cast(pl.Utf8),
            pl.col("admdong_nm").cast(pl.Utf8),
            pl.col("sgg_nm").cast(pl.Utf8),
            pl.col("sido_nm").cast(pl.Utf8),
            pl.col("age_5_start").cast(pl.Int8),
            pl.col("pop_5").cast(pl.Int64),
        ]
    ).sort(["admdong_cd", "age_5_start"])
    df5_out.write_parquet(OUT_5, compression="snappy")
    print(f"wrote {OUT_5}  ({OUT_5.stat().st_size/1e3:.1f} KB, {df5_out.height:,} rows)")

    # ----- 10세 단위 -----
    df10 = (
        df5.with_columns(
            pl.col("age_5_start")
            .map_elements(age5_to_age10, return_dtype=pl.Int8)
            .alias("age_10")
        )
        .group_by(["admdong_cd", "admdong_nm", "sgg_nm", "sido_nm", "age_10"])
        .agg(pl.col("pop_5").sum().alias("pop"))
        .sort(["admdong_cd", "age_10"])
    )
    df10_out = df10.select(
        [
            pl.col("admdong_cd").cast(pl.Utf8),
            pl.col("admdong_nm").cast(pl.Utf8),
            pl.col("sgg_nm").cast(pl.Utf8),
            pl.col("sido_nm").cast(pl.Utf8),
            pl.col("age_10").cast(pl.Int8),
            pl.col("pop").cast(pl.Int64),
        ]
    )
    df10_out.write_parquet(OUT_10, compression="snappy")
    print(
        f"wrote {OUT_10}  ({OUT_10.stat().st_size/1e3:.1f} KB, {df10_out.height:,} rows)"
    )
    print()

    # ----- Validation -----
    print("=" * 60)
    print("Validation")
    print("=" * 60)

    # 시도별 행정동 수
    by_sido = (
        df5.group_by("sido_nm")
        .agg(pl.col("admdong_cd").n_unique().alias("n_admdong"))
        .sort("sido_nm")
    )
    print("\n시도별 행정동 수:")
    print(by_sido)

    # 인구 합계 (전 연령)
    total_pop = df5["pop_5"].sum()
    print(f"\n수도권 총인구 합계: {total_pop:,}")
    by_sido_pop = (
        df5.group_by("sido_nm")
        .agg(pl.col("pop_5").sum().alias("pop"))
        .sort("sido_nm")
    )
    print(by_sido_pop)

    # KT 매핑과 매칭률
    if KT_MAPPING.exists():
        kt = pl.read_parquet(KT_MAPPING)
        kt_codes = set(kt["admdong_cd"].cast(pl.Utf8).to_list())
        mois_codes = set(df5["admdong_cd"].to_list())
        matched = kt_codes & mois_codes
        only_kt = kt_codes - mois_codes
        only_mois = mois_codes - kt_codes
        print(f"\nKT mapping size : {len(kt_codes):,}")
        print(f"MOIS admdongs   : {len(mois_codes):,}")
        print(
            f"Matched         : {len(matched):,} "
            f"({100*len(matched)/max(len(kt_codes),1):.1f}% of KT, "
            f"{100*len(matched)/max(len(mois_codes),1):.1f}% of MOIS)"
        )
        print(f"In KT only      : {len(only_kt):,}")
        print(f"In MOIS only    : {len(only_mois):,}")
        if only_kt:
            kt_only_sample = (
                kt.filter(pl.col("admdong_cd").cast(pl.Utf8).is_in(list(only_kt)))
                .head(10)
            )
            print("\nSample of KT codes missing in MOIS (top 10):")
            print(kt_only_sample)
        if only_mois:
            mois_only_sample = (
                df5.filter(pl.col("admdong_cd").is_in(list(only_mois)))
                .select(["admdong_cd", "sido_nm", "sgg_nm", "admdong_nm"])
                .unique()
                .head(10)
            )
            print("\nSample of MOIS codes missing in KT (top 10):")
            print(mois_only_sample)
    else:
        print(f"\n(KT mapping not found at {KT_MAPPING} — skip match)")

    print("\nDone.")


if __name__ == "__main__":
    main()
