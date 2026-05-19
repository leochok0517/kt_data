"""ILI 시즌별 주별 분율 로더 (CP949 CSV) + ISO 주차 매핑.

파일 형식:
- 헤더 없음, 5행 = 5절기 (2018-2019 ~ 2022-2023)
- 첫 열: 시즌명 "YYYY-YYYY절기"
- 이후 54열: week_in_season 0..53 슬롯 (실제 유효 길이는 시즌별로 52 또는 53)

시즌 정의 (질병관리청):
- 시작: ISO week 36 of start_year
- 종료: ISO week 35 of (start_year + 1)
- **본 모듈은 모든 시즌을 52주로 통일** (시즌간 비교 일관성).
  ISO 53주 시즌(예: 2020-2021)의 추가 1주는 is_valid_week=False 로 표시.

매핑 (uniform 52주):
  week_in_season  0..16  →  ISO 36..52 of start_year
  week_in_season 17..51  →  ISO  1..35 of (start_year + 1)
"""

from __future__ import annotations

import csv
import math
from datetime import date as date_cls
from functools import lru_cache
from pathlib import Path

import numpy as np
import polars as pl

_DEFAULT_PATH = Path("data/external/ili/2018-2023_ILI.csv")
N_SLOTS = 54  # CSV 한 행의 데이터 슬롯 수 (week_in_season 0..53)
UNIFIED_SEASON_LEN = 52  # 모든 시즌을 52주로 통일


@lru_cache(maxsize=64)
def _iso_weeks_in_year(year: int) -> int:
    """그 ISO 연도의 마지막 주차 (52 또는 53). Dec 28은 항상 마지막 ISO 주에 속함.
    참고용 — 시즌 길이 계산에는 사용 안 함 (모든 시즌 52주 통일)."""
    return int(date_cls(year, 12, 28).isocalendar().week)


def get_season_length(season: str) -> int:
    """시즌 길이(주). **모든 시즌 52주 통일**."""
    return UNIFIED_SEASON_LEN


SEASON_WEEKS: dict[str, int] = {f"{y}-{y + 1}": UNIFIED_SEASON_LEN for y in range(2018, 2023)}


def week_in_season_to_iso_week(season: str, week_in_season: int) -> tuple[int, int]:
    """week_in_season → (calendar_year, iso_week). 모든 시즌 동일 매핑.

    Mapping:
        w 0..16  → (start_year,     36 + w)
        w 17..51 → (start_year + 1, w - 16)

    Examples:
        ('2018-2019',  0) → (2018, 36)
        ('2018-2019', 16) → (2018, 52)
        ('2018-2019', 17) → (2019, 1)
        ('2018-2019', 51) → (2019, 35)
        ('2020-2021', 17) → (2021, 1)   # ISO 53 of 2020 은 valid 가 아님
    """
    if week_in_season < 0 or week_in_season >= UNIFIED_SEASON_LEN:
        raise ValueError(
            f"week_in_season {week_in_season} out of range for season {season!r} "
            f"(valid: 0..{UNIFIED_SEASON_LEN - 1})"
        )
    start_year = int(season.split("-")[0])
    if week_in_season < 17:
        return (start_year, 36 + week_in_season)
    return (start_year + 1, week_in_season - 16)


def load_ili_seasons(path: Path = _DEFAULT_PATH) -> pl.DataFrame:
    """ILI long-format DataFrame.

    Columns:
        season(str), season_start_year(i32), week_in_season(i32),
        iso_week(i32; invalid slot은 0), calendar_year(i32; invalid 0),
        is_valid_week(bool), ili_rate(f64; NaN 가능).

    Row count: 5 × N_SLOTS = 270 (모든 시즌 같은 슬롯 수 유지 — 시즌 길이는 is_valid_week로).
    """
    if not path.exists():
        raise FileNotFoundError(path)

    rows = []
    with path.open(encoding="cp949") as f:
        for line in csv.reader(f):
            if not line or not line[0].strip():
                continue
            season_token = line[0].strip()
            season = season_token.replace("절기", "")
            try:
                season_start = int(season.split("-")[0])
            except ValueError:
                raise ValueError(f"can't parse season token: {season_token!r}")

            season_len = SEASON_WEEKS.get(season, _iso_weeks_in_year(season_start))
            weekly = line[1:]
            if len(weekly) < N_SLOTS:
                weekly = weekly + [""] * (N_SLOTS - len(weekly))

            for w in range(N_SLOTS):
                valid = w < season_len
                if valid:
                    cy, iso_w = week_in_season_to_iso_week(season, w)
                    raw = weekly[w].strip()
                    rate = float(raw) if raw else math.nan
                else:
                    cy, iso_w = 0, 0
                    rate = math.nan
                rows.append((season, season_start, w, iso_w, cy, valid, rate))

    return pl.DataFrame(
        rows,
        schema=[
            ("season", pl.String),
            ("season_start_year", pl.Int32),
            ("week_in_season", pl.Int32),
            ("iso_week", pl.Int32),
            ("calendar_year", pl.Int32),
            ("is_valid_week", pl.Boolean),
            ("ili_rate", pl.Float64),
        ],
        orient="row",
    )


def get_ili_timeseries(
    season: str,
    valid_only: bool = True,
    start_week: int | None = None,
    end_week: int | None = None,
    df: pl.DataFrame | None = None,
) -> np.ndarray:
    """한 시즌의 ILI 시계열 (week_in_season 오름차순).

    Args:
        valid_only: True면 is_valid_week=True만 반환 (실제 시즌 길이만큼).
    """
    if df is None:
        df = load_ili_seasons()
    s = df.filter(pl.col("season") == season).sort("week_in_season")
    if s.height == 0:
        raise ValueError(f"unknown season: {season!r}")
    if valid_only:
        s = s.filter(pl.col("is_valid_week"))
    if start_week is not None:
        s = s.filter(pl.col("week_in_season") >= start_week)
    if end_week is not None:
        s = s.filter(pl.col("week_in_season") <= end_week)
    return s.get_column("ili_rate").to_numpy()


def plot_ili_seasons(
    df: pl.DataFrame | None = None,
    output_path: Path | None = None,
) -> None:
    """5 시즌 시계열 (x축 = ISO 주차로 통일). 코로나 시기 회색 점선."""
    import matplotlib.pyplot as plt

    if df is None:
        df = load_ili_seasons()

    covid = {"2020-2021", "2021-2022"}
    seasons = df.select("season").unique().sort("season").get_column("season").to_list()

    # ISO week order along the season axis: 36, 37, ..., 52[, 53], 1, 2, ..., 35
    def _iso_to_axis(iso_w: int) -> int:
        return iso_w - 36 if iso_w >= 36 else iso_w + (53 - 36)

    fig, ax = plt.subplots(figsize=(12, 5.5))
    for season in seasons:
        sub = df.filter((pl.col("season") == season) & pl.col("is_valid_week")).sort("week_in_season")
        iso = sub.get_column("iso_week").to_numpy()
        x = np.array([_iso_to_axis(int(w)) for w in iso])
        y = sub.get_column("ili_rate").to_numpy()
        label = f"{season}" + (" (COVID)" if season in covid else "")
        if season in covid:
            ax.plot(x, y, color="gray", ls="--", lw=1.5, alpha=0.7, label=label)
        else:
            ax.plot(x, y, lw=2, label=label)

    # x-tick labels show ISO week numbers
    ticks_axis = list(range(0, 53, 4))
    tick_labels = []
    for t in ticks_axis:
        iso_w = (t + 36) if (t + 36) <= 52 else (t + 36 - 52)
        tick_labels.append(str(iso_w))
    ax.set_xticks(ticks_axis)
    ax.set_xticklabels(tick_labels)
    ax.set_xlabel("ISO week (season axis: 36 → 52 [→ 53] → 1 → 35)")
    ax.set_ylabel("ILI rate (per 1000 outpatients)")
    ax.set_title("ILI weekly rates by season — 5 seasons")
    ax.grid(alpha=0.3)
    ax.legend(loc="upper left", fontsize=9)
    plt.tight_layout()
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=120)
        print(f"saved {output_path}")
    plt.close(fig)


if __name__ == "__main__":
    df = load_ili_seasons()
    print(f"행 수: {df.height}  (= 5 × {N_SLOTS})")
    print(f"unified season length: {UNIFIED_SEASON_LEN}")
    print()
    print("시즌별 valid 주 수 (52로 통일):")
    for s in SEASON_WEEKS:
        valid = df.filter((pl.col("season") == s) & pl.col("is_valid_week")).height
        print(f"  {s}: valid={valid}")
    print()

    summary = (
        df.filter(pl.col("is_valid_week"))
        .group_by("season")
        .agg(
            pl.col("ili_rate").mean().alias("mean"),
            pl.col("ili_rate").max().alias("max"),
            pl.col("ili_rate").min().alias("min"),
            pl.col("ili_rate").is_nan().sum().alias("nan_in_valid"),
        )
        .sort("season")
    )
    print(summary)

    print("\nISO 주차 매핑 샘플 (모든 시즌 동일):")
    for w in (0, 8, 16, 17, 35, 51):
        print(f"  w={w:>2} → {week_in_season_to_iso_week('2020-2021', w)}")

    plot_ili_seasons(df, output_path=Path("outputs/load_ili_check.png"))
