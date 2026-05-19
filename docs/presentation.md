---
marp: true
theme: default
paginate: true
header: 'KT mobility 기반 전염병 모델링 데이터 정제'
footer: 'NIMS · 2026-05'
size: 16:9
math: mathjax
style: |
  section { font-size: 24px; }
  h1 { color: #1f3a5f; }
  h2 { color: #1f3a5f; }
  table { font-size: 18px; }
  .small { font-size: 18px; }
---

# KT mobility 기반 전염병 모델링을 위한 데이터 정제

## 수도권 metapop 인플루엔자 모델 input 구축

<br>

조형우 · NIMS 수리과학연구소

2026-05

---

## 연구 배경 — Why

**최종 목표**: 수도권 metapop **인플루엔자 모델** + **sick-leave ICER**

- 행정동 단위 (1,148개) × 연령 15군 SEIR 시뮬레이션
- 결석·병가 정책의 비용-효과 정량화 (ICER)

— *데이터 정제 단계*

| 단계 | 상태 |
|---|---|
| 데이터 수집 + 정제 + 표준 로더 | ✓ 본 발표 |
| Metapop 모델 구축 | 다음 프로젝트 (`kt_epimodel`) |
| ILI calibration / 정책 시뮬레이션 | 후속 |



---

## 사용 데이터 — 5종

| 데이터 | 출처 | 기간 | 모델 용도 |
|---|---|---|---|
| **KT LivePOP** | KT 통신 | 2018-01 ~ 2023-12 | 거주 인구 검증 |
| **KT Movement** | KT 통신 (OD) | 2018-01 ~ 2023-12 | mobility π |
| **주민등록** | 행정안전부 | 2023-01 | 공식 인구 N |
| **NIMS Contact** | NIMS 설문  | 2023-12, 2024-02 | contact matrix |
| **ILI** | 질병관리청 표본감시 | 2018 ~ 2023 (5절기) | calibration target |



---

## KT Mobility

**입력**: 250m 통신 셀 → 행정동 매핑 (178,119 셀 → 1,155 행정동)

**처리** (72 개월 일괄):
- `purpose` 코드 제거 — 분류 정확도 낮고 7+(기타) 58%
- 평일 / 주말 분리 (한국 공휴일은 주말로 처리)




![w:780](../outputs/integrated_eda/02_mobility.png)

---

## 데이터 검증 필요성

**질문**. KT mobility가 실제 사람들의 이동을 잡고 있는가?

**검증 방법** — 행정안전부 주민등록과 야간(03–05 시) LivePOP 비교

<br>

> **핵심 가정**: 새벽엔 모두 거주지에 있다.  
> ⇒ 야간 LivePOP ≈ 그 행정동의 KT-검출 거주자  
> ⇒ **KT 검출률 = (야간 LivePOP) / (주민등록 인구)**  

<br>

행정동 × 연령군 별로 검출률을 산출 → 분포 확인.

---

## KT 검출률

![w:780](../outputs/age_validation_2023_01/09_detection_rate_boxplot.png)

<div class="small">

- **10–39세**: 0.92–0.94 ✓ — KT mobility 신뢰 가능
- **0–9세**: **0.15 ❌** — KT가 실제의 약 15%만 잡음
- **70+**: 약 0.55 — 보정 필요

</div>

원인 추정: 휴대전화 미보유, 어린이 단말기 KT 외 점유율, KT 보정 한계.

---

## 연령별 mobility 활용 전략

| 연령군 | KT mobility | 모델 처리 | 근거 |
|---|---|---|---|
| **0–9세** | ❌ | **정적** (자기 행정동 고정) | 검출률 0.15 |
| **10–19세** | 학원만 | 학교 *정적* + 학원 KT | 학교 안 mixing은 위치 무관 |
| **20–69세** | ✓ 적극 활용 | KT π 사용 | 검출률 ~0.9 |
| **70+** | ❌ | **정적** | 휴대전화 보급률·활동 반경 |

<br>

**핵심 통찰**: 학교 안 mixing은 학교 *위치*와 무관 — 같은 학교 내부 contact는 행정동 이동 불필요.  
∴ 0–9세 mobility 부정확해도 모델 동학에 미치는 영향 미미.

---

## NIMS Contact Matrix — 개요

- **출처**: NIMS 호흡기 감염병 밀접접촉 설문 
- **시점**: 2023-12 (학기) + 2024-02 (방학)
- **응답자**: 1,987 명 × 평균 67 건 ≈ 약 **13만 건** 접촉
- **4 setting**: `home` (가족) · `work` (직장) · `school` (학교친구) · `other` (기타)

---
![w:760](../outputs/integrated_eda/03_contact_matrices.png)


---

## ILI 활용 방법

**정상 시기** (2018-19, 2022-23)
- Base 시뮬레이션 calibration target
- $\beta$ (전염력) · 초기 감염자 · 계절성 fitting

**코로나 시기** (2020-21, 2021-22)
- 정책 효과 검증용 **자연 실험**
- 사회적 거리두기 → ILI 90% 감소 재현 가능?

**미해결 (Open)**:
- NIMS contact matrix 절대값 과소 추정 → $\beta$ 로 흡수 vs 외부 scaling
- 시도별 raw data 확보 시 지역 calibration 가능

---

## 최종 모델 input 흐름

| Input | 차원 | 출처 | 처리 |
|---|---|---|---|
| 인구 $N$ | 1,148 × 15 | 주민등록 | 5세 → 15군, 70+ 통합 |
| Mobility $\pi$ | 1,154 × 1,154 × 7 × 24 | KT 생활이동 데이터 | 평일/주말, 가중평균 |
| Contact $C$ | 15 × 15 × 4 | NIMS 설문 | $C(t)$ 시간 가변 |

| ILI | 5 시즌 × 52 주 | 질병청 | calibration |

<br>

→ 다음 프로젝트 [`kt_epimodel`](https://github.com/leochok0517) 에서 metapop 모델 input으로 import.

---

## 결석 · 병가 효과의 명시적 표현

**정책 변수**: $p_{\text{iso}}^{a}$ — 연령군 $a$의 격리 비율

**시나리오 예시**

| 시나리오 | 대상 | $p_{\text{iso}}$ 변화 |
|---|---|---|
| 어린이집 결석 권장 | 0–4 | 0.3 → 0.8 |
| 병가 보조금 | 20–69 | 0.2 → 0.6 |
| 학교 폐쇄 | 5–19 | → 0.8 |

**Spillover 자동 처리**:  
가족 격리 → 직장 → 학교로 이어지는 전파 차단 효과가 contact matrix를 통해 자연스럽게 흘러감.


