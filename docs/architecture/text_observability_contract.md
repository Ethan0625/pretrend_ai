# Text Observability — Contract (SOT)

## Document Status
| Item | Value |
| --- | --- |
| Status | Active |
| Structure Policy | 구조는 고정, 기능은 확장 |
| Effective Date | 2026-02-13 |
| Change Tracking | docs/changelog.md |

## Capability Matrix
| Capability | Status | Notes |
| --- | --- | --- |
| Bronze text raw SOT | Active | 원문 원본 저장/재처리 보장 |
| Silver LLM annotation | Active | 배열 기반 저장(유연성 유지) |
| Gold text daily/event features | Active | Strategy Engine 입력은 Gold 숫자 피처만 사용 |
| VIX/외부 감성 연동 | Reserved | v1+ 확장 |
| Numeric score tuning | Not supported | 본 계약 범위에서 금지 |

## TOC
- [1. 문서 목적](#1-문서-목적)
- [2. Layer 정의](#2-layer-정의)
- [3. Topic/Tag Allowlist](#3-topictag-allowlist)
- [4. 이벤트 정렬 규칙](#4-이벤트-정렬-규칙)
- [5. Strategy Engine 연동 규칙](#5-strategy-engine-연동-규칙)
- [6. Invariants](#6-invariants)
- [7. Validation / DoD](#7-validation--dod)
- [8. Silver JSON 예시](#8-silver-json-예시)
- [9. 버전 관리](#9-버전-관리)
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

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `doc_id` | str | PK (`canonical_url + published_ts` 해시) |
| `source` | str | 뉴스/리포트 출처 |
| `canonical_url` | str | 원문 URL |
| `published_ts_utc` | datetime | UTC 게시 시각 |
| `title` | str | 제목 |
| `body` | str | 본문 |
| `lang` | str | 언어 코드 |

규칙:
- Bronze 원문은 수정하지 않는다.
- Silver/Gold 재처리는 Bronze를 기준으로 수행한다.

### 2.2 Silver Layer — `silver.text_enriched`
목적: LLM annotation 결과 저장(topic/tag/tone/evidence)

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `doc_id` | str | Bronze FK |
| `summary` | str | fact 중심 요약 |
| `topics` | list[str] | Topic allowlist 기반 |
| `tags` | list[str] | Tag allowlist 기반 |
| `tone_spans` | list[ToneSpan] | 문장 단위 tone 근거 |
| `evidence_spans` | list[EvidenceSpan] | topic/tag 근거 스팬 |
| `model_id` | str | LLM 모델 ID |
| `prompt_version` | str | 프롬프트 버전 |
| `enricher_version` | str | 코드/파서 버전 |
| `input_hash` | str | body 해시 |

#### Tone 정의 (중요)
- Tone은 텍스트의 언어적 논조(language polarity)를 의미하며, 가격 영향(impact)을 의미하지 않는다.
- neutral은 별도 enum 라벨로 저장하지 않는다.
- 문서 단위 tone은 span 단위 근거(`tone_spans[]`)의 존재 여부로 파생한다.

파생 규칙:
- `has_positive_language = (positive tone_spans 개수 > 0)`
- `has_negative_language = (negative tone_spans 개수 > 0)`
- `fact_only = (not has_positive_language and not has_negative_language)`
- `mixed_tone = (has_positive_language and has_negative_language)`

#### ToneSpan
```json
{
  "polarity": "positive|negative",
  "sentence": "string",
  "start_offset": 0,
  "end_offset": 10
}
```

#### EvidenceSpan
```json
{
  "sentence": "string",
  "start_offset": 0,
  "end_offset": 10,
  "supports": {
    "topics": ["string"],
    "tags": ["string"]
  }
}
```

### 2.3 Gold Layer — Text Observability
목적: Silver 배열을 전략 소비용 숫자 피처로 집계

#### Gold Daily Signals (`gold.text_daily_signals`)
| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `trade_date` | date | 거래일 |
| `doc_count` | int | 해당 날짜 문서 수 |
| `topic_counts` | map(topic→int) | topic별 문서 수 |
| `tag_counts` | map(tag→int) | tag별 문서 수 |
| `pos_tone_span_count` | int | 긍정 tone span 합 |
| `neg_tone_span_count` | int | 부정 tone span 합 |
| `has_any_tag` | bool | `doc_count > 0` |

#### Gold Event Study (`gold.text_event_study`)
| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `doc_id` | str | Silver FK |
| `symbol` | str | 관측 symbol(ETF) |
| `event_trade_date` | date | 이벤트 정렬 거래일 |
| `ret_1d` | float | 1일 수익률 |
| `ret_5d` | float | 5일 수익률 |
| `ret_21d` | float | 21일 수익률 |

노트:
- tone(언어적 뉘앙스)와 가격 반응(ret)은 독립 관측값으로 취급한다.

## 3. Topic/Tag Allowlist

### 3.1 Topic Allowlist (`asset_name` 기반)
- Topic은 `docs/architecture/eod_observability_contract.md`의 `asset_name` allowlist를 Source of Truth로 재사용한다.
- 거시/추상 개념(예: inflation, growth, rates 등)은 v0에서 Topic으로 정의하지 않는다. (필요 시 Tag 또는 별도 분석 축으로 처리)
- Topic은 multi-label(0..N)이며, v0 권장 최대 3개이다.
- Topic taxonomy 변경은 v1 이상(계약 갱신)에서만 수행한다.

`sp500`, `nasdaq100`, `dow30`, `russell2000`, `us_dividend`, `south_korea`, `china`, `japan`, `india`, `gold`, `silver`, `crude_oil`, `natural_gas`, `agriculture`, `us_treasury_long`, `energy_sector`, `financials`, `regional_banks`, `semiconductor`, `information_tech`, `health_care`, `materials`, `consumer_discretionary`, `consumer_staples`, `communication_services`, `real_estate`, `utilities`, `nuclear_energy`

### 3.2 Tag Allowlist (Event Type)
- Tag는 사건 유형(event-type)을 의미하며 Topic(자산/영역)과 역할이 겹치지 않는다.
- Tag는 multi-label(0..N)이며, v0 권장 최대 5개이다.
- allowlist 외 Tag는 저장하지 않는다.
- Tag taxonomy 변경은 v1 이상(계약 갱신)에서만 수행한다.

#### (A) Policy / Monetary
- hike
- cut
- qe
- qt
- guidance_change
- fiscal_stimulus
- regulation_change

#### (B) Credit / Liquidity
- downgrade
- default
- spread_widening
- liquidity_crunch
- bank_run
- bailout

#### (C) Earnings / Corporate
- earnings_miss
- earnings_beat
- guidance_raise
- guidance_cut
- layoff
- bankruptcy

#### (D) Market Stress / Flow
- crash
- capitulation
- volatility_spike
- risk_off
- risk_on

## 4. 이벤트 정렬 규칙
| 조건 | 결과 |
| --- | --- |
| `published_ts <= market_close_time` | 당일 `trade_date` |
| `published_ts > market_close_time` | 다음 거래일 |

기준:
- 시장 종료 시간은 US ETF 기준 ET 16:00

## 5. Strategy Engine 연동 규칙
- Strategy Engine은 Silver 배열(`topics`, `tags`, `tone_spans`, `evidence_spans`)을 직접 소비하지 않는다.
- Strategy Engine 입력은 Gold day-level numeric features(`gold.text_daily_signals`)로 고정한다.
- 흐름:
  - `Silver (array storage) -> Gold (numeric features) -> Strategy Engine`
- Text 데이터는 v0에서 Strategy Engine의 점수/가중치 입력으로 직접 주입하지 않는다. (Numeric score tuning 금지)
- Strategy Engine은 Gold에서 집계된 day-level numeric features만 소비하며, Silver의 배열 구조 변경과 독립이어야 한다.

## 6. Invariants
- Bronze 원문은 immutable이며 재처리 SOT로 유지된다.
- Silver `topics[]`, `tags[]`는 allowlist 외 값을 허용하지 않는다.
- Strategy Engine은 Silver 배열을 직접 참조하지 않는다.
- Event-sort는 동일 입력에 대해 deterministic해야 한다.
- `model_id`, `prompt_version`, `enricher_version`, `input_hash`는 Silver에서 필수 메타다.
- Tone은 언어적 논조이며, 가격 반응(impact)은 Gold 수익률(ret_*)로만 정의된다.

## 7. Validation / DoD
- Topic allowlist 검증: `topics[]` 허용값 준수
- Tag allowlist 검증: `tags[]` 허용값 준수
- Tone span 검증: `sentence`가 Bronze `body` substring과 일치
- Span limit 검증: positive/negative 각 최대 5개
- Parity 검증: span count 파생값과 저장 필드 정합성
- Event-sort 재현성: 동일 입력에서 `event_trade_date` 결정성 보장

## 8. Silver JSON 예시
```json
{
  "doc_id": "hash://...",
  "summary": "Fed raised interest rate by 25bp...",
  "topics": ["us_treasury_long", "sp500"],
  "tags": ["hike", "risk_off"],
  "tone_spans": [
    {
      "polarity": "negative",
      "sentence": "The market reacted sharply to the hike announcement.",
      "start_offset": 120,
      "end_offset": 208
    }
  ],
  "evidence_spans": [
    {
      "sentence": "The Fed raised rates by 25 basis points.",
      "start_offset": 30,
      "end_offset": 72,
      "supports": {
        "topics": ["us_treasury_long"],
        "tags": ["hike"]
      }
    }
  ],
  "model_id": "ollama/llama-3",
  "prompt_version": "v0.1",
  "enricher_version": "v0.1-contract",
  "input_hash": "hash://..."
}
```

## 9. 버전 관리
- Silver에는 `model_id`, `prompt_version`, `enricher_version`, `input_hash`를 필수 저장한다.
- taxonomy(`topic/tag allowlist`) 변경 시 문서 버전 업(계약 갱신)으로 처리한다.

---

## Change History
| Date | Summary | References |
| --- | --- | --- |
| 2026-02-13 | Text Observability Layer 계약 문서 신규 추가 (Bronze/Silver/Gold + Strategy 연동 규칙) | docs/changelog.md |
