"""kt_data — KT mobility + NIMS contact + ILI 정제 데이터 + 표준 로더."""

__version__ = "0.1.0"

from kt_data.data.load_calendar import (
    classify_date,
    get_daytype_for_range,
)
from kt_data.data.load_contact import (
    get_contact_matrix,
    load_contact_matrices,
)
from kt_data.data.load_ili import (
    get_ili_timeseries,
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
    "classify_date",
    "get_contact_matrix",
    "get_daytype_for_range",
    "get_ili_timeseries",
    "get_population_matrix",
    "load_contact_matrices",
    "load_ili_seasons",
    "load_mobility",
    "load_population_15groups",
]
