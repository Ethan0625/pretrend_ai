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
build_similarity_regime(query_start, query_end)
build_similarity_gold(query_start, query_end)
```

For each `query_date`, the builder must:

1. calculate Top-N from the same normalized feature matrix,
2. delete existing rows for that `query_date` and view,
3. insert the new Top-N rows in one transaction.

This avoids `(query_date, rank)` unique conflicts and keeps repeated runs idempotent.

Same input plus same query range must produce the same `(query_date, neighbor_date, rank, score, gap_days)` rows, except for `built_at`.

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
