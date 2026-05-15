# EOD Observability Contract v1

Markers: architecture, contract
Status: active

> 🟢 **Infrastructure (공유) — 두 트랙 공통 자산**
>
> EOD Observability SOT(32 ETFs)는 Bronze/Silver/Gold 레이어의 입력 universe이며, Observability Track / Personal Track 양쪽이 read-only로 소비합니다.
> 참조: [`track_separation.md`](./track_separation.md)

## 1. 문서 목적
본 문서는 Pretrend AI의 EOD 관측용 ETF 세트(Observability Set)와 분류/라벨 계약을 고정하기 위한 계약 문서다.
이 계약은 EOD Pipeline, Universe-ETF(Execution Universe), Universe-Stock(U0~U3), Gold Layer가 공통으로 참조하는 단일 기준(SOT)으로 사용된다.

## 2. 용어 정의
### Observability Set
시장 상태(섹터 영향력, 국가/원자재/채권 흐름, rotation)를 안정적으로 관측하기 위한 Always-on ETF 세트.
투자 추천 목록이 아니라 관측 센서 집합이다.

### asset_group / asset_name / asset_subtype
- `asset_group`: 관측 축(대분류) ENUM (`INDEX`, `COUNTRY`, `COMMODITY`, `BOND`, `SECTOR`, `VOLATILITY_INDEX`)
- `asset_name`: 사람이 읽을 수 있는 canonical 이름
- `asset_subtype`: 선택적 2차 분류(세부 해석용)

### Always-on vs Universe-driven 입력
- Always-on: Universe-ETF/Universe-Stock 결과와 무관하게 항상 수집/유지되는 고정 입력
- Universe-driven: Universe 계산 결과에 따라 대상이 변동되는 입력
  - Universe-ETF(현재): Observability ETF 내부 후보 선택
  - Universe-Stock(확장): U0~U3 결과 기반 종목 Universe 변경

## 3. 계약 범위 (Scope & Non-Goals)
### Scope
- Base EOD Observability Set v1 심볼/분류/라벨 계약 고정
- Bronze에서 분류를 1회 확정하고 Silver/Gold로 전파하는 규칙 고정
- Universe-ETF/Universe-Stock/Gold의 read-only 소비 규칙 고정

### Non-Goals
- 신규 ETF 추천/제거 정책 제안
- 전략 알파/매수매도 판단 로직 정의
- 기존 데이터의 일괄 재라벨링 수행

## 4. Observability 분류 체계
### INDEX
미국 대표 지수/스타일(대형주, 기술성장, 배당, 소형주 등)의 시장 방향성과 스타일 로테이션을 관측한다.

### COUNTRY
주요 국가/지역 ETF를 통해 국가 단위 상대강도와 글로벌 자금 이동 축을 관측한다.

### COMMODITY
금/은/원유/가스/농산물 및 관련 주식 ETF를 통해 원자재 가격·인플레이션 민감도를 관측한다.

### BOND
장기 금리 민감 자산 축으로서 금리/듀레이션 레짐을 관측한다.

### SECTOR
미국 섹터 ETF를 통해 섹터 상대강도와 rotation(방어↔경기민감) 흐름을 관측한다.

### VOLATILITY_INDEX
매매 대상이 아닌 변동성 센서 지수다. Short Engine의 PANIC/RELIEF 보조 신호 계산에만 사용한다.

## 5. Base EOD Observability Set v1 (표) — 39 ETFs + 2 Volatility Indices

| symbol | asset_group | asset_name | asset_subtype(옵션) | rationale(한줄) |
| --- | --- | --- | --- | --- |
| SPY | INDEX | SP500 | BROAD_MARKET | S&P500 대표 ETF |
| VOO | INDEX | SP500 | BROAD_MARKET | Vanguard S&P500 ETF |
| QQQ | INDEX | NASDAQ100 | GROWTH_TECH | NASDAQ100 기술/성장 축 관측 |
| DIA | INDEX | DOW30 | VALUE_INDUSTRIAL | 다우존스 산업평균 축 관측 |
| SCHD | INDEX | US_DIVIDEND | DIVIDEND_GROWTH | 배당 성장 스타일 축 관측 |
| IWM | INDEX | RUSSELL2000 | SMALL_CAP | Russell2000 소형주 축 관측 |
| DVY | INDEX | US_DIVIDEND_SELECT | DIVIDEND_YIELD | 배당 선별 수익률 축 관측 |
| VIG | INDEX | US_DIVIDEND_APPRECIATION | DIVIDEND_GROWTH | 배당 성장 품질 축 관측 |
| EWY | COUNTRY | SOUTH_KOREA | EM_ASIA | 한국 시장 축 관측 |
| ASHR | COUNTRY | CHINA | CHINA_A_SHARES | 중국 A주 축 관측 |
| CQQQ | COUNTRY | CHINA | CHINA_TECH | 중국 기술 축 관측 |
| EWJ | COUNTRY | JAPAN | DEVELOPED_ASIA | 일본 시장 축 관측 |
| INDA | COUNTRY | INDIA | EM_ASIA | 인도 시장 축 관측 |
| IAU | COMMODITY | GOLD | PHYSICAL_GOLD | 금 현물 축 관측 |
| GDX | COMMODITY | GOLD_MINERS | GOLD_EQUITY | 금광 주식 축 관측 |
| SLV | COMMODITY | SILVER | PHYSICAL_SILVER | 은 현물 축 관측 |
| USO | COMMODITY | CRUDE_OIL | ENERGY_RAW | 원유 가격 축 관측 |
| XOP | COMMODITY | OIL_PRODUCERS | ENERGY_EQUITY | 에너지 생산기업 축 관측 |
| UNG | COMMODITY | NATURAL_GAS | ENERGY_RAW | 천연가스 가격 축 관측 |
| DBA | COMMODITY | AGRICULTURE | SOFT_COMMODITY | 농산물 가격 축 관측 |
| TLT | BOND | US_TREASURY_20Y | LONG_DURATION | 미국 장기 국채 축 관측 |
| HYG | BOND | US_HIGH_YIELD | HIGH_YIELD | 하이일드 채권 신용 스프레드 축 관측 |
| LQD | BOND | US_INVESTMENT_GRADE | INVESTMENT_GRADE | 투자등급 회사채 축 관측 |
| SHY | BOND | US_TREASURY_1_3Y | SHORT_DURATION | 단기 국채 금리 민감도 축 관측 |
| TIP | BOND | US_TIPS | INFLATION_PROTECTED | 인플레이션 연동 채권 축 관측 |
| XLV | SECTOR | HEALTH_CARE | DEFENSIVE | 헬스케어 섹터 축 관측 |
| XLE | SECTOR | ENERGY | CYCLICAL | 에너지 섹터 축 관측 |
| SOXX | SECTOR | SEMICONDUCTOR | TECH_INDUSTRY | 반도체 섹터 축 관측 |
| XLF | SECTOR | FINANCIALS | CYCLICAL | 금융 섹터 축 관측 |
| KRE | SECTOR | REGIONAL_BANKS | SMALL_BANKS | 지역은행 축 관측 |
| NLR | SECTOR | NUCLEAR | CLEAN_ENERGY | 원자력/클린에너지 축 관측 |
| XLK | SECTOR | INFORMATION_TECH | TECH | 정보기술 섹터 축 관측 |
| XLB | SECTOR | MATERIALS | CYCLICAL | 소재 섹터 축 관측 |
| XLY | SECTOR | CONSUMER_DISCRETIONARY | CYCLICAL | 경기소비재 축 관측 |
| XLP | SECTOR | CONSUMER_STAPLES | DEFENSIVE | 필수소비재 축 관측 |
| XLC | SECTOR | COMMUNICATION_SERVICES | DEFENSIVE_GROWTH | 통신서비스 축 관측 |
| XLRE | SECTOR | REAL_ESTATE | RATE_SENSITIVE | 부동산 섹터 축 관측 |
| XLU | SECTOR | UTILITIES | DEFENSIVE | 유틸리티 섹터 축 관측 |
| XLI | SECTOR | INDUSTRIALS | CYCLICAL | 산업재 섹터 축 관측 |
| ^VIX | VOLATILITY_INDEX | CBOE_VOLATILITY_INDEX | IMPLIED_VOL | 매매 대상 제외, PANIC 신호 계산 전용 |
| ^SKEW | VOLATILITY_INDEX | CBOE_SKEW_INDEX | SKEW | 매매 대상 제외, 꼬리위험/OTM put 수요 센서 |

## 6. 데이터 계약 (Data Contract)
### 6.1 레이어별 라벨 전파 규칙
- Bronze: 분류(`asset_group`, `asset_name`, `asset_subtype`)를 1회 확정
- Silver: Bronze 라벨을 수정 없이 전파
- Gold: Silver 라벨을 수정 없이 전파
- 규칙: 분류는 Bronze에서 1회 확정, 하위 레이어에서 수정 금지

### 6.2 필수 컬럼/타입/허용값
- `asset_group`: TEXT NOT NULL, 허용값 ENUM = `INDEX`, `COUNTRY`, `COMMODITY`, `BOND`, `SECTOR`, `VOLATILITY_INDEX`
- `asset_name`: TEXT NOT NULL
- `asset_subtype`: TEXT NULLABLE (옵션)

### 6.3 분류 매핑 규칙
- 미국지수 → `INDEX`
- 국가별 → `COUNTRY`
- 원자재 → `COMMODITY`
- 채권 → `BOND`
- 섹터별 → `SECTOR`
- 변동성 지수 → `VOLATILITY_INDEX`

## 7. 파티션/경로 정책 (문서로만 기술)
- 파티션은 안정적으로 유지하고, 분류는 컬럼으로 관리한다.
- 분류 변경을 파티션 구조 변경으로 해결하지 않는다.

## 8. Universe-ETF / Universe-Stock 연계 규칙 (Read-only consumer)
- Universe-ETF는 Observability 데이터를 읽기만 하며 입력 라벨을 변경하지 않는다.
- Universe-Stock(U1 단계)에서 섹터 상대강도/rotation proxy 계산 입력으로 사용한다.
- 국가/원자재/채권 관측치 그룹핑도 본 계약 컬럼(`asset_group`, `asset_name`, `asset_subtype`)을 기준으로 수행한다.

## 9. 변경 관리 (Versioning)
- Observability Set 변경은 문서 수정 + `docs/changelog.md` 기록을 필수로 한다.
- 과거 데이터 재라벨링은 원칙적으로 수행하지 않는다.
- 재라벨링이 필요한 예외 상황은 소비자 레이어에서 기간별 룰로 처리한다.
