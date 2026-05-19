# KT 데이터 기반 전염병 모델링 — 작업 로드맵

> 최종 갱신: 2026-05-18 (학회 후)
> 목표: 수도권 metapop 인플루엔자 모델 + sick-leave 정책 ICER 평가
> 연구 방향: **정상 시기 정책 가이드** (매년 활용)

---

## 학회 후 확정 결정사항 (2026-05-18)

### 데이터 검증 결과
- ✅ **KT 검출률 (20-39세)**: 0.92-0.94 → KT 데이터 신뢰 가능
- ✅ **KT 검출률 (0-9세)**: 0.15 → mobility 사용 불가, 정적 모델 확정
- ✅ **avg_dist**: m 단위 확정
- ✅ **avg_time**: 분 단위 확정 (직선거리 기준 8.67 km/h, 정상)

### 모델 설계 결정
- ✅ **질병**: 인플루엔자 (ILI), 정상 시기 (2018-2019, 2023) 메인
- ✅ **모델 구조**: SEIR + Isolation (인플루엔자 무증상/pre-symptomatic 무시 가능)
- ✅ **공간 단위**: 행정동 1,155개
- ✅ **연령 단위**: 5세 17구간 (NIMS contact matrix 호환)
- ✅ **연령별 mobility 처리**:
  - 0-9세: 정적 (자기 행정동 내 home/school)
  - 10-19세: 학교 정적, 학원은 KT mobility + other
  - 20-69세: KT Movement 사용
  - 70+: 정적, minimal mobility
- ✅ **Contact matrix**: NIMS raw data 정리본 활용 (2019, 2023-12, 2024-2)
- ✅ **Calibration**: 연령별 susceptibility φ_a fit, contact matrix는 고정

### 데이터 가용성 확인
- ✅ **ILI 데이터**: 전국 평균만 (지역별 비공개)
- ⏳ **질병청 raw data 협조 요청**: NIMS 채널로 진행 중

---

## 진행 현황

| 단계 | 상태 | 비고 |
|---|---|---|
| Phase 1 LivePOP 정제 | ✅ 완료 (10세) | 5세 재정제 대기 |
| Phase 2 셀-행정동 매핑 | ✅ 완료 | 178,119 셀 → 1,155 행정동 |
| Phase 3-A Movement 2023-01 파일럿 | ✅ 완료 | purpose 포함 (재처리 필요) |
| Phase 3-B Movement 71개월 정제 | 🔄 진행 중 | tmux 백그라운드, ~3시간 예상 |
| 검증 노트북 (age_validation) | ✅ 완료 | 학회 결과 검증됨 |
| 검증 노트북 (avgdist) | ✅ 완료 | 단위 결정됨 |
| Phase 4 주민등록 비교 | ✅ 완료 | 2023-01 검출률 산출됨 |
| NIMS contact matrix | ✅ 보유 | raw data 정리본 활용 |
| ILI 데이터 (전국 평균) | ✅ 보유 | 2018-2023 5절기 |
| ILI 시도별/연령별 | ⏳ 요청 중 | 질병청 협조 |
| Stage 2 Metapop 프로토타입 | ⬜ 다음 단계 | |
| Stage 3 ILI Calibration | ⬜ | |
| Stage 4 Sick-leave 시나리오 | ⬜ | |
| Stage 5 ICER 분석 | ⬜ | |

---

## Part 1: 데이터 정제 마무리 (1-2일)

### Task 1-1: Phase 3-B 완료 확인 ⏰ 자동
- [ ] tmux 세션 종료 확인
- [ ] 71개 parquet 파일 생성 확인
- [ ] 자동 검증 노트북 결과 검토

### Task 1-2: Phase 3-A 재처리 (2023-01) ⏰ 4분
- [ ] 같은 로직(purpose 제거)으로 2023-01 다시 처리
- [ ] 결과: 72개월 전체 동일 포맷

### Task 1-3: Phase 1 재정제 — LivePOP 5세 단위 ⏰ 10분
- [ ] livepop_full.py: age_5 컬럼 유지, age_10 합산 제거
- [ ] 사유: NIMS contact matrix 5세 단위 호환

### Task 1-4: 정제 후 통합 검증 ⏰ 1시간
- [ ] 학기 중 데이터(2023-05, 2023-10) 추가 분석
- [ ] 0-9, 10-19세 학기 효과 확인

---

## Part 2: Stage 2 — Metapop 프로토타입 (2-4주)

별도 설계 문서: `docs/STAGE2_DESIGN.md`

### Task 2-1: 모델 구조 확정 + 코드 스켈레톤 ⏰ 1주
### Task 2-2: 0-9세, 70+세 정적 모듈 ⏰ 3일
### Task 2-3: 행정동 OD 변환 ⏰ 3일
### Task 2-4: 시뮬레이션 엔진 ⏰ 1주
### Task 2-5: 단위 테스트 + 보존 법칙 검증 ⏰ 3일

---

## Part 3: Stage 3 — ILI Calibration (3-4주)

### Task 3-1: ILI 데이터 정리 ⏰ 2일
### Task 3-2: Deterministic calibration ⏰ 2주
- [ ] β, φ_a, σ, γ 파라미터
- [ ] 2018-2019 시즌으로 fit
- [ ] 정규화 제약: φ_20-29 = 1 (reference)

### Task 3-3: 검증 ⏰ 1주
- [ ] Holdout: 2019-2020 시즌
- [ ] 자연 실험: 2020-2022 거리두기 시기 정책 효과 검증

### Task 3-4 (선택): Stochastic 확장 ⏰ 2주

---

## Part 4: Stage 4 — Sick-Leave 효과 (3-4주)

### Task 4-1: 시나리오 정의 ⏰ 1주
- 병가 사용률 변동 (30% → 70%)
- 학교 폐쇄, 원격수업, 재택근무

### Task 4-2: Spill-over 모델링 ⏰ 2주
- NIMS 12월(학기) vs 2월(방학) 비교

### Task 4-3: 정책 효과 시뮬레이션 ⏰ 1주

---

## Part 5: Stage 5 — ICER 분석 (4-6주)

### Task 5-1: 비용 산출 ⏰ 2주
- 직접의료비, 간접비, 정책 비용

### Task 5-2: QALY 산출 ⏰ 1주

### Task 5-3: ICER 계산 + 민감도 ⏰ 2주
- WTP threshold 5,000만원/QALY

---

## 마일스톤

| 시점 | 목표 |
|---|---|
| ~ 1주 | Part 1 정제 완성 |
| 1-3주 | Stage 2 프로토타입 |
| 1-2개월 | Stage 3 calibration |
| 2-3개월 | Stage 4 sick-leave |
| 3-5개월 | Stage 5 ICER |
| 6-12개월 | 논문 작업 |

---

## 미해결 결정 사항

- [ ] 논문 타겟 (국내 정책 vs 국제 방법론)
- [ ] ILI 시도별 raw data 협조 결과
- [ ] NIMS 설문 Q4 코드 8/9/9997 의미

---

## 데이터 위치 요약

### 서버 (wsson1)
- 원본: `/data_ssd/KT_data_2025/` (RO)
- 정제: `/data_ssd/hwcho/projects/kt_mobility/data/`

### 로컬 (맥북)
- 프로젝트: `~/Documents/python/NIMS/kt_data/`
- 데이터:
  - `data/raw/` — LivePOP 2023, Movement 2023-01
  - `data/mapping/` — 행정동 polygon, 주민등록, cell-admdong
  - `data/external/ili/` — ILI 전국 평균 (2018-2023)
  - `data/external/contact_matrix/` — NIMS raw data 정리본
- 노트북: `notebooks/`
- 출력: `outputs/`
- GitHub: https://github.com/leochok0517/kt_data
