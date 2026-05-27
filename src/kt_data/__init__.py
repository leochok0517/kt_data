"""kt_data — KT mobility + NIMS contact + ILI/HIRA 정제 데이터 + 표준 로더."""

__version__ = "0.1.0"

from kt_data.data.load_calendar import (
    classify_date,
    get_daytype_for_range,
)
from kt_data.data.load_contact import (
    get_contact_matrix,
    load_contact_matrices,
)
from kt_data.data.load_employment import (
    build_rho_matrix,
    get_sido_array,
    get_sido_from_admdong,
    load_employment_rate,
)
from kt_data.data.load_hira import (
    HIRA_AGE_GROUPS,
    HIRA_SIDO_CODES,
    SUDOGWON_SIDO_CODES,
    aggregate_hira_weekly,
    extract_hira_season,
    load_hira_episodes,
)
from kt_data.data.load_ili import (
    ILI_AGE_GROUPS,
    ILI_GROUP_TO_NIMS,
    ILI_GROUP_TO_NIMS_WEIGHTED,
    get_ili_timeseries,
    load_ili_all_age_groups,
    load_ili_by_age,
    load_ili_seasons,
)
from kt_data.data.load_mobility import load_mobility
from kt_data.data.load_population import (
    AGE_LABELS_15,
    get_population_matrix,
    load_population_15groups,
)

__all__ = [
    "AGE_LABELS_15",
    "HIRA_AGE_GROUPS",
    "HIRA_SIDO_CODES",
    "ILI_AGE_GROUPS",
    "ILI_GROUP_TO_NIMS",
    "ILI_GROUP_TO_NIMS_WEIGHTED",
    "SUDOGWON_SIDO_CODES",
    "aggregate_hira_weekly",
    "build_rho_matrix",
    "classify_date",
    "extract_hira_season",
    "get_contact_matrix",
    "get_daytype_for_range",
    "get_ili_timeseries",
    "get_population_matrix",
    "get_sido_array",
    "get_sido_from_admdong",
    "load_contact_matrices",
    "load_employment_rate",
    "load_hira_episodes",
    "load_ili_all_age_groups",
    "load_ili_by_age",
    "load_ili_seasons",
    "load_mobility",
    "load_population_15groups",
]
