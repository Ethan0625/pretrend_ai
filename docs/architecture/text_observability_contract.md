# Text Observability — Contract (SOT)

> 🔄 **Observability Track 자료 — 이름 그대로 observability**
>
> 본 문서는 2026Q2 방향 재정의 후 Observability Track의 핵심 자료로 그대로 유효합니다.
> Text feature(FOMC, SEC, 거시 리포트 텍스트)는 시장 관측·해석 컨텍스트로 활용되며, **observer-only 원칙**(직접 매매 연결 금지)은 유지됩니다.
> Phase 2 explainability layer에서 본 contract를 직접 소비합니다.
> 참조: [`track_separation.md`](./track_separation.md), [`REFACTOR_2026Q2.md`](../../.agent/REFACTOR_2026Q2.md)

## Document Status
| Item | Value |
| --- | --- |
| Status | **Active (Observability 자료, observer-only 원칙 유지)** |
| Structure Policy | 구조는 고정, 기능은 확장 |
| Effective Date | 2026-02-13 |
| Last Updated | 2026-03-04 |
| Change Tracking | docs/changelog.md |

## Capability Matrix
| Capability | Status | Notes |
| --- | --- | --- |
| Bronze text raw SOT | Active | 원문 원본 저장/재처리 보장. 멱등키: `(source, source_doc_id)` |
| Silver 정규화/dedup/quality_flags | Active | v0 구현 범위. clean_text + asset_scope + quality_flags |
| Silver LLM annotation | Reserved (v1+) | topics/tags/tone_spans/evidence_spans — LLM 통합 후 확장 |
| Gold rule-based features (long format) | Active | Strategy Engine 입력. long 포맷 `(trade_date, feature_name, feature_value)` |
| Gold LLM-derived features | Active (v1) | `gold_llm_build.py` — Ollama 로컬, Observer only. §13 참조 |
| VIX/외부 감성 연동 | Reserved (v1+) | 별도 확장 |
| Numeric score tuning | Not supported | 본 계약 범위에서 금지 |

## TOC
- [1. 문서 목적](#1-문서-목적)
- [2. Layer 정의](#2-layer-정의)
- [3. Topic/Tag Allowlist](#3-topictag-allowlist)
- [4. 이벤트 정렬 규칙](#4-이벤트-정렬-규칙)
- [5. Strategy Engine 연동 규칙](#5-strategy-engine-연동-규칙)
- [6. Fail-open 정책](#6-fail-open-정책)
- [7. 품질 KPI](#7-품질-kpi)
- [8. Invariants](#8-invariants)
- [9. Validation / DoD](#9-validation--dod)
- [10. Silver JSON 예시](#10-silver-json-예시)
- [11. 버전 관리](#11-버전-관리)
- [12. v1+ 확장 체크리스트 (Gate D)](#12-v1-확장-체크리스트-gate-d)
- [13. LLM Observer Layer — v1 계약 (Gate D)](#13-llm-observer-layer--v1-계약-gate-d)
- [14. 운영 경계 정책 (v1)](#14-운영-경계-정책-v1)
- [Change History](#change-history)

참조:
- `docs/strategy_engine_design.md`
- `docs/architecture/eod_observability_contract.md`
- `docs/architecture/gold_design_contract.md`
- `docs/architecture/axis_horizon_dependency_contract.md`

## 1. 문서 목적
### 책임
- 텍스트 데이터를 전략 분석/백테스트용 관측 피처로 사용하기 위한 Text Observability Layer 계약을 고정한다.
- Bronze/Silver/Gold 레이어의 입력/출력 경계와 저장 형태를 명확히 한다.
- Strategy Engine 입력을 Gold의 day-level numeric features로 고정한다.

### Non-goals
- 텍스트 기반 점수화/가중치/임계값 설계
- LLM 모델 성능 최적화 설계

## 2. Layer 정의

### 2.1 Bronze Layer — `bronze.text_raw`
목적: 원문 백업 및 재처리 보장(SOT)

**멱등키**: `(source, source_doc_id)` — 동일 문서 재수집 시 중복 미발생 보장

| 컬럼 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `doc_id` | str | Y | PK (`source + source_doc_id` 해시) |
| `source` | str | Y | 출처 식별자 (`sec_edgar`, `fed_fomc`, `fmp_news` 등) |
| `source_doc_id` | str | Y | 소스 내부 문서 ID (멱등키 구성) |
| `canonical_url` | str | Y | 원문 URL |
| `published_at` | datetime | Y | 게시 시각 (UTC) |
| `ingested_at` | datetime | Y | 수집 시각 (UTC) |
| `title` | str | Y | 제목 |
| `body` | str | Y | 본문 원문 |
| `lang` | str | Y | 언어 코드 (예: `en`) |
| `raw_payload_hash` | str | Y | body SHA-256 해시 (재처리 변경 감지) |

파티션: `source` / `ingest_date`

규칙:
- Bronze 원문은 수정하지 않는다.
- Silver/Gold 재처리는 Bronze를 기준으로 수행한다.
- `(source, source_doc_id)` 중복 시 최신 `ingested_at` 기준으로 upsert.
- `sec_edgar` source는 submissions API의 `filings.recent` + `filings.files`를 모두 순회할 수 있어야 한다.
- `filings.files` 요청은 기존 SEC rate-limit(`~10 req/sec`)을 유지하면서 수행한다.

**SEC Filing 유형 (수집 대상)**:

| Form | 설명 | 빈도 | 영향 범위 |
| --- | --- | --- | --- |
| `8-K` | 중요 사건 공시 (임원 변경, M&A, 실적 발표, 구조 변경 등) | 수시 | 개별 종목 → ETF 구성종목 가격 |
| `10-K` | 연차 보고서 (재무제표, 사업 현황, 리스크 요인) | 연 1회 | 개별 종목 → ETF 구성종목 가격 |
| `10-Q` | 분기 보고서 (분기별 재무제표, 경영진 분석) | 연 3회 | 개별 종목 → ETF 구성종목 가격 |

**SEC 문서 활용 정책**:
- v0/v1: Observer only — `filing_risk_burst` 등 rule-based 집계 피처 + LLM annotation 저장
- 개별 종목 이벤트(8-K/10-K/10-Q)는 종목가격→ETF가격 경로로 간접 영향
- 매크로 직접 신호(FOMC)보다 현 ETF 전략에서의 우선순위 낮음
- 향후 Universe-Stock (U0~U3) 파이프라인에서 종목 단위 분석 시 직접 활용 예정

### 2.2 Silver Layer — `silver.text_enriched`
목적: 정규화, dedup, 품질 플래그. v0에서 LLM annotation은 Reserved.

#### v0 필수 필드

| 컬럼 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `doc_id` | str | Y | Bronze FK |
| `canonical_source` | str | Y | 정규화된 출처 (`sec_edgar`, `fed_fomc` 등) |
| `event_date` | date | Y | 이벤트 정렬 거래일 (§4 기준) |
| `asset_scope` | str | Y | 문서 대상 범위 (`macro`, `theme`, `ticker`) |
| `clean_text` | str | Y | HTML 제거 + 정규화된 본문 |
| `quality_flags` | list[str] | Y | 품질 이슈 플래그 (`body_too_short`, `lang_unsupported`, `duplicate_title` 등) |
| `enricher_version` | str | Y | 파서/정규화 코드 버전 |
| `input_hash` | str | Y | Bronze body 해시 (재처리 감지) |

파티션: `event_date`

dedup 기준: `canonical_source + normalized_title + event_date` 조합 동일 시 최신 `ingested_at` 우선.

#### v1+ Reserved (LLM annotation)
> 아래 필드는 LLM 통합 이후 확장. v0에서 저장하지 않음.

| 컬럼 | 설명 |
| --- | --- |
| `summary` | fact 중심 요약 |
| `topics` | Topic allowlist 기반 |
| `tags` | Tag allowlist 기반 |
| `tone_spans` | 문장 단위 tone 근거 |
| `evidence_spans` | topic/tag 근거 스팬 |
| `model_id` | LLM 모델 ID |
| `prompt_version` | 프롬프트 버전 |

#### Tone 정의 (v1+ 참조용)
- Tone은 텍스트의 언어적 논조(language polarity)를 의미하며, 가격 영향(impact)을 의미하지 않는다.
- neutral은 별도 enum 라벨로 저장하지 않는다.
- 문서 단위 tone은 span 단위 근거(`tone_spans[]`)의 존재 여부로 파생한다.

### 2.3 Gold Layer — Text Observability
목적: Silver를 전략 소비용 숫자 피처로 집계 (long 포맷)

#### Gold Daily Features (`gold.text_daily_features`) — v0 스키마

**포맷**: long format — feature 종류별 1행

| 컬럼 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `trade_date` | date | Y | 거래일 |
| `feature_name` | str | Y | feature 식별자 |
| `feature_value` | float | Y | feature 수치 |
| `feature_version` | str | Y | 계산 로직 버전 |
| `coverage_ratio` | float | Y | 해당 날짜 소스 커버리지 (0~1) |
| `staleness_days` | int | Y | 가장 최근 문서 기준 경과 일수 |

**v0 초기 feature 목록**:

| feature_name | 소스 | 계산 방식 |
| --- | --- | --- |
| `macro_hawkish_score` | fed_fomc | FOMC/Fed 문서 내 "hike/tighten/hawkish" 키워드 비율 (0~1) |
| `filing_risk_burst` | sec_edgar | 일별 8-K 건수 rolling z-score (20일 기준) |
| `policy_uncertainty_idx` | sec_edgar + fed_fomc | SEC burst + Fed burst 가중합 (정규화) |

파티션: `year` / `month`

결측 처리:
- 특정 소스 장애 시 해당 소스 feature에 `coverage_ratio=0.0`, `staleness_days`는 마지막 성공일 기준으로 기록.
- 결측이 있어도 파티션 파일 자체는 생성 (fail-open).

#### Gold Event Study (`gold.text_event_study`) — v1+ Reserved
> tone + 수익률 연계 분석. LLM annotation 이후 확장.

| 컬럼 | 설명 |
| --- | --- |
| `doc_id` | Silver FK |
| `symbol` | 관측 ETF 심볼 |
| `event_trade_date` | 이벤트 정렬 거래일 |
| `ret_1d` / `ret_5d` / `ret_21d` | 수익률 |

## 3. Topic/Tag Allowlist

### 3.1 Topic Allowlist
- Topic은 자산/영역을 의미한다. `gold_llm_build.py` 내 `TOPIC_TAXONOMY` dict가 SOT.
- 거시/추상 개념(예: inflation, growth, rates 등)은 `macro` 카테고리에 포함.
- Topic은 multi-label(0..N)이며, v0 권장 최대 3개이다.
- Topic taxonomy 변경은 v1 이상(계약 갱신)에서만 수행한다.

| 카테고리 | Items |
| --- | --- |
| `index` | `sp500`, `nasdaq100`, `dow30`, `russell2000`, `us_dividend` |
| `country` | `south_korea`, `china`, `japan`, `india` |
| `commodity` | `gold`, `gold_miners`, `silver`, `crude_oil`, `oil_producers`, `natural_gas`, `agriculture` |
| `bond` | `us_treasury_long`, `high_yield_bond`, `investment_grade_bond`, `short_treasury`, `tips` |
| `sector` | `energy_sector`, `financials`, `regional_banks`, `semiconductor`, `information_tech`, `health_care`, `materials`, `consumer_discretionary`, `consumer_staples`, `communication_services`, `real_estate`, `utilities`, `nuclear_energy`, `industrials` |
| `macro` | `fed_policy`, `inflation`, `employment`, `treasury_yield` |

### 3.2 Tag Allowlist (Event Type)
- Tag는 사건 유형(event-type)을 의미하며 Topic(자산/영역)과 역할이 겹치지 않는다.
- Tag는 multi-label(0..N)이며, v0 권장 최대 5개이다.
- allowlist 외 Tag는 저장하지 않는다.
- Tag taxonomy 변경은 v1 이상(계약 갱신)에서만 수행한다.
- **SOT**: `gold_llm_build.py` 내 `TAG_TAXONOMY` dict. 아래 목록과 코드가 일치해야 한다.

#### (A) Policy Action
- hike, cut, pause, pivot, qe, qt

#### (B) Forward Guidance
- guidance_change, guidance_raise, guidance_cut

#### (C) Fiscal / Trade
- fiscal_stimulus, regulation_change, tariff

#### (D) Credit / Liquidity
- downgrade, default, spread_widening, liquidity_crunch, bank_run, bailout

#### (E) Corporate Event
- earnings_miss, earnings_beat, layoff, bankruptcy

#### (F) Market Regime
- crash, correction, capitulation, volatility_spike, risk_off, risk_on

## 4. 이벤트 정렬 규칙
| 조건 | 결과 |
| --- | --- |
| `published_ts <= market_close_time` | 당일 `trade_date` |
| `published_ts > market_close_time` | 다음 거래일 |

기준:
- 시장 종료 시간은 US ETF 기준 ET 16:00

## 5. Strategy Engine 연동 규칙
- Strategy Engine은 Silver 배열(`topics`, `tags`, `tone_spans`, `evidence_spans`)을 직접 소비하지 않는다.
- Strategy Engine 입력은 Gold long-format features (`gold.text_daily_features`)로 고정한다.
- **텍스트 feature는 보조 입력**: Strategy Engine 핵심 판단(4축 Axis Feature)은 Macro + EOD 기반. 텍스트 결측 시에도 핵심 로직은 계속 동작한다.
- 흐름:
  - `Bronze (raw) -> Silver (clean/dedup) -> Gold (numeric features) -> Strategy Engine (auxiliary input)`
- Text 데이터는 v0에서 Strategy Engine의 점수/가중치 입력으로 직접 주입하지 않는다. (Numeric score tuning 금지)
- Strategy Engine은 Gold의 long-format numeric features만 소비하며, Silver 구조 변경과 독립이어야 한다.

## 6. Fail-open 정책

텍스트 파이프라인 장애 시 Strategy Engine은 fail-open으로 동작한다.

| 장애 상황 | 대응 |
| --- | --- |
| Bronze 수집 실패 (특정 소스) | 해당 소스 건너뜀. 나머지 소스로 Gold 생성 계속 |
| Silver dedup/파싱 실패 | quality_flags에 기록. 해당 문서 제외 후 계속 |
| Gold feature 결측 (소스 전체 장애) | `coverage_ratio=0.0`, `staleness_days` 갱신. 파티션 파일 생성 유지 |
| Gold feature 없음 | Strategy Engine은 텍스트 feature 없이 계속 동작. 결측 로그만 기록 |

원칙:
- 텍스트 결측은 Strategy Engine 핵심 판단을 차단하지 않는다.
- 결측이 발생해도 Gold 파티션 파일 자체는 항상 생성 (빈 DataFrame 허용).

## 7. 품질 KPI

| 지표 | 기준 | 경고 조건 |
| --- | --- | --- |
| 수집 성공률 | ≥ 95% (소스별) | 소스별 3일 연속 미달 |
| Gold 커버리지 (`coverage_ratio`) | ≥ 90% (거래일 기준) | 주별 평균 미달 |
| Staleness (`staleness_days`) | ≤ 3일 (핵심 feature) | 5일 초과 시 경고 |
| Bronze 중복률 | ≤ 5% (Silver 변환 후) | 10% 초과 시 경고 |

## 8. Invariants
- Bronze 원문은 immutable이며 재처리 SOT로 유지된다.
- `(source, source_doc_id)` 멱등키는 Bronze 수준에서 강제된다.
- Strategy Engine은 Silver 배열을 직접 참조하지 않는다.
- Event-sort는 동일 입력에 대해 deterministic해야 한다.
- Gold feature 결측 시에도 파티션 파일은 생성된다 (fail-open).
- Tone은 언어적 논조이며, 가격 반응(impact)은 Gold 수익률(ret_*)로만 정의된다.

## 9. Validation / DoD
- Bronze 멱등성: 동일 `(source, source_doc_id)` 재수집 → 중복 미발생
- Silver dedup: 동일 이벤트 변형 입력 → 병합 처리
- Gold feature 범위: `macro_hawkish_score` ∈ [0, 1], `filing_risk_burst` z-score 범위
- Gold coverage_ratio: 소스 장애 시 0.0 기록
- Fail-open: 소스 전체 장애 → Gold 파티션 파일 생성 확인
- Contract 회귀: Bronze/Silver/Gold 필수 컬럼 타입 일치

## 10. Silver JSON 예시 (v0 포맷)
```json
{
  "doc_id": "hash://...",
  "canonical_source": "fed_fomc",
  "event_date": "2026-01-29",
  "asset_scope": "macro",
  "clean_text": "The Federal Open Market Committee decided to maintain the target range...",
  "quality_flags": [],
  "enricher_version": "v0.1",
  "input_hash": "sha256://..."
}
```

## 11. 버전 관리
- Silver에는 `enricher_version`, `input_hash`를 필수 저장한다. (v1+에서 `model_id`, `prompt_version` 추가)
- taxonomy(`topic/tag allowlist`) 변경 시 문서 버전 업(계약 갱신)으로 처리한다.

## 12. v1+ 확장 체크리스트 (Gate D)
Text v1+ 확장(외부 API/LLM 포함)은 아래 항목을 모두 충족해야 한다.

### 12.1 External API (Rate-limit / ToS / Secret)
- Rate-limit 완화:
  - 소스별 요청 상한(QPS/RPM) 명시
  - 429/5xx 재시도 정책(지수 백오프, 최대 재시도 횟수) 명시
- ToS/라이선스 준수:
  - 수집 허용 범위(저장/재배포 가능 여부) 문서화
  - 금지 항목(스크래핑 제한, 재배포 제한) 반영
- Secret 관리:
  - 키/토큰은 `.env`/운영 Secret Store로만 주입
  - 코드/테스트/문서 예시는 `DEMO_KEY`, `EXAMPLE_TOKEN`만 허용

### 12.2 Fail-open 보장 (Strategy 독립성)
- Text pipeline 장애/결측 시 Strategy 3-state(Long/Mid/Short) 판단은 독립적으로 계속 동작해야 한다.
- Text feature 결측은 보조 입력 결측으로 처리하고, 핵심 게이트(`run_universe`, `risk_gate`) 의미를 변경하지 않는다.
- Gold text 파티션은 결측이어도 생성되어야 하며(`coverage_ratio=0.0`), 운영 파이프라인 성공 상태를 유지한다.

### 12.3 운영 준비 체크
- 비용 상한(일/월)과 알림 임계 정의
- 장애 fallback 경로(결정론 메시지/기존 규칙 기반 신호) 검증 테스트 존재
- 변경 이력(changelog) + 운영 가이드(operation_guide) 동기화

---

## 13. LLM Observer Layer — v1 계약 (Gate D)

### 13.1 개요
- **역할**: Silver `clean_text`를 LLM으로 분석하여 Gold LLM 피처 생성
- **구현 위치**: `gold_llm_build.py` — Gold 별도 스텝 (Silver, Gold rule-based와 독립)
- **출력**: `gold.text_llm_features/` parquet (long format, `feature_version="v1"`)
- **원칙**: **Observer only** — 전략 신호/게이트/Allocation 판정에 영향 없음

### 13.2 LLM 환경

| 항목 | 값 | 비고 |
| --- | --- | --- |
| 런타임 | Ollama 로컬 서버 | GPU/CUDA는 Ollama 서버가 자체 처리 |
| 기본 모델 | `llama3.1:latest` (8B, 4.7GB) | `OLLAMA_MODEL` env var로 override 가능 |
| 경량화 로드맵 | `llama3.1:latest` → `llama3.2:3b` → Q4_K_M quantize | 성능/속도 트레이드오프 평가 후 전환 |
| 서버 URL | `http://localhost:11434` | `OLLAMA_BASE_URL` env var로 override |
| Python 패키지 | `ollama` (HTTP 클라이언트) | `pytest-pretrend` env에 설치 (`pip install ollama`) |
| CUDA 의존성 | Python 패키지 없음 | Ollama 서버가 GPU 단독 처리 |
| 모델 저장 위치 | `~/.ollama/models/` | conda env 비의존, 전역 공유 |

### 13.3 LLM 처리 파이프라인

```
Silver (clean_text)
  → gold_llm_build.py
      → _batch_annotate()      # 문서 단위 배치 처리 (일 단위 파티션)
          → _ollama_chat()         # Ollama HTTP 호출 (JSON 응답 강제)
          → _parse_llm_response()  # 응답 파싱 + allowlist 필터링 + fallback
  → gold.text_llm_features/   # long format parquet
```

**입력**:
- Silver `clean_text` — `quality_flags == "ok"` 문서 우선 처리 (has_html_markup 등은 skip 허용)
- 파티션 범위: `event_date` 기준

**출력 파티션**: `year` / `month` (Gold rule-based와 동일 구조, 별도 테이블)

### 13.4 LLM 출력 스키마 — `gold.text_llm_features`

용어 고정:
- `llm_feature`: text snapshot만 기반으로 생성된 LLM 산출물 묶음
- `llm_summary`: `llm_feature` 내부의 text-only 요약 필드
- `interpretation_summary`: signal snapshot + text snapshot 결합 해석문(본 계약 범위 밖, Telegram/리포트 레이어)

| 컬럼 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `trade_date` | date | Y | 거래일 (§4 이벤트 정렬 기준) |
| `doc_id` | str | Y | Silver FK |
| `source` | str | Y | 원본 소스 (`fed_fomc`, `sec_edgar` 등). Silver join 없이 source별 필터 가능 |
| `feature_name` | str | Y | `llm_tone` / `llm_topics` / `llm_tags` / `llm_summary` |
| `feature_value` | float | Y | tone: hawkish=1.0 / dovish=-1.0 / neutral=0.0 (`llm_tone`만 유효, 나머지 0.0) |
| `feature_str` | str | N | topics/tags JSON 배열, summary 텍스트 (수치형 아닌 경우) |
| `confidence` | float | Y | LLM 자체 confidence [0.0, 1.0]. 미제공 시 0.5 기본값 |
| `feature_version` | str | Y | `v1` |
| `model_id` | str | Y | 예: `llama3.1:latest` |
| `prompt_version` | str | Y | 프롬프트 템플릿 버전 (예: `text_annotation_v2`) |
| `coverage_ratio` | float | Y | 해당 날짜 Ollama 호출 성공률 (0~1) |
| `staleness_days` | int | Y | 마지막 성공 처리 기준 경과 일수 |

**LLM 응답 포맷 (JSON 강제)**:
```json
{
  "summary": "The Federal Reserve signaled a 25bp rate hike amid persistent inflation.",
  "tone": "hawkish",
  "topics": ["fed_policy", "inflation", "us_treasury_long"],
  "tags": ["hike", "guidance_change"],
  "confidence": 0.87
}
```

**응답 규칙**:
- `tone`: `hawkish` | `dovish` | `neutral` — allowlist 외 값은 `neutral`로 강제
- `topics`: Topic Taxonomy 내 item만 허용. 최대 3개. 저장 시 `feature_str`는 `[{"category": "...", "item": "..."}]`
- `tags`: Tag Taxonomy 내 item만 허용. 최대 5개. 저장 시 `feature_str`는 `[{"category": "...", "item": "..."}]`
- `confidence`: LLM 제공 시 파싱, 미제공 시 0.5 기본값
- `summary`: text-only 문서 요약이며, 시장 signal과 결합된 상위 해석문을 의미하지 않는다

### 13.5 프롬프트 설계 원칙

- **출력 포맷**: JSON strict — Ollama `format="json"` 파라미터 활용
- **시스템 프롬프트**: 역할 정의 + 출력 스키마 명시 + Topic/Tag item 목록(설명 포함) 명시 (할루시네이션 억제)
- **입력 전처리**: `_prepare_text_for_llm()` — 콘텐츠 마커 기반 보일러플레이트 skip + `max_chars=4096` 잘림
- **이중 방어**: allowlist 외 값 → LLM 프롬프트 제한 + 클라이언트 파싱 시 필터링
- **비결정성 허용**: LLM 응답은 non-deterministic. 운영 KPI §13.7로 분포 모니터링

**Tag Selection Rules (프롬프트 명시)**:
- 금리 인상/인하/동결 언급 → `hike`/`cut`/`pause`
- Implementation Notes, 이사회 결의 등 운영 세부사항도 해당 정책 행동으로 분류
- 대차대조표 축소/자산 매입 → `qt`/`qe`

**Few-shot Examples (프롬프트 포함, 3건)**:
1. Fed 금리 인상 → `{"tags": ["hike"]}`
2. Implementation Note 금리 인상 → `{"tags": ["hike"]}`
3. 금리 동결 → `{"tags": ["pause"]}`

**응답 파싱 방어 (`_parse_llm_response`)**:
1. 직접 JSON 파싱 시도
2. 마크다운 코드블록 (`````json ... `````) 내 JSON 추출
3. 첫 `{...}` 블록 추출 (fallback)
4. 모두 실패 시 해당 문서 skip

**Topic Taxonomy (6 categories / 39 items)**:
- `index`: `sp500`, `nasdaq100`, `dow30`, `russell2000`, `us_dividend`
- `country`: `south_korea`, `china`, `japan`, `india`
- `commodity`: `gold`, `gold_miners`, `silver`, `crude_oil`, `oil_producers`, `natural_gas`, `agriculture`
- `bond`: `us_treasury_long`, `high_yield_bond`, `investment_grade_bond`, `short_treasury`, `tips`
- `sector`: `energy_sector`, `financials`, `regional_banks`, `semiconductor`, `information_tech`, `health_care`, `materials`, `consumer_discretionary`, `consumer_staples`, `communication_services`, `real_estate`, `utilities`, `nuclear_energy`, `industrials`
- `macro`: `fed_policy`, `inflation`, `employment`, `treasury_yield`

**Tag Taxonomy (6 categories / 27 items)**:
- `policy_action`: `hike`, `cut`, `pause`, `pivot`, `qe`, `qt`
- `forward_guidance`: `guidance_change`, `guidance_raise`, `guidance_cut`
- `fiscal_trade`: `fiscal_stimulus`, `regulation_change`, `tariff`
- `credit_event`: `downgrade`, `default`, `spread_widening`, `liquidity_crunch`, `bank_run`, `bailout`
- `corporate_event`: `earnings_miss`, `earnings_beat`, `layoff`, `bankruptcy`
- `market_regime`: `crash`, `correction`, `capitulation`, `volatility_spike`, `risk_off`, `risk_on`

### 13.6 Fail-open 정책

| 장애 상황 | 대응 |
| --- | --- |
| Ollama 서버 미실행/미응답 | LLM 스텝 전체 skip. v0 rule-based features 그대로 유지 |
| 특정 문서 LLM 응답 오류 | 해당 doc skip. `coverage_ratio` 감소. 나머지 처리 계속 |
| JSON 파싱 실패 | 해당 문서 skip. 로그 기록 |
| allowlist 외 tone/topic/tag | 클라이언트 필터링 (tone→neutral 강제, 나머지 제거) |
| 응답 지연 > timeout | timeout=30s 기본. skip 처리 후 계속 |

**원칙**:
- Ollama 미실행 시 `gold_llm_build.py`는 warning 로그 후 정상 종료 — 오류로 처리하지 않음
- `gold.text_llm_features` 파티션은 Ollama 미실행 시 생성하지 않아도 됨
- Strategy Engine은 `gold.text_llm_features` 미의존 — 결측 시에도 정상 동작 (§5, §6 규칙 적용)

### 13.7 운영 KPI

| 지표 | 기준 | 경고 조건 |
| --- | --- | --- |
| LLM 처리 성공률 (`coverage_ratio`) | ≥ 80% (일별) | 3일 연속 미달 |
| 평균 처리 시간 | ≤ 5s / 문서 | 10s 초과 시 경고 |
| allowlist 필터 비율 | ≤ 20% | 과다 필터 시 프롬프트 재검토 |
| tone 분포 | hawkish+dovish ≥ 30% | 과도한 neutral 편향 시 프롬프트 재검토 |

### 13.8 Phase 1 Telegram 정책

- **Phase 1** (현재): `gold.text_llm_features` **저장만** — Telegram 발송 없음
- **Phase 1.5** (별도 계약 갱신 필요):
  - 전략 신호 구조체 → 한국어 서술 생성 (numbers → text)
  - 대상 섹션: 시장 컨텍스트, 다음 스텝 가설, 시장 근거, 진단 요약, 전술 그룹 다음 스텝
  - Fail-open: LLM 실패 시 기존 규칙 기반 텍스트 그대로 발송
  - 범위 제한: Allocation 판정/수치에 영향 없음. 서술 생성만
  - 구현 위치: `report_context.py` LLM 연동 (별도 Phase 1.5 계약)

### 13.9 Gate D 충족 현황

| 항목 | 상태 | 근거 |
| --- | --- | --- |
| Rate-limit | ✅ 충족 | 로컬 Ollama — 외부 API 없음 |
| ToS/라이선스 | ✅ 충족 | Meta Llama 3.1 Community License (연구/비상업 허용) |
| Secret 관리 | ✅ 충족 | API 키 없음. `OLLAMA_BASE_URL`, `OLLAMA_MODEL` env var만 사용 |
| Fail-open | ✅ 충족 | §13.6 — Ollama 미실행 시 Strategy 독립 동작 유지 |
| 비용 상한 | ✅ 충족 | 로컬 GPU — 외부 과금 없음 |
| 운영 가이드 | 🔲 미완 | `docs/operation_guide.md` §LLM 운영 섹션 추가 필요 |
| Fallback 테스트 | 🔲 미완 | `test_text_failopen.py` LLM 미실행 시나리오 추가 필요 |

### 13.10 구현 DoD

- `src/pretrend/pipeline/text/gold_llm_build.py` — LLM annotation Gold 스텝 구현
- `conda run -n pytest-pretrend pip install ollama` 완료 확인
- `tests/pipeline/text/test_text_llm.py` — LLM mock 처리 시나리오 (mock ollama 응답, allowlist 필터 검증)
- `tests/pipeline/text/test_text_failopen.py` — Ollama 미실행 시 v0 rule-based 정상 동작 시나리오 추가
- `docs/operation_guide.md` §LLM 운영 섹션 추가 (모델 pull 절차, OLLAMA_BASE_URL 설정)
- `gold.text_llm_features` parquet 스키마 계약 컬럼 일치 확인

---

## 14. 운영 경계 정책 (v1)

### 14.1 Gold Rule-Based Feature (3종)

| Feature | 소비자 | 역할 | 연결 시점 |
| --- | --- | --- | --- |
| `filing_risk_burst` | 저장 전용 (v0) | 8-K 공시 빈도 이상 탐지 | Strategy v1+ 예약 |
| `macro_hawkish_score` | 저장 전용 (v0) | FOMC 기조 수치화 | Strategy v1+ 예약 |
| `policy_uncertainty_idx` | 저장 전용 (v0) | 파생 불확실성 지수 | Strategy v1+ 예약 |

**불변식**:
- v0 Strategy Engine(7-stage)은 Text Gold feature를 소비하지 않는다.
- Text feature 결측/장애가 `INCREASE/DECREASE/HOLD` 판정에 영향을 주어서는 안 된다.

**Strategy 연결 경계 (현행)**:
1. Text feature는 observer-only로 유지한다.
2. Strategy/Paper/Backtest 실행 입력으로 직접 연결하지 않는다.
3. 연결 실험은 별도 계약/실험 문서로만 다루며, 본 계약의 운영 경계를 바꾸지 않는다.

### 14.2 Gold LLM Feature (4종)

| Feature | 소비자 | 역할 |
| --- | --- | --- |
| `llm_tone` | 저장 전용 (Phase 1) | 문서별 hawkish/dovish/neutral |
| `llm_topics` | 저장 전용 (Phase 1) | 문서별 주제 태그 |
| `llm_tags` | 저장 전용 (Phase 1) | 문서별 이벤트 태그 |
| `llm_summary` | 저장 전용 (Phase 1) | 문서별 1줄 요약 |

**Phase 1 정책**:
- Observer-only. 저장만 수행하고 Strategy/Paper/Backtest는 소비하지 않는다.

**Phase 1.5 정책**:
- Telegram 리포트에 당일 텍스트 요약과 `interpretation_summary`를 추가할 수 있다.
- 이 단계에서도 신호 판정/게이트/allocation 입력은 금지한다.

### 14.3 Telegram 반영 범위 (Phase 1.5)

용어:
- Telegram에서 사람이 읽는 최종 문장은 `interpretation_summary`로 부른다.
- `interpretation_summary`는 저장된 `llm_summary`를 포함할 수 있지만, 동일 개념이 아니다.

**적용 섹션**:
- `시장 근거 (Market Evidence)`에 1~2줄 추가
  - 당일 `llm_tone` 분포 요약
  - 당일 `llm_tags` 상위 태그 요약

예시:
- `Fed 문서 2건: hawkish 1, neutral 1`
- `주요 태그: hike, guidance_change`

**적용하지 않는 섹션**:
- `시장 컨텍스트`
- `다음 스텝 가설`
- `진단 요약`

이 섹션들은 기존 규칙 기반 유지가 원칙이다.

**Fail-open**:
- LLM feature가 없으면 해당 줄만 생략한다.
- 기존 메시지 구조와 신호 의미는 유지한다.

**구현 위치**:
- `report_context.py`의 `interpretation_summary` 선택 helper 확장

### 14.4 Backtest 연결 조건

**현재**:
- Backtest runner는 Strategy snapshot만 소비한다.
- Text Gold를 독립적으로 로드하지 않는다.

**연결 전제 (실험 전용)**:
1. Strategy Engine이 먼저 Text feature를 observer-only로 읽을 수는 있다.
2. Backtest runner는 Text Gold를 독립 로드하지 않는다.
3. Text feature 유무에 따른 AB 백테스트는 observer-only 정책의 검증 자료로만 사용한다.

즉, 연결 순서는 `Text -> Strategy -> Backtest` 단방향으로 고정한다.

### 14.5 Airflow 스케줄 정책

| DAG | 스케줄 | LLM task |
| --- | --- | --- |
| `text_pipeline_dag` | 09:30 UTC daily | Gold LLM task 포함 (P1-19) |

**의존성**:
- `text_pipeline_dag`는 `strategy_engine_dag`(10:00 UTC)보다 30분 먼저 실행한다.
- 단, v0에서 Strategy가 Text를 소비하지 않으므로 hard dependency는 아니다.
- 현재 단계에서는 운영 순서 정렬 목적의 soft ordering만 가진다.

---

## Change History
| Date | Summary | References |
| --- | --- | --- |
| 2026-03-04 | §13.4 Gold LLM 스키마에 `source` 컬럼 추가. §13.5 프롬프트 정책 명시 (tag selection rules, few-shot, parser 방어). §3 Topic/Tag Taxonomy를 코드 TOPIC_TAXONOMY/TAG_TAXONOMY와 정합 동기화. §2.1 SEC filing 유형(8-K/10-K/10-Q) 및 활용 정책 명시 | gold_llm_build.py |
| 2026-03-04 | SEC `filings.files` 페이지네이션 지원 명시: `sec_edgar` source는 `recent + files` 순회, date-range skip 최적화와 live SEC 검증 주의사항 추가 | docs/changelog.md |
| 2026-03-04 | §14 운영 경계를 영구 observer-only 원칙으로 정리하고 `interpretation_summary`를 Telegram/리포트 전용 해석문으로 명시 | docs/changelog.md |
| 2026-03-03 | §14 운영 경계 정책 추가: rule-based/LLM feature의 observer-only 범위, Telegram Phase 1.5 반영 범위, Backtest 단방향 연결 규칙 명시 | docs/changelog.md |
| 2026-03-03 | §13 LLM Observer Layer v1 계약 추가: Ollama 로컬(llama3.1:latest), gold_llm_build.py 위치, 출력 스키마, fail-open, Gate D 충족 현황, Phase 1.5 Telegram 정책 초안 | docs/changelog.md |
| 2026-02-27 | v1+ 확장 체크리스트(Gate D) 추가: Rate-limit/ToS/Secret + fail-open Strategy 독립성 + 운영 준비 항목 명시 | docs/changelog.md |
| 2026-02-20 | 수집 전략 v1 확정 반영: Bronze 멱등키 `(source, source_doc_id)` + 신규 필드 추가, Silver LLM → Reserved(v1+) + v0 필수 필드(asset_scope/quality_flags), Gold long 포맷 + 초기 3개 feature, Fail-open 정책 + 품질 KPI 섹션 추가 | docs/changelog.md |
| 2026-02-13 | Text Observability Layer 계약 문서 신규 추가 (Bronze/Silver/Gold + Strategy 연동 규칙) | docs/changelog.md |
