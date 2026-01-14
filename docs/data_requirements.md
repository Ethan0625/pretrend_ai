# 📄 Data Requirements Document

**Project:** Pre-Trend Value 기반 자동매매 AI 시스템\
**Document:** Data Requirements\
**Version:** 2026.01.14\
**Purpose:** Universe 생성(U0~U3), EOD Ingest 및 현재 구현된 Macro Silver Feature Layer의 데이터 요구사항과 운영 전제를 정의

---

# 1. Overview

본 문서는 Universe 파이프라인(U0 → U1 → U2 → U3)과
EOD 데이터 수집을 수행하기 위해 필요한 "데이터 항목 (Data Requirements
)"을 정의한다.

데이터는 다음 4개의 카테고리로 구분한다.

* **Macro Data (U0)**: 거시·정책 신호 감지
* **Theme Data (U1)**: 테마 영향력 스코어 산출
* **Stock Level Data (U2/U3)**: 종목 후보 필터링
* **Market Price Data (EOD)**: 최종 Universe 종목 EOD 시계열 저장

---

# 2. Macro Data Requirements (U0)

## 2.1 경제지표(Economic Indicators – Bronze → Silver)

| 항목              | 설명          | 목적             | 출처         |
| --------------- | ----------- | -------------- | ---------- |
| Fed Funds Rate  | 기준금리        | 금리 인상/인하 신호 감지 | FRED       |
| CPI / Core CPI  | 소비자물가지수     | 인플레이션 흐름 파악    | FRED       |
| PPI             | 생산자물가지수     | 비용 상승/하락 신호    | FRED       |
| ISM PMI         | 제조업/서비스 지수  | 경기 속도 판단       | ISM / FRED |
| 고용지표 (NFP, 실업률) | 고용 시장 상황    | 경기 모멘텀 판단      | FRED       |
| GDP 성장률         | 경제 확장/둔화 흐름 | 테마 방향성 판단      | BEA / FRED |

**※ 실제 Universe(U0) 및 이후 파이프라인에서는 Bronze 원천 지표가 아닌, Silver Macro Feature를 사용한다.**

Silver Macro Feature 예:
- yoy, mom, rolling_3m, rolling_12m
- regime (inflation / labor / rate cycle)
- level (전략 입력용 정규화된 수준 값)

## 2.2 정책/이벤트(Policy & Events)

| 항목              | 설명             | 목적          |
| --------------- | -------------- | ----------- |
| FOMC 의사록/발표 요약  | 금리 전망 파악       | 금리 테마 영향    |
| 정부/백악관 산업 정책 발표 | 산업 수혜 예측       | 특정 섹터 테마 강화 |
| 주요 인프라/투자 법안    | CAPEX·산업 테마 감지 | 에너지·인프라 테마  |

## 2.3 뉴스/키워드(News & Keyword Signals)

| 항목            | 설명           | 이유          |
| ------------- | ------------ | ----------- |
| 경제 뉴스 헤드라인    | 주요 이벤트 추출    | 테마 후보 시드 생성 |
| 테마 키워드 빈도     | AI/배터리/반도체 등 | 테마 강도 측정    |
| LLM 기반 요약 키워드 | 의미 기반 신호 분류  | 노이즈 제거      |

## 2.4 Macro Silver Feature 운영 정책
- Macro Silver Feature는 Airflow DAG에 의해 매일 트리거된다.
- 운영 환경에서 실행 누락이 발생할 수 있음을 전제로 설계되었다.
- 각 실행 시:
  - 처리 구간을 직전월 1일 ~ 전일로 설정하여
  - 해당 기간을 롤링 재처리한다.
- Silver Macro Feature는 year/month 파티션 단위 overwrite 전략을 사용하여
  동일 기간 재실행 시 결과 일관성을 보장한다.
- Universe(U0) 및 Gold Layer에서는
  이 Silver Macro Feature를 EOD trade_date 기준 as-of join하여 사용한다.
---

# 3. Theme Data Requirements (U1)

## 3.1 테마 ETF 데이터

| 항목                 | 설명                  | 목적          |
| ------------------ | ------------------- | ----------- |
| 테마 ETF 목록          | AI/반도체/REITs/로보틱스 등 | 테마 정의       |
| ETF 구성 종목(Weights) | Top10~20 종목         | 테마 핵심 종목 추출 |
| ETF 성과(1M/3M/6M)   | 상대강도(RS) 계산         | 테마 우선순위 결정  |
| ETF 자금 유입(Flow)    | 모멘텀 확인              | 테마 스코어 강화   |

## 3.2 뉴스 기반 테마 신호

| 항목           | 설명             |
| ------------ | -------------- |
| 테마 키워드 등장 빈도 | AI, Robotics 등 |
| 테마 관련 이벤트    | 정책/기업 투자 발표    |

---

# 4. Stock-Level Data Requirements (U2/U3)

## 4.1 기본 종목 정보

| 항목             | 설명    | 목적           |
| -------------- | ----- | ------------ |
| Ticker         | 종목 코드 | Universe 식별자 |
| Sector (GICS)  | 산업 분류 | 테마 매핑        |
| Industry       | 세부 산업 | 테마 정밀도 향상    |
| Market Cap     | 시가총액  | 대표성 판단       |
| Average Volume | 평균거래량 | 유동성 필터       |

## 4.2 펀더멘털(Fundamentals)

| 항목                | 설명     | 목적     |
| ----------------- | ------ | ------ |
| Revenue / YoY 성장률 | 매출 증가  | 성장성 판단 |
| Operating Income  | 영업이익   | 수익성 분석 |
| Net Income        | 순이익    | 안정성 판단 |
| EPS / EPS 성장률     | 수익성 개선 | 성장성 점수 |
| Free Cash Flow    | 현금흐름   | 건전성 판단 |
| ROE/ROIC          | 자본효율성  | 경쟁력 측정 |
| Debt Ratio        | 레버리지   | 위험도 평가 |

## 4.3 수급(Flow) Proxy

(*미국 시장은 한국 대비 수급 접근 용이*)

| 항목           | 설명            | 목적       |
| ------------ | ------------- | -------- |
| 거래량 Spike    | 평균 대비 2~5배 증가 | 매수세 포착   |
| OBV          | 거래량 기반 추세     | 매집 가능성   |
| MFI          | 자금 유입지표       | 수급 확인    |
| ETF 구성 비중 변화 | 기관계 자금 흐름     | 테마·종목 수요 |

## 4.4 기술적 흐름(Price Momentum)

| 항목               | 설명      |
| ---------------- | ------- |
| 3M/6M/12M Return | 중기 추세   |
| 52주 고점/저점        | 모멘텀 전환점 |
| 이동평균선(20/60/120) | 추세 변화   |

---

# 5. Market Price Data Requirements (EOD – Bronze)

## 5.1 필수 시세 데이터

| 항목         | 타입    | 설명   |
| ---------- | ----- | ---- |
| trade_date | date  | 거래일  |
| open       | float | 시가   |
| high       | float | 고가   |
| low        | float | 저가   |
| close      | float | 종가   |
| adj_close  | float | 수정종가 |
| volume     | int   | 거래량  |

## 5.2 저장 관련 메타데이터

| 항목           | 설명      |
| ------------ | ------- |
| run_id       | 실행 식별자  |
| ingestion_ts | 적재 시각   |
| source       | API 공급자 |
| symbol       | 종목 코드   |

**※ 실제 Universe 및 Gold Layer에서는 EOD Bronze 데이터가 아닌, Silver EOD Feature를 사용한다.
(EOD Silver Feature는 별도 문서 및 파이프라인에서 정의)**

---

# 6. Minimal Data Set for MVP

초기 MVP에서는 아래 데이터만 수집하면 Universe 생성이 가능하다.

### Macro (Silver Feature 기준)

* Fed Funds Rate 기반 Feature (level, delta_3m, regime)
* CPI / Core CPI 기반 Feature (yoy, regime)
* 실업률 기반 Feature (level, delta_3m, regime)
* (향후) PMI Feature
* (향후) 뉴스 헤드라인

### Theme

* 테마 ETF 목록
* ETF 성과(1M/3M)
* ETF 구성 종목

### Stock

* 매출/영업이익/EPS
* 시총/섹터
* 거래량 기반 수급 proxy(OBV, 거래량 Spike)

### EOD

* OHLCV + adj_close

---

# 7. Data Source Summary

| 데이터      | API/소스                | 난이도   |
| -------- | --------------------- | ----- |
| 경제지표 (Raw) | FRED | 매우 쉬움 |
| Macro Feature (Silver) | 내부 파이프라인 | - |
| 뉴스       | RSS/NewsAPI           | 쉬움    |
| ETF      | Yahoo Finance / ETFdb | 쉬움    |
| ETF Flow | FMP                   | 중간    |
| 펀더멘털     | Finnhub / FMP         | 쉬움    |
| EOD      | Yahoo Finance         | 매우 쉬움 |
