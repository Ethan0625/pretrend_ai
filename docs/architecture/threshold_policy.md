# Long Engine z-score Threshold 가변화 정책 — 설계 문서 (v2)

Markers: architecture, contract
Status: reference

> 🟢 **Market Data Platform 관측 정책**
>
> 본 문서는 **Long-cycle regime 분류 임계값 정책**의 설계 reference입니다.
> 투자 의사결정이나 매매 지시가 아니라 read-only observation context로 활용됩니다.
> 참조: [`track_separation.md`](./track_separation.md)

## 문서 상태
| Item | Value |
| --- | --- |
| Status | **Draft — Observability 자료, 설계만, 코드 미구현** |
| Effective Date | 미정 (운영 검증 후 결정) |
| Change Tracking | docs/changelog.md |
| Prerequisite | walk-forward + phase 분포 모니터링으로 필요 조건 확인 후 적용 |

---

## 1. 배경 및 목적

Long Engine v1에서 `z_threshold=0.3` 고정 채택 (v2026.02.20).
고정값 운영 중 다음 상황이 관찰될 경우 이산 상태 전환 정책으로 대응한다.

**필요 조건 (둘 중 하나라도 연속 2년 발생 시 가변화 검토)**:
- `LATE_CYCLE%` > 60% : threshold가 지나치게 억제적 → 민감도 복원 필요
- `S+R%` (SLOWDOWN+RECESSION 합계) < 15% : SLOWDOWN/RECESSION 신호 과소 → 민감도 하향 필요

---

## 2. 이산 상태 설계

### 2.1 허용 상태
```
threshold ∈ {0.0, 0.3}
```
연속값 탐색 금지. 두 이산값 사이에서만 전환.

| 상태 | threshold | 특성 |
| --- | --- | --- |
| 민감 (sensitive) | 0.0 | SLOWDOWN/RECESSION 민감, LATE_CYCLE 감소 |
| 둔감 (damped) | 0.3 | 경계값 LATE_CYCLE 유지, S+R 과다 억제 |

### 2.2 기본값
- 운영 기본: `threshold=0.3` (둔감 상태 유지)
- 전환 후 복귀: cooldown 완료 후 재평가

---

## 3. 전환 트리거 (결정론적)

| 방향 | 조건 | 전환 |
| --- | --- | --- |
| 둔감→민감 | rolling 12개월 `LATE_CYCLE%` > 60% | 0.3 → 0.0 |
| 민감→둔감 | rolling 12개월 `S+R%` < 15% | 0.0 → 0.3 |

**측정 기준**:
- `compute_phase_distribution(group_by="year")` 결과 기반
- rolling 12개월 = 직전 12개월 연환산 기준 (월별 분포 rolling 평균)

**중요**: 두 조건이 동시에 충족되면 현재 상태 유지 (전환 보류).

---

## 4. Cooldown 정책

전환 후 **최소 6개월** 동일 상태 유지.
- 과도한 스위칭(whipsawing) 방지
- 6개월 미만 구간에서 트리거 재충족 시 무시

```
전환 이력:
  last_transition_date: date
  current_threshold: float

전환 가능 조건:
  (today - last_transition_date).months >= 6
```

---

## 5. 미래 구현 구조 (참고용)

```python
@dataclass(frozen=True)
class ThresholdPolicy:
    default_threshold: float = 0.3          # 기본값
    sensitive_threshold: float = 0.0         # 민감 상태
    late_cycle_trigger: float = 0.60         # LATE_CYCLE% 상한
    sr_trigger: float = 0.15                 # S+R% 하한
    cooldown_months: int = 6                 # 최소 유지 기간
    lookback_months: int = 12               # rolling 측정 기간
```

`StrategyEngineConfig` 또는 `build_axis_horizon_state()` 파라미터로 주입.
스냅샷 생성 시 `decision_date` 기준으로 트리거 평가 → `long_z_threshold` 결정.

---

## 6. 구현 보류 조건

아래 두 가지가 모두 충족될 때 구현 착수:
1. walk-forward 분석 결과에서 LATE_CYCLE% 또는 S+R% 이상이 **연속 2년** 관찰
2. 백테스트 재실행으로 가변화 시 성과 개선(CAGR +0.2%p 이상 또는 MDD -1%p 이상) 확인

---

## 변경 이력
| Date | Summary |
| --- | --- |
| 2026-02-21 | 초안 작성 — 이산 상태 {0.0, 0.3}, 트리거, cooldown=6개월, 구현 보류 |
