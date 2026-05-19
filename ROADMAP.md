# kt_data 로드맵

> 최종 갱신: 2026-05 (프로젝트 완료, `kt_epimodel` 이관)  
> 목표: 수도권 metapop 인플루엔자 모델용 input 데이터 정제 + 표준 로더

## 프로젝트 완료 — 산출물 요약

### 데이터 정제
- KT Movement 72개월 정제 완료 (103 GB)
- LivePOP 5세 단위 72개월 (4.5 GB)
- 주민등록 5세 단위 (2023-01) → NIMS 15군 매핑
- NIMS contact matrix 15군 (home/work/school/other 4 settings)
- ILI 5절기 (52주 통일)

### 표준 로더 ([`src/kt_data/data/`](src/kt_data/data/))
- `load_population.py` — 주민등록 → 15군 인구
- `load_mobility.py` — KT Movement → π 텐서 (1154 × 1154 × 7 × 24)
- `load_contact.py` — NIMS contact matrix 로드 (transpose 적용)
- `load_calendar.py` — 학사 + 공휴일 → daytype 분류
- `load_ili.py` — ILI 시즌별 시계열 (ISO 36 → 다음해 35주, 52주 통일)

### 검증 노트북
- `age_validation_2023_01` — 연령별 검출률 (0–9: 0.15, 10–69: ~0.9, 70+: 1.5)
- `avgdist_unit_validation` — `avg_dist` (m) + `avg_time` (분) 단위 확정
- `integrated_eda` — 5개 데이터 통합 시각화

### 발표 자료
- [`docs/presentation.md`](docs/presentation.md) — MARP, 17 슬라이드

## 주요 결정 사항

### 데이터 검증
- **0–9세 KT 검출률 0.15** → mobility 사용 불가, **정적 모델 확정**
- **20–39세 검출률 ~0.9** → 보정 계수 ~1.1
- **70+ 검출률 1.5** → 정적 모델 + 자녀 집 거주 가설 (후속 검증 보류)
- `avg_dist` = m, `avg_time` = 분 (확정)

### 모델 구조 (`kt_epimodel`으로 이관)
- 질병: **인플루엔자** (정상 시기 정책 가이드)
- 모델 구조: **SEIR + Isolation**
- 공간: 행정동 **1,155**
- 연령: **NIMS 15군** (0-4, 5-9 분리)
- 시간 단위: **1일**
- 연령별 mobility 전략:
  - 0–9, 70+: 정적
  - 10–19: 학교 정적 + 학원 mobility
  - 20–69: KT 적극 활용

## 미해결 사항 (`kt_epimodel`에서 진행)

- $\lambda_{home}$, $\lambda_{work}$, $\lambda_{other}$ 시간 가변 정확값 (NIMS notebook 04/06 확인 필요)
- NIMS contact matrix 절대값 보정 ($\beta$로 흡수 잠정)
- ILI 시도별/연령별 raw data 협조 요청 (질병청)
- NIMS 설문 Q4 코드 8 / 9 / 9997 의미

## 다음 프로젝트: `kt_epimodel`

- 위치: [`../kt_epimodel`](../kt_epimodel/)
- 의존성: `kt-data` (editable)
- 작업:
  - **Stage 2**: Metapop 프로토타입
  - **Stage 3**: ILI Calibration
  - **Stage 4**: Sick-leave 시나리오
  - **Stage 5**: ICER 분석
- 자세한 설계: [`../kt_epimodel/docs/STAGE2_DESIGN.md`](../kt_epimodel/docs/STAGE2_DESIGN.md)
