# KT 생활인구 / 이동 데이터 정제

KT 시그널링 기반 생활인구(LivePOP) 및 이동(Movement) CSV 원본을 수도권 행정동 단위 parquet으로 정제하고, 시간별·연령별 시각화를 만드는 프로젝트.

## 데이터 출처
- 제공: KT (NIMS 수리과학연구소 협력 과제, **비공개 원본 — 본 저장소에 포함되지 않음**)
- 기간: 2018-01 ~ 2023-12 (72개월)
- 종류:
  - **LivePOP** (`MSL_NATIE_LIVEPOP_YYYYMM.csv`): 행정동 × 시간대 × 성/연령 인구 스냅샷
  - **Movement** (`MSL_YYYYMM.csv`): 셀 OD × 시간대 × 성/연령/통행목적 이동량

원본 데이터는 원격 분석 서버 (`wsson1`) 의 `/data_ssd/KT_data_2025/` 에 위치. 본 저장소는 정제 코드와 노트북만 보관.

## 환경 설정
```bash
git clone https://github.com/leochok0517/kt_data.git
cd kt_data
uv sync  # .venv 생성 + 의존성 설치 (Python 3.12)
```

Jupyter 커널을 등록하려면:
```bash
uv run python -m ipykernel install --user --name kt-data --display-name "Python (kt-data)"
```

## 폴더 구조
```
.
├── CLAUDE.md                # 작업 컨텍스트 및 환경 메모
├── README.md
├── pyproject.toml           # uv 의존성
├── uv.lock
├── .python-version
├── notebooks/
│   └── heatmap_2023_hourly.ipynb   # 2023 시간별 인구/밀도 히트맵
├── scripts/                 # 정제 파이프라인 (서버에서 실행)
│   ├── build_sudogwon_mapping.py
│   ├── livepop_pilot.py
│   ├── livepop_full.py
│   ├── livepop_sanity.py
│   ├── verify_shapefiles.py
│   └── movement_pilot.py
├── docs/                    # 참조 자료 (규격서 등)
└── data/                    # ※ .gitignore — 로컬에서만 보존
    ├── raw/                 # 정제 후 parquet (LivePOP 월별, Movement 월별)
    └── mapping/             # 행정동/폴리곤 매핑
```

## 진행 상황
- [x] **Phase 1-A**: 수도권 행정동 매핑 (1,314개) 생성
- [x] **Phase 1-B**: LivePOP 2023-01 파일럿 정제 (11초, 검증 통과)
- [x] **Phase 1-D**: LivePOP 72개월 전체 정제 (5.6분, 모든 월 OK)
- [x] **Phase 2-A**: GIS 환경 + shapefile 검증
- [x] **Phase 2-B**: 수도권 행정동 polygon (EPSG:5179, 1,155개)
- [x] **Phase 2-C**: cell ↔ admdong 공간 매핑 (178,119개 셀)
- [x] **Phase 3-A**: Movement 2023-01 파일럿 정제
- [ ] **Phase 3-B**: Movement 전체 72개월 정제
- [ ] **Phase 4**: 분석/시각화 확장 (출퇴근 OD, 연령별, 시계열 등)

## 작업 환경
- 정제 파이프라인은 원격 서버 (`wsson1`) 에서 실행. 큰 CSV (LivePOP 2.3GB/월, Movement 44GB/월) 를 polars streaming 으로 처리.
- 시각화 노트북은 로컬 macOS 에서 실행. 서버에서 정제된 parquet 만 받아옴.
- 모든 데이터 산출물은 `.gitignore` 로 추적 제외 (저장소 크기 보호).
