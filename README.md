# kt_data

KT mobility + NIMS contact + ILI 데이터 정제 및 표준 로더 패키지.

수도권 metapop 인플루엔자 모델용 input 구축이 목적.

## 프로젝트 목표
- 수도권(서울/경기/인천) 행정동 단위 metapop 모델용 데이터 정제
- 인플루엔자 정상 시기 정책 가이드 + sick-leave ICER 분석 후속 프로젝트([`kt_epimodel`](../kt_epimodel/))에 input 제공

## 핵심 데이터 5종

| 데이터 | 출처 | 형태 | 용도 |
|---|---|---|---|
| 인구 (15군) | 행정안전부 주민등록 | 1,148 × 15 | $N$ (인구 분모) |
| Mobility $\pi$ | KT 통신 데이터 | 1,154 × 1,154 × 7 × 24 | $\pi$ (FOI 가중치) |
| Contact $C$ | NIMS 설문 | 15 × 15 × 4 settings | $C$ (FOI 강도) |
| Calendar $\lambda(t)$ | 학사 + 공휴일 | 일별 daytype | $\lambda(t)$ 시간 가변 |
| ILI | 질병청 표본감시 | 5 시즌 × 52주 | calibration target |

## 정제 결과

### KT Mobility (72개월)
- 입력: KT 셀(250m) 단위 OD 데이터
- 출력: 행정동(1,155) × 행정동 × 연령(10세) × 시간(24h) parquet
- 크기: 약 **103 GB** (월별 ~1.4 GB)
- 변환: 셀-행정동 매핑 / 평일·주말 분리 / `purpose` 제거 / `avg_dist`(m)·`avg_time`(분) 가중평균

### KT 검출률 (주요 발견)

야간(03–05시) LivePOP과 주민등록 비교:

| 연령 | 검출률 | 모델 처리 |
|---|---|---|
| **0–9** | **0.15** | 정적 (휴대폰 미보유) |
| 10–69 | 0.85–0.95 | KT 사용 (× 1/0.9 보정) |
| **70+** | **1.50** | 정적 (자녀 집 거주로 주민등록 < 실거주 추정) |

→ 0–9, 70+는 mobility 사용 불가, **정적 모델 결정**.

## 설치
uv 환경 권장 (Python 3.12+):
```bash
cd ~/Documents/python/NIMS/kt_data
uv sync
uv pip install -e .
```

## 사용법

### 패키지 import
```python
from kt_data import (
    load_population_15groups,
    load_mobility,
    load_contact_matrices,
    get_contact_matrix,
    classify_date,
    load_ili_seasons,
)
```

### 예시
```python
# 인구 데이터 (수도권 15군)
df_pop = load_population_15groups()              # polars DataFrame

# Mobility (한 월, 평일 평균)
mob = load_mobility("202301", daytype="weekday")
pi = mob["pi"]                                   # (1154, 1154, 7, 24) ndarray

# Contact matrix
contact = load_contact_matrices()
C_weekday = get_contact_matrix(contact, daytype="weekday_school")

# 캘린더
daytype = classify_date(20230315)                # 'weekday_school'

# ILI
df_ili = load_ili_seasons()                      # 5 seasons × 52 weeks
```

### 다른 프로젝트에서 사용
형제 폴더(예: `../kt_epimodel`)의 `pyproject.toml`에:
```toml
[tool.uv.sources]
kt-data = { path = "../kt_data", editable = true }
```
데이터 경로는 자동 해석 (`../kt_data/data`) 또는 `KT_DATA_ROOT` 환경변수로 지정.

## 데이터 위치
`data/` 폴더는 git에 포함되지 않음. 별도 보관/복사 필요.

| 경로 | 내용 | 크기 |
|---|---|---|
| `data/raw/movement/` | KT Movement 72개월 | ~103 GB |
| `data/raw/livepop_age5/` | LivePOP 5세 단위 72개월 | ~4.5 GB |
| `data/mapping/` | 행정동 polygon, 주민등록 매핑 | 수십 MB |
| `data/external/contact_matrices/` | NIMS 4 settings | 수십 KB |
| `data/external/ili/` | ILI 시즌별 | 수 KB |

## 노트북
- [`notebooks/integrated_eda.ipynb`](notebooks/integrated_eda.ipynb) — 5개 로더 통합 시각화
- [`notebooks/age_validation_2023_01.ipynb`](notebooks/age_validation_2023_01.ipynb) — 검출률 분석 (전 연령)
- [`notebooks/avgdist_unit_validation.ipynb`](notebooks/avgdist_unit_validation.ipynb) — `avg_dist` / `avg_time` 단위 검증
- [`notebooks/heatmap_2023_hourly.ipynb`](notebooks/heatmap_2023_hourly.ipynb) — 시간대별 mobility heatmap

## 발표 자료
- [`docs/presentation.md`](docs/presentation.md) — MARP 슬라이드
- 변환: `npx @marp-team/marp-cli docs/presentation.md --pdf`

## 다음 프로젝트
[`kt_epimodel`](../kt_epimodel/) — metapop 모델 + ILI calibration + sick-leave ICER 분석

## 라이선스 / 인용
(추후 명시)
