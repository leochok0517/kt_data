"""Data loaders + shared DATA_ROOT.

DATA_ROOT 결정 우선순위:
1. 환경변수 `KT_DATA_ROOT`
2. 패키지가 소스 트리에 있으면 프로젝트 루트의 `data/`
3. 위 둘 다 실패하면 cwd의 `data/`
"""

from __future__ import annotations

import os
from pathlib import Path


def _resolve_data_root() -> Path:
    env = os.environ.get("KT_DATA_ROOT")
    if env:
        return Path(env)
    # __file__ = .../src/kt_data/data/__init__.py
    # parents[3] = project root
    here = Path(__file__).resolve()
    candidate = here.parents[3] / "data"
    if candidate.exists():
        return candidate
    return Path("data")


DATA_ROOT: Path = _resolve_data_root()
