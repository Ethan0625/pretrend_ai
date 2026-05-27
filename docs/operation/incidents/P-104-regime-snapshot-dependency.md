Markers: operation
Status: active

# P-104 — Regime similarity runtime snapshot 의존성

## 1. 요약

- ID: `P-104`
- 날짜: 2026-05-27
- 영역: Regime Similarity
- 심각도: Medium
- 상태: Deferred
- 관련 커밋: P32 event similarity / runtime freshness work
- 관련 테스트: API smoke, `/api/v1/meta` freshness check
- 관련 계약 문서:
  - `docs/architecture/runtime_flow.md`
  - `docs/architecture/similarity_design.md`
  - `docs/architecture/track_separation.md`

---

## 2. 깨진 계약

Observability dashboard의 regime similarity는 Observability runtime 안에서 재현 가능하게 생성되어야 한다.

```text
Gold Macro/EOD
-> Observability regime feature builder
-> gold_market_state_similarity_feature
-> similarity_regime
```

---

## 3. 증상

Gold serving mirror는 `2026-05-26`까지 갱신되었지만, `gold_market_state_similarity_feature`와 `similarity_regime`은 `2026-05-21`에 머물렀다.

반면 `similarity_gold`는 Gold mirror를 직접 읽기 때문에 `2026-05-26`까지 정상 갱신됐다.

---

## 4. 기대 동작

Gold Macro/EOD가 최신 날짜까지 갱신되면 Observability regime feature와 regime similarity도 같은 최신 관측일을 따라가야 한다.

---

## 5. 근본 원인

- 코드 경로: `src/pretrend/observability/similarity/runtime_source.py`
- 데이터 경로: `data/strategy/axis_horizon_state`, `market_position`, `next_step_signal`, `what_to_hold`
- 문서/계약 경로: Observability Track과 Personal/Strategy Track 분리 원칙
- 누락된 검증: Gold freshness와 regime similarity freshness가 함께 이동하는지 확인하는 운영 gate 부족
- 잘못된 가정: strategy snapshot이 항상 최신 Gold 관측일을 포함한다고 가정

현재 regime similarity source가 legacy `strategy_job` snapshot에 의존한다. 따라서 Gold mirror가 최신이어도 `strategy_job --date <latest>`가 실행되지 않으면 regime feature가 갱신되지 않는다.

---

## 6. 수정

임시 조치:

- `python -m pretrend.pipeline.strategy_engine.strategy_job --date 2026-05-26 --invested-ratio 0.0`를 실행해 runtime snapshot을 갱신했다.
- 이후 `gold_market_state_similarity_feature`, `similarity_regime`, `similarity_gold`를 `2026-05-26`까지 재생성했다.

구조적 조치는 아직 수행하지 않았다.

---

## 7. 검증

- `/api/v1/meta` 기준:
  - `gold_macro_features.max_trade_date = 2026-05-26`
  - `gold_eod_features.max_trade_date = 2026-05-26`
  - `gold_market_state_similarity_feature.max_trade_date = 2026-05-26`
  - `similarity_regime.max_query_date = 2026-05-26`
  - `similarity_gold.max_query_date = 2026-05-26`
- 대표 API smoke:
  - `/api/v1/regime?trade_date=2026-05-26` -> 200
  - `/api/v1/regime/explain?trade_date=2026-05-26` -> 200
  - `/api/v1/similarity/events?query_date=2026-05-26` -> 200

---

## 8. 예방 / 가드

현재는 Deferred 상태다.

후속 가드:

- Observability 전용 regime runtime snapshot builder를 `strategy_job` 밖으로 분리
- `similarity_build_dag`가 legacy strategy snapshot 없이 `gold_market_state_similarity_feature`를 생성하도록 변경
- Gold freshness와 `similarity_regime` freshness 간 max date 차이를 검증하는 운영 테스트 추가

---

## 9. 남은 부채

- Observability regime runtime snapshot 독립화 필요
- `data/strategy/*` path 의존을 Observability runtime source에서 제거해야 한다.
- 이 작업은 P33 이후 별도 task로 분리한다.

---

## 10. 메모

현재 임시 조치는 운영 freshness를 맞추기 위한 one-off 실행이다. 장기 구조에서는 dashboard read-only 관측 계층이 legacy strategy execution snapshot에 의존하지 않아야 한다.
