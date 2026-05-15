# Explainability Design

> Observability Track P27 SOT. This document defines the LLM explanation layer for cached market-structure reports.

## 1. Purpose And Scope

The explainability layer turns existing Postgres observability data into structured Korean-language reports for API and dashboard use. It explains observed market structure, historical similarity, and macro conditions. It does not forecast returns, recommend trades, or provide buy/sell guidance.

Inputs are existing Postgres mirror/cache tables only:

- `similarity_regime`
- `similarity_gold`
- `gold_market_state_similarity_feature`
- `gold_macro_features`
- regime runtime snapshots as normalized input where needed

No external news, social, web, or user chat data is collected in P27.

## 2. Invariant

The layer is observation-only. It must not produce predictions, recommendations, target prices, or trading signals.

Forbidden terms:

- `predicted_`
- `forecast_`
- `recommend_`
- `should_buy_`
- `target_price`
- `target_return`
- `buy_signal`
- `sell_signal`
- `trading_signal`

Existing observational schema names such as `short_signal_code` and `short_signal_confidence` are allowed because they are regime-state identifiers, not trading recommendations.

## 3. Provider Boundary

P27 uses a protocol-based provider boundary. The only implemented provider in P27 is `VSCodeCodexProvider`, which wraps the existing VSCode extension Codex binary subprocess pattern. OpenAI SDK/API is not used in P27.

Gemini and Ollama are future extension points, not P27 implementation targets.

```python
class LLMProvider(Protocol):
    model_id: str

    def health_check(self, *, timeout_s: int = 10) -> bool:
        ...

    def call(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        timeout_s: int,
    ) -> str:
        ...
```

Provider selection:

- `PRETREND_LLM_PROVIDER`: default `vscode_codex`
- `PRETREND_CODEX_BIN`: optional explicit Codex binary path

Caller policy:

- Direct explainer calls use `get_provider()` when no provider is injected.
- Airflow `explainability_build_dag` defaults to its in-DAG mock provider unless DAG conf explicitly sets a non-mock `provider`.
- Real LLM DAG runs are manual verification only, for example `{"provider": "vscode_codex"}`.

Retry and timeout:

- call retry: 3 attempts
- backoff: 1s / 2s / 4s
- default call timeout: 60s
- default health check timeout: 10s

Health check policy:

- `VSCodeCodexProvider.health_check()` verifies binary discovery and executable invocation.
- DAG task startup must fail fast if health check fails.
- Actual LLM response generation is optional manual verification; unit and DAG integration tests use mock providers.

## 4. Use Cases

User-facing reports are 3 kinds:

- similarity
- regime
- macro

Cache `use_case` enum has 4 values because similarity has two independent views:

- `similarity_regime`
- `similarity_gold`
- `regime`
- `macro`

## 5. Report Schemas

### 5.1 SimilarityReport

```json
{
  "query_date": "YYYY-MM-DD",
  "view": "regime | gold",
  "summary": "현재 시장 구조와 과거 유사 구간에 대한 1~2문장 관측 요약",
  "neighbors": [
    {
      "neighbor_date": "YYYY-MM-DD",
      "score": 0.92,
      "rank": 1,
      "match_reasons": [
        "장기 국면이 유사합니다.",
        "변동성 구조가 비슷합니다."
      ]
    }
  ],
  "disclaimer": "본 결과는 과거 유사성 관측이며 예측이 아닙니다."
}
```

Pydantic-compatible shape:

- `query_date`: date
- `view`: literal `regime` or `gold`
- `summary`: string
- `neighbors`: list of objects with `neighbor_date`, `score`, `rank`, `match_reasons`
- `disclaimer`: string

### 5.2 RegimeReport

```json
{
  "query_date": "YYYY-MM-DD",
  "ahs_summary": "장기/중기/단기 시장 상태에 대한 관측 요약",
  "market_position": "현재 risk posture와 gate 상태에 대한 관측 설명",
  "transition": "5/10/20/60/120일 sojourn 및 hazard에 대한 관측 설명",
  "disclaimer": "본 설명은 관측이며 매수/매도 추천이 아닙니다."
}
```

Pydantic-compatible shape:

- `query_date`: date
- `ahs_summary`: string
- `market_position`: string
- `transition`: string
- `disclaimer`: string

### 5.3 MacroReport

```json
{
  "query_date": "YYYY-MM-DD",
  "indicators": [
    {
      "indicator_id": "CPI_US_ALL_ITEMS_SA",
      "current_value": 308.7,
      "delta_3m": 1.2,
      "regime": "tightening",
      "narrative": "최근 3개월 기준 상승 압력이 관측됩니다."
    }
  ],
  "disclaimer": "본 설명은 과거 vintage 기반 관측이며 미래 예측이 아닙니다."
}
```

Pydantic-compatible shape:

- `query_date`: date
- `indicators`: list of objects with `indicator_id`, `current_value`, `delta_3m`, `regime`, `narrative`
- `disclaimer`: string

## 6. Prompt Policy

Prompt version starts at `v1`.

`PROMPT_VERSION = "v1"` must be defined in each explainer module. Any prompt text change requires prompt version increment. Cache keys include `prompt_version`, so prompt changes automatically create a separate cache namespace.

### 6.1 Common System Prompt

```text
당신은 시장 구조 관측 시스템의 설명자입니다.
역할은 현재와 과거 데이터의 관측 상태를 한국어로 설명하는 것입니다.

금지:
- 예측
- 매수/매도 추천
- 미래 가격 전망
- should_buy
- target_price
- target_return
- buy_signal
- sell_signal
- trading_signal

허용:
- 과거 관측
- 현재 상태 묘사
- 과거 유사 시기 비교
- 데이터 출처 설명

출력은 한국어로만 작성합니다.
출력은 반드시 제공된 JSON schema와 동일한 JSON 객체여야 합니다.
```

### 6.2 Similarity User Prompt Template

```text
다음 similarity 입력을 기반으로 SimilarityReport JSON을 작성하세요.
view는 regime 또는 gold 중 하나입니다.
Top-N 전체를 설명하지 말고 Top-10 이내 핵심 근거만 요약하세요.
예측, 추천, 목표가격, 매수/매도 신호 표현은 금지합니다.

INPUT_JSON:
{input_json}
```

### 6.3 Regime User Prompt Template

```text
다음 regime 입력을 기반으로 RegimeReport JSON을 작성하세요.
장기/중기/단기 상태, market position, transition hazard를 관측 문장으로 요약하세요.
예측, 추천, 목표가격, 매수/매도 신호 표현은 금지합니다.

INPUT_JSON:
{input_json}
```

### 6.4 Macro User Prompt Template

```text
다음 macro 입력을 기반으로 MacroReport JSON을 작성하세요.
각 indicator의 현재값, 최근 변화, 관측 regime을 간결히 설명하세요.
예측, 추천, 목표가격, 매수/매도 신호 표현은 금지합니다.

INPUT_JSON:
{input_json}
```

## 7. Cache Policy

Table: `explainability_cache`.

Primary key:

- `use_case`
- `query_date`
- `model_id`
- `prompt_version`

Columns:

- `use_case` text, one of `similarity_regime`, `similarity_gold`, `regime`, `macro`
- `query_date` date
- `model_id` text
- `prompt_version` text
- `report_json` JSONB
- `output_hash` text
- `built_at` timestamptz

Hypertable axis:

- `query_date`

Chunk interval:

- 1 year

Cache invalidation:

- prompt text change: increment `prompt_version`
- input data changes: caller decides whether to force refresh
- force refresh: explainer bypasses cache read and upserts new report

## 8. Post-Hoc Invariant Filter

LLM output must be checked immediately after provider response and before cache write.

Implementation contract:

```python
class InvariantViolationError(ValueError):
    pass

def check_invariant_or_raise(text: str) -> None:
    ...
```

The function scans raw response text and serialized parsed JSON for forbidden terms:

- `predicted_`
- `forecast_`
- `recommend_`
- `should_buy_`
- `target_price`
- `target_return`
- `buy_signal`
- `sell_signal`
- `trading_signal`

On violation:

- raise `InvariantViolationError`
- do not write cache
- surface task failure in DAG

## 9. DAG Schedule

DAG: `explainability_build_dag`.

Schedule:

- `0 13 * * *` KST
- `catchup=False`
- `max_active_runs=1`
- task retries: 3

Rationale:

- Gold sync runs at 11:00 KST.
- Similarity build runs at 12:00 KST.
- Explainability runs at 13:00 KST with a 1-hour buffer.

Default daily behavior:

- yesterday trade date
- 4 cache use cases: `similarity_regime`, `similarity_gold`, `regime`, `macro`

Manual backfill:

- DAG conf `{"days_back": N}` uses the mock provider by default
- DAG conf `{"days_back": N, "provider": "mock"}` is equivalent and explicit
- real VSCode Codex calls are optional manual verification with explicit provider conf

Historical full backfill policy:

- Current cache identity is `use_case + query_date + model_id + prompt_version`.
- It does not distinguish explanation scope/window, such as snapshot, rolling 20D, rolling 120D, or full-history-to-date.
- Do not run historical full LLM backfill until the Phase 3 dashboard defines the explanation scope and the cache/API contract is updated if needed.
- Phase 3 MVP should prefer latest snapshot explanation or on-demand generation over prefilled historical mock explanations.

## 10. Validation SQL

Cache row count by use case:

```sql
SELECT use_case, COUNT(*)
FROM explainability_cache
GROUP BY use_case
ORDER BY use_case;
```

Prompt version distribution:

```sql
SELECT use_case, model_id, prompt_version, COUNT(*)
FROM explainability_cache
GROUP BY use_case, model_id, prompt_version
ORDER BY use_case, model_id, prompt_version;
```

Forbidden term scan:

```sql
SELECT use_case, query_date
FROM explainability_cache
WHERE report_json::text ~* '(predicted_|forecast_|recommend_|should_buy_|target_price|target_return|buy_signal|sell_signal|trading_signal)';
```

Latest reports:

```sql
SELECT use_case, query_date, model_id, prompt_version, built_at
FROM explainability_cache
ORDER BY built_at DESC
LIMIT 10;
```

## 11. Implementation Notes

- P27 new modules use direct imports such as `pretrend.observability.explainability.similarity_explainer`.
- `src/pretrend/observability/explainability/__init__.py` should not export new P27 APIs.
- Legacy Telegram report code lives under `legacy_report/`; root legacy files remain shims.
- DB integration tests must skip when Postgres settings or connection are unavailable.

## 12. Change History

- 2026-05-14: P27-1 initial SOT. `prompt_version=v1`.
