# Explainability 설계

Markers: architecture, contract
Status: active

> Observability Track P27 SOT. 이 문서는 시장 구조 관측 결과를 설명문으로 변환하는 LLM 설명 계층의 계약을 정의한다.

## 1. 목적과 범위

Explainability 계층은 Postgres에 적재된 observability 데이터를 API와 대시보드에서 사용할 수 있는 구조화된 한국어 설명문으로 변환한다. 설명 대상은 관측된 시장 구조, 과거 유사 구간, 거시 상태이며, 수익률 예측·매매 추천·매수/매도 판단은 생성하지 않는다.

입력은 기존 Postgres mirror/cache table로 제한한다.

- `similarity_regime`
- `similarity_gold`
- `gold_market_state_similarity_feature`
- `gold_macro_features`
- 필요한 경우 정규화된 regime runtime snapshot

P27에서는 외부 뉴스, 소셜 데이터, 웹 데이터, 사용자 채팅 데이터를 수집하지 않는다.

## 2. 불변 조건

이 계층은 관측 설명 전용이다. 예측, 추천, 목표가, 매매 신호를 생성하면 안 된다.

금지 용어:

- `predicted_`
- `forecast_`
- `recommend_`
- `should_buy_`
- `target_price`
- `target_return`
- `buy_signal`
- `sell_signal`
- `trading_signal`

`short_signal_code`, `short_signal_confidence`처럼 기존 관측 schema에 존재하는 이름은 regime 상태 식별자이므로 허용한다. 단, 설명문이 이를 매매 추천 의미로 확장하면 안 된다.

## 3. Provider 경계

P27은 protocol 기반 provider 경계를 둔다. 직접 실행 provider는 `VSCodeCodexProvider`이며, VS Code extension에 포함된 Codex binary를 subprocess로 호출한다. Docker 운영 경로에서는 Airflow가 Codex를 직접 실행하지 않고 `ApiCodexProvider`를 통해 FastAPI internal analyzer endpoint에 위임한다. OpenAI SDK/API는 P27 구현 대상이 아니다.

Gemini와 Ollama는 향후 확장 지점이며 P27 구현 대상은 아니다.

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

Provider 선택:

- `PRETREND_EXPLAINABILITY_PROVIDER`: Airflow `explainability_build_dag` provider. Docker Compose 기본값은 `api_vscode_codex`다.
- `PRETREND_EXPLAINABILITY_ANALYZER_API_URL`: Airflow에서 호출하는 internal analyzer endpoint. 기본값은 `http://api:8000/api/v1/report/explainability/analyze`다.
- `PRETREND_LLM_PROVIDER`: 기본값은 `vscode_codex`다.
- `PRETREND_CODEX_BIN`: Codex binary의 명시 경로다. 비어 있으면 OS별 후보 경로를 자동 탐색한다.
- `PRETREND_CODEX_BIN_DIR`: Docker API mode에서 Linux `codex` executable을 `/opt/pretrend/codex-bin`에 read-only mount하기 위한 host directory다.
- `PRETREND_CODEX_BYPASS_SANDBOX`: API 컨테이너 내부 Codex sandbox를 우회해야 하는 경우에만 `1`로 둔다. 기본 실행은 `workspace-write` sandbox를 사용한다.

호출 정책:

- Host-local 직접 실행은 provider가 주입되지 않았을 때 `get_provider()`를 사용한다.
- Airflow `explainability_build_dag`는 Docker Compose에서 `api_vscode_codex` provider를 사용한다. DAG는 Codex binary를 직접 실행하지 않고 FastAPI internal analyzer endpoint를 호출한다.
- FastAPI `report` router가 Strategy Engine Telegram report analyzer와 같은 `subprocess + --output-last-message` 방식으로 Codex를 실행한다.
- 이 구조는 OS 차이를 흡수하기 위한 것이다. Windows host에서는 VS Code extension의 `codex.exe`/`codex.cmd` 후보를 찾고, Docker API 컨테이너에서는 Linux `codex` 실행 파일을 mount해 사용한다.
- `mock` provider는 pytest와 명시적 manual conf `{"provider": "mock"}` 용도다.
- Dashboard API는 동일한 `use_case`, `query_date`에 mock row와 real row가 함께 있으면 non-mock cache row를 우선 반환한다.

재시도와 timeout:

- call retry: 3회
- backoff: 1s / 2s / 4s
- 기본 call timeout: 60s
- 기본 health check timeout: 10s

Health check 정책:

- `VSCodeCodexProvider.health_check()`는 binary 탐색과 실행 가능 여부를 확인한다.
- `ApiCodexProvider.health_check()`는 internal analyzer API 접근성과 API key 설정을 확인한다.
- DAG task 시작 시 health check가 실패하면 빠르게 실패해야 한다.
- 실제 LLM 응답 생성은 runtime smoke 또는 manual verification 대상이며, unit/DAG integration test는 mock provider를 사용한다.

## 4. Use Case

사용자-facing report는 3종이다.

- similarity
- regime
- macro

Cache `use_case` enum은 similarity가 두 개의 독립 view를 가지므로 4개 값을 가진다.

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

스케줄 근거:

- Gold sync는 11:00 KST에 실행된다.
- Similarity build는 12:00 KST에 실행된다.
- Explainability는 1시간 buffer를 두고 13:00 KST에 실행된다.

기본 일일 실행:

- 기준일은 전일 trade date다.
- 4개 cache use case를 생성한다: `similarity_regime`, `similarity_gold`, `regime`, `macro`

Manual backfill:

- Docker Compose runtime에서는 `.env`/compose 기본값에 따라 `api_vscode_codex` provider를 사용한다.
- 코드 단위 기본값은 test 안정성을 위해 `mock`이다. 따라서 `.env` 없이 module만 import하는 테스트에서는 mock provider가 기본이다.
- DAG conf `{"days_back": N, "provider": "mock"}`는 synthetic/mock cache를 명시적으로 생성할 때만 사용한다.
- Host-local 직접 검증이 필요한 경우 `{"provider": "vscode_codex"}`를 명시할 수 있지만, Docker 운영 경로의 표준은 `api_vscode_codex`다.

과거 전체 backfill 정책:

- 현재 cache identity는 `use_case + query_date + model_id + prompt_version`이다.
- 이 identity는 snapshot, rolling 20D, rolling 120D, full-history-to-date 같은 설명 scope/window를 구분하지 않는다.
- Phase 3 dashboard에서 설명 scope를 확정하고 필요 시 cache/API 계약을 확장하기 전까지 과거 전체 LLM backfill은 실행하지 않는다.
- Phase 3 MVP는 대량 mock 설명을 미리 채우기보다 최신 snapshot 설명 또는 on-demand generation을 우선한다.

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

## 12. 변경 이력

- 2026-05-14: P27-1 initial SOT. `prompt_version=v1`.
