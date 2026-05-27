# Historical Similarity Design

Markers: architecture, contract
Status: active

> P26 SOT. Market structure historical similarity는 현재 시장 구조와 과거 시점의 유사성을 관측하기 위한 기능이다. 예측, 추천, 매매 신호 생성에 사용하지 않는다.

## 1. 목적 / 범위 / 불변식

Historical similarity answers one question:

- "이 trade_date의 시장 구조는 과거 어떤 trade_date들과 닮았는가?"

Invariant:

- 예측 금지
- 추천 금지
- 매매 신호 생성 금지

It is an Observability Track feature. It must not create execution guidance, target allocation, forecast, recommendation, or trading signal semantics.

Forbidden variable / column prefixes:

- `predicted_`
- `forecast_`
- `signal_`
- `recommend_`

Outputs are historical neighbor rows only. API/dashboard exposure should describe them as similar past states, not as future outcomes.

## 2. Multi-view Principle

Similarity is computed as two independent views:

- `regime view`: market state / regime structure from canonical market-state features.
- `gold view`: numeric macro + EOD market measurements from Gold Postgres mirror.

The two views must not be concatenated into one vector. They are stored separately in:

- `similarity_regime`
- `similarity_gold`

Reason: regime features and Gold numeric features have different meaning, scale, sparsity, and stability. Separate Top-N outputs preserve interpretability and avoid a high-dimensional Gold vector dominating regime state.

## 3. Regime View Feature Definition

Similarity Engine does not consume raw outputs from `src/pretrend/observability/regime/` directly. It consumes only the canonical table/view:

- `gold_market_state_similarity_feature`

Required grain:

- one row per `trade_date`

Allowed column types:

- numeric features
- boolean flags encoded as numeric
- enum codes with explicit mapping
- one-hot columns for non-directional enum states

Disallowed inputs:

- explanation evidence text
- narrative text
- next-step style judgment
- raw multi-row rotation output
- JSON diagnostic blobs

Rotation is important, but it must be transformed to fixed-width columns before similarity. The similarity universe is keyed by canonical `asset_name`, and volatility sensors are excluded.

Excluded from rotation/gold similarity universe:

- `asset_group = VOLATILITY_INDEX`
- `asset_name = CBOE_VOLATILITY_INDEX`
- `asset_name = CBOE_SKEW_INDEX`

### 3.1 Enum Mappings

Directional risk enum:

| Raw value | Code |
| --- | ---: |
| `RISK_ON` | 1 |
| `NEUTRAL` | 0 |
| `RISK_OFF` | -1 |
| `UNKNOWN` or missing | `NULL` |

Short signal enum:

| Raw value | Code |
| --- | ---: |
| `RELIEF` | 1 |
| `STABLE` | 0 |
| `PANIC` | -1 |
| `UNKNOWN` or missing | `NULL` |

Rotation strength enum:

| Raw value | Code |
| --- | ---: |
| `STRONG` | 1 |
| `NEUTRAL` | 0 |
| `WEAK` | -1 |
| `UNKNOWN` or missing | `NULL` |

Boolean mapping:

| Raw value | Code |
| --- | ---: |
| `True` | 1 |
| `False` | 0 |
| missing | `NULL` |

Long phase is not encoded as an ordinal number. It is a cycle state, so it uses one-hot columns:

- `long_phase_expansion`
- `long_phase_late_cycle`
- `long_phase_slowdown`
- `long_phase_recession`
- `long_phase_recovery`
- `long_phase_unknown`

Unknown or missing long phase values are stored as `NULL` across the long phase
one-hot columns. They are not encoded as neutral.

Bias / next-step enums are excluded from P26 similarity input.

### 3.2 Regime Feature Columns

`gold_market_state_similarity_feature` contains `trade_date`, `built_at`, and the following 61 feature columns.

Core horizon / position features, 13 dimensions:

| Column | Source meaning | Encoding |
| --- | --- | --- |
| `long_phase_expansion` | long phase | one-hot |
| `long_phase_late_cycle` | long phase | one-hot |
| `long_phase_slowdown` | long phase | one-hot |
| `long_phase_recession` | long phase | one-hot |
| `long_phase_recovery` | long phase | one-hot |
| `long_phase_unknown` | long phase | one-hot |
| `mid_regime_code` | `RISK_ON/NEUTRAL/RISK_OFF/UNKNOWN` | risk enum code |
| `short_signal_code` | `RELIEF/STABLE/PANIC/UNKNOWN` | short enum code |
| `long_phase_confidence` | long state confidence | numeric |
| `mid_regime_confidence` | mid state confidence | numeric |
| `short_signal_confidence` | short state confidence | numeric |
| `run_universe_flag` | market-position run universe flag | boolean code |
| `risk_gate_flag` | market-position risk gate flag | boolean code |

Transition numeric features, 11 dimensions:

| Column | Encoding |
| --- | --- |
| `state_age_days` | numeric |
| `sojourn_prob_5d` | numeric |
| `sojourn_prob_10d` | numeric |
| `sojourn_prob_20d` | numeric |
| `sojourn_prob_60d` | numeric |
| `sojourn_prob_120d` | numeric |
| `transition_hazard_5d` | numeric |
| `transition_hazard_10d` | numeric |
| `transition_hazard_20d` | numeric |
| `transition_hazard_60d` | numeric |
| `transition_hazard_120d` | numeric |

Rotation wide features, 37 dimensions:

The source may be multi-row, but the canonical table stores one fixed-width column per `asset_name`. Each observed value uses the rotation strength enum code. Missing or unknown source rows are stored as `NULL` before z-score normalization.

| Column |
| --- |
| `rot_sp500_state_code` |
| `rot_nasdaq100_state_code` |
| `rot_dow30_state_code` |
| `rot_us_dividend_state_code` |
| `rot_russell2000_state_code` |
| `rot_us_dividend_select_state_code` |
| `rot_us_dividend_appreciation_state_code` |
| `rot_south_korea_state_code` |
| `rot_china_state_code` |
| `rot_japan_state_code` |
| `rot_india_state_code` |
| `rot_gold_state_code` |
| `rot_gold_miners_state_code` |
| `rot_silver_state_code` |
| `rot_crude_oil_state_code` |
| `rot_oil_producers_state_code` |
| `rot_natural_gas_state_code` |
| `rot_agriculture_state_code` |
| `rot_us_treasury_20y_state_code` |
| `rot_us_high_yield_state_code` |
| `rot_us_investment_grade_state_code` |
| `rot_us_treasury_1_3y_state_code` |
| `rot_us_tips_state_code` |
| `rot_health_care_state_code` |
| `rot_energy_state_code` |
| `rot_semiconductor_state_code` |
| `rot_financials_state_code` |
| `rot_regional_banks_state_code` |
| `rot_nuclear_state_code` |
| `rot_information_tech_state_code` |
| `rot_materials_state_code` |
| `rot_consumer_discretionary_state_code` |
| `rot_consumer_staples_state_code` |
| `rot_communication_services_state_code` |
| `rot_real_estate_state_code` |
| `rot_utilities_state_code` |
| `rot_industrials_state_code` |

Regime view dimension: 61.

## 4. Gold View Feature Definition

Gold view uses:

- `gold_macro_features`
- `gold_eod_features`

Gold EOD features are keyed by canonical `asset_name`, not raw `symbol`. If multiple symbols map to the same `asset_name`, values are aggregated by `asset_name` and `trade_date` using the mean before vector construction. This handles duplicate canonical names such as `SP500` and `CHINA`.

Excluded from Gold similarity universe:

- `asset_group = VOLATILITY_INDEX`
- `asset_name = CBOE_VOLATILITY_INDEX`
- `asset_name = CBOE_SKEW_INDEX`

### 4.1 Gold EOD Universe

The P26 similarity universe has 37 canonical `asset_name` values:

| asset_name |
| --- |
| `SP500` |
| `NASDAQ100` |
| `DOW30` |
| `US_DIVIDEND` |
| `RUSSELL2000` |
| `US_DIVIDEND_SELECT` |
| `US_DIVIDEND_APPRECIATION` |
| `SOUTH_KOREA` |
| `CHINA` |
| `JAPAN` |
| `INDIA` |
| `GOLD` |
| `GOLD_MINERS` |
| `SILVER` |
| `CRUDE_OIL` |
| `OIL_PRODUCERS` |
| `NATURAL_GAS` |
| `AGRICULTURE` |
| `US_TREASURY_20Y` |
| `US_HIGH_YIELD` |
| `US_INVESTMENT_GRADE` |
| `US_TREASURY_1_3Y` |
| `US_TIPS` |
| `HEALTH_CARE` |
| `ENERGY` |
| `SEMICONDUCTOR` |
| `FINANCIALS` |
| `REGIONAL_BANKS` |
| `NUCLEAR` |
| `INFORMATION_TECH` |
| `MATERIALS` |
| `CONSUMER_DISCRETIONARY` |
| `CONSUMER_STAPLES` |
| `COMMUNICATION_SERVICES` |
| `REAL_ESTATE` |
| `UTILITIES` |
| `INDUSTRIALS` |

EOD numeric features per `asset_name`:

- `ret_5d`
- `ret_20d`
- `vol_20d`
- `vol_60d`
- `ma_ratio_5_20`
- `rsi_14`
- `volume_zscore_20d`

Column naming pattern:

```text
eod_<asset_name_lower>_<feature>
```

Examples:

- `eod_sp500_ret_5d`
- `eod_china_ret_20d`
- `eod_us_treasury_20y_vol_60d`
- `eod_information_tech_rsi_14`

Gold EOD dimension: 37 asset names x 7 numeric features = 259.

### 4.2 Gold Macro Features

Macro indicators:

- `CPI_US_ALL_ITEMS_SA`
- `CPI_US_CORE_SA`
- `US_UNEMPLOYMENT_RATE`
- `US_FED_FUNDS_RATE`
- `US_TREASURY_10Y_YIELD`

Numeric features per indicator:

- `delta_1m`
- `delta_3m`
- `delta_6m`
- `zscore_12m`

Macro regime code:

| Raw value | Code |
| --- | ---: |
| `easing` | 1 |
| `neutral` | 0 |
| `tightening` | -1 |
| `UNKNOWN` or missing | `NULL` |

Macro direction code:

| Raw value | Code |
| --- | ---: |
| `up` | 1 |
| `flat` | 0 |
| `down` | -1 |
| `UNKNOWN` or missing | `NULL` |

Assumption flag:

- `is_assumption_based`: boolean code.

Column naming pattern:

```text
macro_<indicator_id_lower>_<feature>
```

Macro dimension:

- 5 indicators x 4 numeric features = 20
- 5 indicators x `regime_code` = 5
- 5 indicators x `direction_code` = 5
- 5 indicators x `is_assumption_based` = 5
- total = 35

Gold view dimension: 259 EOD + 35 macro = 294.

## 5. Cosine Similarity Metric

Each view uses cosine similarity:

```text
cos(a, b) = dot(a, b) / (norm(a) * norm(b))
```

Expected range after filtering:

- stored scores: `[0, 1]`

Pairs with score `<= 0` are not stored. A zero or negative cosine does not represent a useful historical neighbor for this feature space.

Pseudocode:

```python
def cosine(a, b):
    a_norm = norm(a)
    b_norm = norm(b)
    if a_norm == 0 or b_norm == 0:
        return 0.0
    return dot(a, b) / (a_norm * b_norm)

if score <= 0:
    skip
```

## 6. Top-N Policy

Default Top-N:

- `N = 100`

Stored rank:

- `rank = 1..N`
- `rank = 1` is the highest similarity score for that `query_date`.

Recommended exposure:

- API/dashboard should expose Top-10 by default.
- Top-100 is stored to keep enough context for replay, sampling, and future explanation layers.

## 7. min_gap Policy

Default min gap:

- `min_gap = 30 calendar days`

Rule:

```text
(query_date - neighbor_date).days >= 30
```

Reason:

- Without a gap, adjacent dates dominate Top-N because market structure changes slowly.
- 30 days avoids trivial self-neighbor matches while keeping enough candidate history.

Only historical neighbors are allowed:

```text
neighbor_date < query_date
```

## 8. Missing Value Handling

Normalization is z-score per feature over full available history:

```text
z = (x - mean(feature)) / std(feature)
```

규칙:

- If raw value is missing, keep it missing until normalization.
- After z-score, missing values become `0`.
- In z-score space, `0` means mean replacement.
- If a feature has zero std, normalized values for that feature become `0`.
- If a `trade_date` lacks enough source rows to build either view, exclude that `trade_date` from that view's query set.

Pseudocode:

```python
z = (raw - ref_mean) / ref_std
if missing(z):
    z = 0
```

Unknown enum values are stored as `NULL`, not as directional values. They become
`0` only after normalization, so they do not add artificial directional
contribution to cosine similarity.

## 9. Backfill Chunk Policy

First backfill runs by year.

Memory guard:

- max query chunk size = 252 trade dates

Candidate pool:

- all available candidate dates up to the query date minus `min_gap`
- never includes future dates

Pseudocode:

```python
for year in [2006, 2007, ..., current_year]:
    query_dates = [d for d in trade_dates if d.year == year]
    query_dates = chunk(query_dates, chunk_size=252)

    for query_chunk in query_dates:
        candidate_dates = [
            d for d in trade_dates
            if d <= max(query_chunk) - 30 days
        ]

        for q in query_chunk:
            top_n = compute_topn(
                query_date=q,
                candidate_dates=candidate_dates,
                view=view,
                N=100,
                min_gap=30,
            )
            upsert(top_n)
```

The chunk policy is required for first backfill. Daily scheduled runs use only the recent query window.

## 10. Idempotency

The builder accepts a query date range:

```text
build_market_state_similarity_features_from_db(query_start, query_end)
build_similarity_regime(query_start, query_end)
build_similarity_gold(query_start, query_end)
```

P34 이후 `build_market_state_similarity_features_from_db`가 `gold_macro_features`와 `gold_eod_features`만 읽어 `gold_market_state_similarity_feature`를 먼저 upsert한다. 기본 일일 build는 `query_start - 730 days`부터 `query_end`까지만 읽고, 최종 저장 대상은 `query_start ~ query_end`로 자른다. 이 lookback은 transition/state-age 계열 feature의 과거 맥락을 확보하면서도 전체 history scan을 일일 실행에 강제하지 않기 위한 운영 상한이다.

`build_market_state_similarity_features_from_runtime`는 과거 `data/strategy` snapshot 호환 경로로만 남긴다. `similarity_build_dag`의 기본 task는 이 경로를 호출하지 않는다.

For each `query_date`, the similarity builder must:

1. calculate Top-N from the same normalized feature matrix,
2. delete existing rows for that `query_date` and view,
3. insert the new Top-N rows in one transaction.

This avoids `(query_date, rank)` unique conflicts and keeps repeated runs idempotent.

Same input plus same query range must produce the same `(query_date, neighbor_date, rank, score, gap_days)` rows, except for `built_at`.

## 10.1 Replay Read Model

P35부터 `GET /api/v1/similarity/replay`가 현재 구간과 과거 유사 구간의 EOD 관측 궤적을 같은 상대일 축에서 비교한다.

입력:

- `gold_market_state_similarity_feature`: `view=events`에서 현재 `query_date`와 역사 이벤트 anchor의 regime feature 유사도 계산
- `similarity_regime`, `similarity_gold`: `view=regime|gold`에서 날짜 기반 Top-N neighbor anchor 제공
- `gold_eod_features`: 현재 anchor(`query_date`)와 과거 anchor(`actual_date` 또는 `neighbor_date`) 전후의 EOD 가격 경로

제약:

- `view=events|regime|gold`
- `top_n <= 10`
- `compare_days + forward_days <= 365`
- `symbol`은 단일 선택 자산이다. 화면 표시는 `asset_name` 중심, 내부 식별자는 `symbol` 중심으로 유지한다.
- `top_assets <= 10`
- `ranking_symbols <= 60`
- DB write 없이 read-only로 동작한다.

응답의 `current_path.points[]`는 `query_date`를 0일로, `historical_path.points[]`는 과거 anchor를 0일로 둔 `day_offset` 축을 사용한다. 기본 표시 범위는 현재 구간 `D-60 ~ D`, 과거 구간 `D-60 ~ D+30`이다. 각 path는 anchor일의 `adj_close`를 기준으로 `normalized_return = adj_close / base_adj_close - 1`을 제공한다.

Score semantics:

- `state_similarity_score`: feature 상태 유사도. `events`는 역사 이벤트 catalog와 현재 feature row의 cosine similarity, `regime|gold`는 기존 similarity table의 `score`다.
- `trajectory_similarity_score`: 선택 자산의 현재 normalized return path와 과거 normalized return path를 `D-compare_days ~ D` 구간에서 비교한 cosine similarity다.
- `overlay_assets`: 동일 anchor 기준 `trajectory_similarity_score` 상위 Asset Name의 과거 EOD path다. 기본 화면은 Top 5 overlay를 사용한다.
- `asset_rankings`: 동일 anchor 기준으로 Asset Name별 `trajectory_similarity_score`를 정렬한 보조 ranking이다. 이것은 어떤 자산의 현재 궤적이 해당 과거 구간과 가장 비슷한지 확인하기 위한 관측 surface다.

이 endpoint는 현재와 유사한 역사 이벤트 또는 유사 날짜에서 EOD 경로가 실제로 어떻게 흘렀는지 보여주기 위한 read model이며, anchor 이후 결과를 예측값으로 해석하지 않는다.

### 10.2 Replay Window Policy

P35 replay 화면은 다음 기준을 기본값으로 사용한다.

- 비교 구간과 이후 관측 구간을 분리한다.
  - 기본 비교 구간: `D-60 ~ D`
  - 기본 이후 관측 구간: `D+30`
  - 기본 표시 구간: `D-60 ~ D+30`
- `trajectory_similarity_score`는 기본적으로 `D-60 ~ D` 구간만 사용해 계산한다.
- `D+1 ~ D+30`은 유사도 계산에 쓰지 않고, 과거 유사 구간 이후 실제 흐름을 관측하는 영역으로만 표시한다.
- 기본 화면은 `trajectory_similarity_score` 상위 Asset Name 5개를 overlay한다.
- 사용자는 Asset Name을 직접 선택해 특정 자산의 현재 path와 과거 path를 2-line detail chart로 확인할 수 있어야 한다.
- API는 `compare_days`, `forward_days`, `top_assets` query parameter를 지원한다. 차후에는 이 값을 사용자가 직접 조정할 수 있도록 대시보드 control을 추가할 수 있다.

이 구조의 사용자 해석 흐름은 다음과 같다.

1. 현재 국면이 어떤 역사 이벤트 또는 유사 날짜와 닮았는지 확인한다.
2. 그 anchor 기준으로 현재까지의 `D-60 ~ D` 자산 궤적과 가장 닮은 Asset Name을 확인한다.
3. 과거 유사 구간의 `D+1 ~ D+30` 실제 흐름을 참고해, 강세 지속/약세 전환/반등 같은 관측 시나리오를 점검한다.

주의: 이 기능은 예측 확률이나 매수/매도 신호를 만들지 않는다. `D+30` 영역은 과거 관측 결과이며, 현재 이후의 결과로 해석하면 안 된다.

## 11. DAG Schedule Recommendation

DAG:

- `dags/similarity_build_dag.py`

Schedule:

- `0 12 * * *`
- timezone: KST

Reason:

- Gold Postgres sync runs at 11:00 KST.
- Similarity starts one hour later to provide a buffer.
- DAG has no hard dependency chain to sync DAG.
- `similarity_build_dag` 안에서는 `build_market_state_features`가 `build_regime`보다 먼저 실행되어야 한다. `build_market_state_features`와 `build_gold`는 모두 Gold mirror table을 읽고, `build_regime`은 갱신된 canonical regime feature table에 의존한다.

Daily default query window:

- yesterday minus 5 days through yesterday

Manual backfill:

- accepts `query_start` and `query_end`

## 12. Validation SQL

Row count:

```sql
SELECT COUNT(*) FROM similarity_regime;
SELECT COUNT(*) FROM similarity_gold;
SELECT COUNT(*) FROM gold_market_state_similarity_feature;
```

Idempotency count check:

```sql
SELECT query_date, COUNT(*) AS rows_per_query
FROM similarity_regime
GROUP BY query_date
ORDER BY query_date DESC
LIMIT 10;
```

min_gap violation:

```sql
SELECT COUNT(*) AS violations
FROM similarity_regime
WHERE gap_days < 30;

SELECT COUNT(*) AS violations
FROM similarity_gold
WHERE gap_days < 30;
```

Cosine range:

```sql
SELECT COUNT(*) AS violations
FROM similarity_regime
WHERE score < 0.0 OR score > 1.0;

SELECT COUNT(*) AS violations
FROM similarity_gold
WHERE score < 0.0 OR score > 1.0;
```

Top-N rank check:

```sql
SELECT query_date, COUNT(*) AS row_count, MIN(rank) AS min_rank, MAX(rank) AS max_rank
FROM similarity_regime
GROUP BY query_date
HAVING COUNT(*) > 100 OR MIN(rank) <> 1 OR MAX(rank) > 100;
```

## 13. 변경 이력

| Date | Summary |
| --- | --- |
| 2026-05-13 | 초안 작성. P26-1. |
