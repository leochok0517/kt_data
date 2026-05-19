# Stage 2: Metapop 인플루엔자 모델 설계

> 갱신: 2026-05-18 (15군 결정)
> 목표: 수도권 행정동 단위 metapop 인플루엔자 모델 프로토타입

---

## 1. 모델 개요

### 핵심 구조
- **공간**: 수도권 1,155개 행정동
- **연령**: 15군 (0-4, 5-9 분리 — 어린이집 vs 초등학교 구분)
  - `0-4, 5-9, 10-14, 15-19, 20-24, 25-29, 30-34, 35-39, 40-44, 45-49, 50-54, 55-59, 60-64, 65-69, 70+`
- **시간 단위**: 일 (day) — 인플루엔자 동학에 충분
- **질병**: 인플루엔자, SEIR + Isolation
- **계절성**: 정상 시기 시즌 (40주차 ~ 다음해 20주차)

### Compartment

```
S^a_i, E^a_i, I^a_i, J^a_i (isolated), R^a_i

a: 연령 (15군)
i: 행정동 (1,155)

전체 상태 변수: 5 × 15 × 1,155 = 86,625개
```

---

## 2. 방정식 (Daily ODE)

```
dS^a_i/dt = -λ^a_i(t) · S^a_i
dE^a_i/dt = +λ^a_i(t) · S^a_i - σ · E^a_i
dI^a_i/dt = +σ · E^a_i - (γ + δ · p_iso(a)) · I^a_i
dJ^a_i/dt = +δ · p_iso(a) · I^a_i - γ · J^a_i
dR^a_i/dt = +γ · (I^a_i + J^a_i)
```

파라미터:
- σ ≈ 1/2 day⁻¹ (잠복기 2일)
- γ ≈ 1/4 day⁻¹ (감염기 4일)
- δ ≈ 1/1 day⁻¹ (격리까지 1일)
- p_iso(a): 연령별 격리 비율 (정책 변수)

### Force of Infection

```
λ^a_i(t) = β · φ_a · Σ_b C^ab(t) · Σ_j π^b_ji(t) · I^b_j / N_eff_j
```

### Contact Matrix (NIMS 시간 가변)

```
C(t) = λ_home(t) · C_home + λ_work(t) · C_work + λ_other(t) · C_other + λ_school(t) · C_school
```

C_home, C_work, C_school, C_other: 15×15, NIMS empirical_matrices_15.npz
- 단위: contacts/person/day
- 컨벤션 (npz): [participant, contact]
- 행렬 합: home=23.26, work=17.03, school=14.24, other=31.77

λ_*(t): 시간 가변 계수 (NIMS notebook 04, 06 참조)

### 연령별 mobility 처리

#### 0-4세, 5-9세 (정적, 자기 행정동)
```
π^a_ji(t) = 1 if i==j else 0  (a=0-4, 5-9)
모든 mixing이 자기 거주 행정동 안에서만
```

차이:
- **0-4세**: school contact 약함 (1.27), home 위주
- **5-9세**: school contact 강함 (3.86), 초등 또래 mixing 큼

#### 10-14, 15-19세 (학교 정적, 학원 mobility)
```
학교 시간: 자기 행정동 내 (정적)
학원/방과후: KT mobility 적용 (age_10=10에서)
```

#### 20-69세 (KT Movement)
```
NIMS 15군 → KT 10세 매핑 (인구비례 분할):
  NIMS [20-24, 25-29] → KT age_10=20
  NIMS [30-34, 35-39] → KT age_10=30
  ... (대칭)
  NIMS [60-64, 65-69] → KT age_10=60

검출률 보정 × 1/0.9
```

#### 70+ (정적, low contact)
```
π^70+_ji(t) = 1 if i==j else 0
```

---

## 3. 입력 데이터

### A. 거주 인구 N^a_i (15군)
주민등록 5세 단위 → 15군 매핑 (직접 매핑, 0-4 + 5-9도 자연)
```
0-4   ← 0-4
5-9   ← 5-9
10-14 ← 10-14
...
65-69 ← 65-69
70+   ← 70-74 + 75-79 + 80+
```

### B. Mobility π^a_ji (20-69세)
KT Movement 72개월 정제본
- 평일/주말 분리
- 일 단위 평균
- KT age_10 → NIMS 15군 (인구 비례 분할)
- 검출률 보정 × 1/0.9

### C. Contact Matrix
파일: `data/external/contact_matrices/empirical_matrices_15.npz`
- Keys: `home`, `work`, `school`, `other`, `age_groups`, `age_labels`
- Shape: 15×15
- 형태: [participant, contact] (npz 컨벤션)

### D. λ(t) 시간 가변
NIMS notebook 04, 06 참조 필요. 일단 기본:
```
학기 평일: λ_home=1, λ_work=1, λ_other=1, λ_school=1
학기 주말: λ_home=1.3, λ_work=0.2, λ_other=1.2, λ_school=0
방학 평일: λ_home=1.1, λ_work=1, λ_other=1.1, λ_school=0.2
방학 주말: λ_home=1.3, λ_work=0.2, λ_other=1.2, λ_school=0
공휴일:    λ_home=1.3, λ_work=0.2, λ_other=1.2, λ_school=0
```

### E. ILI Calibration Target
전국 평균 시즌별 주별 ILI 분율 (2018-2023, 5절기)

---

## 4. Calibration

### Fit 대상 (총 ~18개)
- β: 1개
- φ_a: 14개 (reference 1개 고정)
- γ_report: 1개
- I_0 시즌별: 1-2개

### 제약
- Reference: φ_25-29 = 1
- 인구 가중 평균 = 1
- 양수 제약

### Objective
- 1차: 시계열 RMSE
- 2차: Log-likelihood (Poisson)

### Optimization
- scipy.optimize.minimize (Nelder-Mead)
- 후속: MCMC (emcee)

---

## 5. 코드 구조

```
src/
├── data/
│   ├── load_population.py      # 15군 매핑
│   ├── load_mobility.py        # KT → π (10세→15군 분배)
│   ├── load_contact.py         # NIMS npz 로드
│   ├── time_varying_lambda.py  # λ_*(t)
│   └── load_ili.py
│
├── model/
│   ├── compartments.py
│   ├── dynamics.py
│   ├── foi.py
│   ├── mobility.py
│   └── parameters.py
│
├── simulation/
│   ├── solver.py
│   ├── scenario.py
│   └── output.py
│
├── calibration/
│   ├── objective.py
│   ├── optimizer.py
│   └── validation.py
│
└── viz/
    ├── plots.py
    └── maps.py
```

---

## 6. 검증

### 단위 테스트
- 인구 보존: Σ (S+E+I+J+R) = const
- 비음수
- I_0=0 → 평탄

### 합리성
- 시즌 attack rate 10-30%
- 정점 시기 1-2월
- 연령별 attack rate (어린이 높음)

### Calibration 검증
- Holdout 시즌
- φ_a 안정성
- 자연 실험: 2020-2022 거리두기 시기

### 공간
- 행정동별 attack rate
- 시도별 합산 vs ILI

---

## 7. 잠재 이슈

### Reciprocity (비대칭)
- C_home 비대칭 ~0.75 큼
- 모델 적용 시 보정 고려 또는 그대로

### NIMS notebook 04, 06 참조 필요
- λ_home, λ_work, λ_other 계산법
- C_work mobility 기반 fit

### 시즌 초기 조건
- I_0(t_start) 분포 (uniform vs 인구비례 vs ILI 시작 패턴)
- 면역 잔존 처리

### 계산 시간
- ODE 1 시즌: 수 초~분
- Calibration: 수십 분~수 시간
- 시즌 병렬화 가능

---

## 8. 0-4 vs 5-9 분리의 가치 (15군 결정 근거)

| 항목 | 0-4세 | 5-9세 |
|---|---|---|
| school 일일 접촉 | 1.27 | 3.86 |
| home 일일 접촉 | 2.25 | 2.48 |
| 총 일일 접촉 | 6.22 | 10.26 |
| 주 환경 | 어린이집 부분 등원 | 초등학교 의무교육 |

**정책 시나리오 분리 가능**:
- 어린이집 운영 정책 (0-4세)
- 초등학교 운영 정책 (5-9세)
- 학교 폐쇄 효과 정량화: 주로 5-9세에 큼

---

## 9. 다음 단계

1. **Task 2-1** `src/` 디렉토리 + load_* 모듈 (1주)
2. **Task 2-2** 0-4, 5-9, 70+ 정적 모듈 + KT 15군 분배 (3일)
3. **Task 2-3** Contact matrix λ(t) 구현 (3일)
4. **Task 2-4** ODE solver 통합 (1주)
5. **Task 2-5** 단위 테스트 (3일)

---

## 미확정 사항

- λ_home(t), λ_work(t), λ_other(t) 시간 가변 계산법 (NIMS notebook 04, 06)
- C_work mobility fit 방법 (notebook 06)
- 시즌 초기 감염자 분포
- 면역 잔존 처리 (이전 시즌 회복자)
- 백신 효과 (Stage 2 미포함)
