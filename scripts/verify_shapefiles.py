"""Verify GIS environment and shapefiles before spatial join (Phase 2-A)."""

from pathlib import Path

import geopandas as gpd
import polars as pl

GIS_BASE = Path("/data_ssd/hwcho/projects/kt_mobility/data/gis")
SHAPEFILES = {
    "서울": GIS_BASE / "서울" / "TN_EMD_BNDRY.shp",
    "경기도": GIS_BASE / "경기도" / "TN_EMD_BNDRY.shp",
    "인천": GIS_BASE / "인천" / "TN_EMD_BNDRY.shp",
}

MAPPING = Path("/data_ssd/hwcho/projects/kt_mobility/data/mapping/sudogwon_admdong.parquet")
CELL_INFO = Path("/data_ssd/KT_data_2025/MSL_CELL_INFO.csv")


def main() -> None:
    print("=" * 80)
    print("SHAPEFILE PER-REGION VERIFICATION")
    print("=" * 80)

    gdfs: dict[str, gpd.GeoDataFrame] = {}
    for region, path in SHAPEFILES.items():
        print(f"\n--- {region} ---")
        print(f"path: {path}")
        if not path.exists():
            print("  FILE NOT FOUND")
            continue
        gdf = gpd.read_file(path)
        gdfs[region] = gdf
        print(f"  polygon count: {len(gdf):,}")
        print(f"  CRS: {gdf.crs}")
        print(f"  columns: {list(gdf.columns)}")
        print(f"  geom type distribution:")
        for t, n in gdf.geometry.geom_type.value_counts().items():
            print(f"    {t}: {n}")
        print(f"  bounds (minx, miny, maxx, maxy):")
        b = gdf.total_bounds
        print(f"    ({b[0]:.2f}, {b[1]:.2f}, {b[2]:.2f}, {b[3]:.2f})")
        print(f"  first 3 rows (no geometry):")
        print(gdf.drop(columns="geometry").head(3).to_string())

    # ---- 종합 점검 ----
    print("\n" + "=" * 80)
    print("CROSS-REGION CHECKS")
    print("=" * 80)
    crs_set = {region: str(g.crs) for region, g in gdfs.items()}
    print(f"CRS by region: {crs_set}")
    unique_crs = set(crs_set.values())
    print(f"  → {'PASS (모두 동일)' if len(unique_crs) == 1 else 'FAIL: CRS 불일치'}")

    col_set = {region: tuple(g.columns) for region, g in gdfs.items()}
    unique_cols = set(col_set.values())
    print(f"\n컬럼 구조 동일 여부: {'PASS' if len(unique_cols) == 1 else 'FAIL'}")
    if len(unique_cols) != 1:
        for r, c in col_set.items():
            print(f"  {r}: {c}")

    total_poly = sum(len(g) for g in gdfs.values())
    print(f"\nshapefile polygon 총합: {total_poly:,}")
    print(f"매핑 테이블 행정동 수:  1,314")
    print(f"차이: {total_poly - 1314:+d}")

    # ---- 매핑 join 가능성 샘플 ----
    print("\n" + "=" * 80)
    print("MAPPING JOIN COMPATIBILITY")
    print("=" * 80)
    mapping = pl.read_parquet(MAPPING)
    print(f"매핑 테이블 컬럼: {mapping.columns}")
    print(f"매핑 admdong_cd 길이 분포:")
    lengths = mapping.with_columns(pl.col("admdong_cd").str.len_chars().alias("L"))
    print(lengths.group_by("L").len().sort("L"))

    # shapefile 행정동 코드 후보 컬럼 — TN_EMD_BNDRY는 EMD_CD가 일반적
    candidates = ["EMD_CD", "ADM_CD", "ADMD_CD", "BJDONG_CD", "EMD_KOR_NM", "EMD_ENG_NM"]
    if gdfs:
        sample_region = next(iter(gdfs))
        cols = list(gdfs[sample_region].columns)
        present = [c for c in candidates if c in cols]
        print(f"\nshapefile에서 발견된 코드/이름 후보 컬럼: {present}")

        # 길이 분포로 8자리 코드 추정
        for c in cols:
            if c == "geometry":
                continue
            try:
                series = gdfs[sample_region][c].astype(str)
                lens = series.str.len().value_counts().to_dict()
                if any(k in (5, 7, 8, 10) for k in lens):
                    print(f"  '{c}' 값 길이 분포: {dict(lens)}")
            except Exception:
                pass

        # 모든 shapefile의 폴리곤 코드 vs 매핑 코드 교집합
        print("\n각 shapefile에서 'EMD_CD' 컬럼이 있으면 매핑과 교집합 확인:")
        all_shape_codes: set[str] = set()
        for region, g in gdfs.items():
            if "EMD_CD" not in g.columns:
                print(f"  {region}: EMD_CD 컬럼 없음")
                continue
            codes = set(g["EMD_CD"].astype(str).tolist())
            all_shape_codes |= codes
            print(f"  {region}: {len(codes):,}개 unique EMD_CD")
        if all_shape_codes:
            map_codes = set(mapping.get_column("admdong_cd").to_list())
            inter = all_shape_codes & map_codes
            print(f"\n  shapefile codes ∩ mapping codes: {len(inter):,}")
            print(f"  shapefile only: {len(all_shape_codes - map_codes):,}")
            print(f"  mapping only:   {len(map_codes - all_shape_codes):,}")
            sample = list(inter)[:5]
            print(f"  공통 코드 샘플 5개: {sample}")

    # ---- MSL_CELL_INFO ----
    print("\n" + "=" * 80)
    print("MSL_CELL_INFO PREVIEW")
    print("=" * 80)
    if not CELL_INFO.exists():
        print(f"NOT FOUND: {CELL_INFO}")
    else:
        cell_lazy = pl.scan_csv(CELL_INFO, infer_schema_length=10000)
        cell_schema = cell_lazy.collect_schema()
        print(f"컬럼: {dict(cell_schema)}")

        cell_head = cell_lazy.head(3).collect()
        print(f"\n첫 3행:")
        with pl.Config(tbl_width_chars=200, fmt_str_lengths=30):
            print(cell_head)

        if "UTM_X" in cell_schema and "UTM_Y" in cell_schema:
            stats = cell_lazy.select(
                pl.col("UTM_X").min().alias("x_min"),
                pl.col("UTM_X").max().alias("x_max"),
                pl.col("UTM_Y").min().alias("y_min"),
                pl.col("UTM_Y").max().alias("y_max"),
                pl.len().alias("n_rows"),
            ).collect(engine="streaming")
            print(f"\nUTM 좌표 범위:")
            print(stats)
            x_min = stats.item(0, "x_min")
            y_min = stats.item(0, "y_min")
            print(f"\n좌표계 추정:")
            print(f"  X≈{x_min:.0f}, Y≈{y_min:.0f}")
            if 700_000 <= x_min <= 1_200_000 and 1_500_000 <= y_min <= 2_100_000:
                print("  → EPSG:5179 (UTM-K) 가능성 높음")
            elif 100_000 <= x_min <= 300_000 and 400_000 <= y_min <= 700_000:
                print("  → EPSG:5186 (중부원점 TM) 가능성")


if __name__ == "__main__":
    main()
