# ADR-003: 3-Layer Market Structure (Long / Mid / Short + Composer)

> 🔄 **Observability Track 자료** — 시장 구조 관측의 핵심 결정. 분류: [`README.md`](README.md)

## Status
Accepted

## Date
2026-01-20 (설계), 2026-02-13 (v1.1 확장)

---

## Context

시장 상태를 하나의 신호로 집약할 것인지, 다중 레이어로 분리할 것인지 결정해야 했다.

전략이 반응해야 하는 시장 변화는 성격이 서로 다른 세 가지 시간 차원에서 발생한다.

- **장기(Long)**: 수개월~수년 단위의 거시 경제 Regime 변화 (금리 사이클, 경기 순환)
- **중기(Mid)**: 수주~수개월 단위의 위험 선호도 변화 (Risk-On/Off 전환)
- **단기(Short)**: 수일 단위의 급격한 시장 충격 (PANIC, RELIEF)

각 차원은 서로 다른 데이터 소스, 다른 임계값, 다른 반응 속도를 가진다.

---

## Decision

**시장 상태 판단을 Long / Mid / Short 3개 독립 엔진으로 분리하고,
Composer가 이를 합성하여 단일 Action 벡터를 생성한다.**

```
ms_long_term_phase   → EXPANSION / RECOVERY / LATE_CYCLE / SLOWDOWN / RECESSION
ms_mid_term_regime   → RISK_ON / NEUTRAL / RISK_OFF
ms_short_term_signal → PANIC / NORMAL / RELIEF

ms_composer          → action(INCREASE/HOLD/DECREASE) + next_invested_ratio + risk_gate
```

각 엔진은 독립적으로 계산되며, 단일 엔진의 데이터 부재가 전체 판단을 무너뜨리지 않는다.
Composer는 3개 엔진 출력을 조합하여 Allocation Engine에 전달할 단일 실행 지시를 생성한다.

---

## Rationale

**1. 시간 차원의 독립성**
거시 Regime(Long)은 수개월 이상 유지되고 FRED 경제지표로 감지된다.
Risk-On/Off(Mid)는 수주 단위로 가격·정책·breadth 신호로 감지된다.
PANIC(Short)은 수일 단위의 급격한 충격으로 일별 수익률·변동성으로 감지된다.
이 세 차원을 하나의 신호로 합산하면 각 차원의 독립적 정보가 손실된다.

**2. 독립 실패 모드**
FRED 데이터가 지연되면 Long Engine이 `UNKNOWN`을 반환하지만,
Mid/Short Engine은 정상 작동한다.
단일 신호 구조라면 하나의 데이터 부재가 전체 판단을 마비시킨다.
3-layer 구조는 각 레이어가 Fail-open으로 독립 작동한다.

**3. 전략 해석 가능성**
"Long=RECESSION, Mid=RISK_OFF, Short=PANIC → DECREASE" 경로는
각 레이어의 기여도를 명확히 설명할 수 있다.
단일 합산 점수로는 어떤 요인이 결정을 주도했는지 추적이 어렵다.

**4. 확장성**
Long Engine v1(z-score 기반), Mid Engine v1.1(3-signal majority vote),
Short Engine v1.1(smallcap_stress 추가) 각각이 독립적으로 버전업됐다.
레이어 간 결합도가 낮아 하나를 개선해도 다른 레이어에 영향이 없다.

**5. 실증 검증**
GFC 2009-03-09: Long=RECESSION, Mid=RISK_OFF, Short=PANIC — 3개 레이어 모두 정확히 감지.
COVID 2020-03: 동일 패턴 감지. Rate Hike 2022: Long=LATE_CYCLE, Short=NORMAL — 과도한 방어 없이 적절히 반응.

---

## Alternatives Considered

| 대안 | 거부 이유 |
|---|---|
| 단일 복합 신호 (점수 합산) | 시간 차원 정보 손실, 디버깅·설명 어려움 |
| Long + Short 2-layer | Mid(Risk-On/Off 전환) 없으면 중기 과매도/과매수 미감지 |
| 4개 이상 레이어 | 레이어 간 상호작용 복잡성 증가, 운영 부담 |
| 단일 ML 앙상블 | ADR-002 거부 이유와 동일 |

---

## Consequences

**수용한 트레이드오프**
- Composer 로직이 추가됨 (3개 출력 → 1개 Action 합성 규칙 필요)
- 레이어별 임계값을 각각 연구/조정해야 함

**얻은 것**
- 레이어 독립 실패 허용 (Fail-open)
- 각 레이어 독립 버전업 가능
- 전략 판단의 3-차원 설명 가능성
- 각 레이어별 독립 Backtest 검증 가능
