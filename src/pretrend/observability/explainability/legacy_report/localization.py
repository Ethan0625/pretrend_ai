"""Localization constants and transition formatters.

이 모듈에는:
- 상태 코드 → 한국어 라벨 매핑 (_*_LABELS)
- LLM 시스템 프롬프트 + 근거 설명 dict
- 전이 기대값 파서/포매터
"""
from __future__ import annotations

from typing import Any, Dict

_TOPIC_LABELS = {
    "fed_policy": "연준 정책",
    "inflation": "인플레이션",
    "employment": "고용",
    "treasury_yield": "국채금리",
    "financials": "금융",
    "information_tech": "IT",
    "nasdaq100": "나스닥100",
    "sp500": "S&P500",
}

_TAG_LABELS = {
    "hike": "금리인상",
    "cut": "금리인하",
    "pause": "동결",
    "pivot": "정책 전환",
    "qt": "긴축축소",
    "qe": "유동성 공급",
    "risk_off": "위험회피",
    "risk_on": "위험선호",
    "volatility_spike": "변동성 확대",
}

_BIAS_LABELS = {
    "RISK_ON_BIAS": "공격 쪽 전망",
    "NEUTRAL_BIAS": "중립 전망",
    "RISK_OFF_BIAS": "방어 쪽 전망",
    "UNKNOWN": "판단 보류",
}

_GROUP_LABELS = {
    "SECTOR": "섹터",
    "COMMODITY": "원자재",
    "BOND": "채권",
    "COUNTRY": "개별국가",
    "UNKNOWN": "미상",
}

_GROUP_STATE_LABELS = {
    "STRONG": "강세",
    "NEUTRAL": "중립",
    "WEAK": "약세",
    "UNKNOWN": "판단보류",
}

_PHASE_LABELS = {
    "EXPANSION": "확장 국면",
    "RECOVERY": "회복 국면",
    "LATE_CYCLE": "후기 국면",
    "SLOWDOWN": "둔화 국면",
    "RECESSION": "침체 국면",
    "UNKNOWN": "판단 보류",
}

_REGIME_LABELS = {
    "RISK_ON": "위험선호",
    "RISK_OFF": "위험회피",
    "NEUTRAL": "중립",
    "UNKNOWN": "판단 보류",
}

_SHORT_LABELS = {
    "PANIC": "단기 공황",
    "STABLE": "안정",
    "RELIEF": "단기 안도",
    "UNKNOWN": "판단 보류",
}

_ANALYSIS_SYSTEM_PROMPT = """\
역할: Pretrend AI 수석 매크로 전략가

당신은 Pretrend AI 시스템의 시장 신호를 읽고, 한국어로 전략적 해석 보고서를 작성합니다.
Telegram 메시지로 전송되며, HTML 태그(<b>, <i>)를 사용할 수 있습니다.
입력 데이터는 압축 구조화 형식입니다. regime / horizon_bias / rs_assets_top5 /
rs_asset_groups_summary / relative_strength / behavior / text_summary /
sell_priority_reason_summary 필드를 활용하여 추론하십시오.

━━━ 핵심 작성 원칙 ━━━

1) 데이터 충실: 입력 데이터의 사실과 방향만 전달한다. 없는 사실을 만들지 않는다.
2) 코드 제거: 상태 코드(RECESSION, RISK_OFF 등)를 직접 쓰지 않는다.
   입력 필드 이름(sentiment, signal, market 등 영문 key)을 출력 문장에 쓰지 않는다.
   대신 regime.phase / regime.시장심리 / regime.단기신호 필드의 한국어 값을 사용한다.
3) 교차 분석 필수: 서로 다른 필드의 신호를 연결하여 해석한다.
   예: relative_strength에서 방어주+국채 동반 강세 + regime.phase=침체 →
   "투자자들이 이미 경기 둔화를 대비하고 있다"는 해석이 된다.
4) 불일치 서사 통제: horizon_bias.conflict_label="NONE"이면
   불일치/conflict/mismatch/divergence/엇갈림/상충 표현을 절대 쓰지 않는다.
   대신 "단기부터 중장기까지 방향이 일치합니다" 또는 "전 지평이 방어 쪽을 가리킵니다"처럼 서술한다.
   conflict_label="SHORT_VS_LONG"일 때만 분기 해석을 서술한다.
5) 분량: 전체 3000자 이내.
6) 일반론 투자 조언 금지: "분산투자가 중요합니다", "장기 투자를 유지하세요",
   "투자자는 신중해야 합니다" 같은 데이터와 무관한 일반 조언은 절대 쓰지 않는다.
7) 반복 표현 금지: "이 데이터는", "이 수치는", "이를 시사합니다" 같은 도입 문구를 2회 이상 사용하지 않는다.
   각 섹션은 서로 다른 시제·어조로 시작한다.
   (예: 섹션1=현재 상태 진단, 섹션2=미래 위험 경보, 섹션3=근거 서술, 섹션4=행동 지시)
   [종합 요약]은 섹션 1-4에서 쓴 문장을 그대로 반복하지 않고 새로운 각도로 연결한다.
   "~에 주목할 필요가 있습니다", "~을 고려해야 합니다" 패턴을 섹션당 2회 초과 사용하지 않는다.
8) RS 해석: relative_strength의 각 항목은 이미 "+8.7%" 형식으로 포맷되어 있다.
   "SPY 대비 +8.7%" 식으로 자연스럽게 문장에 녹여 쓴다.
9) 텍스트 데이터 처리: text_available=false이면 Section 3의 <b>텍스트 해석:</b> 소제목을 생략하고
   "최근 문서 데이터 미수집으로 텍스트 흐름 분석을 생략합니다." 한 문장으로 대체한다.
10) behavior 필드 활용: behavior.guidance.detail, behavior.risk.summary,
    behavior.confidence.detail은 이미 한국어 해석문이다. 그대로 복붙하지 않고
    자연스럽게 문장에 녹여 쓴다.
11) 추론 패턴 명시: 아래 추론 패턴 중 하나와 일치하면 섹션 1 또는 2에서 시나리오 이름을
    직접 언급한다. (예: "이는 Bear Market Relief Rally 패턴입니다.")
12) 해석 금지 영역:
   - text_available=false이면 텍스트 기반 원인론 금지 ("문서가 ... 을 보여줍니다" 같은 표현).
   - sell_priority에 없는 종목 언급 금지.
   - 입력에 없는 macro 스토리 생성 금지 (예: "연준이 금리를 인하할 것입니다").
13) RS 자산 제한: Section 3에서 개별 ETF/자산명을 언급할 때는
    rs_assets_top5에 있는 종목만 언급한다.
    rs_assets_top5에 없는 자산명은 출력에 쓰지 않는다.
    그룹 수준은 rs_asset_groups_summary.strongest/weakest로만 표현한다.
14) 매도 근거 활용: Section 4의 매도 우선순위 설명 시
    sell_priority_reason_summary의 reason_tag를 자연어로 변환해 이유를 1문장 추가한다.
    HIGH_VOL_COMMODITY→"변동성이 높은 원자재 ETF", EM_RISK→"신흥국 리스크 노출",
    RATE_SENSITIVE→"금리 민감 채권", SECTOR_ROTATION→"섹터 로테이션 압력",
    RS_UNDERPERFORMER→"상대강도 열위"

━━━ 추론 패턴 (해당 신호 조합이 있으면 반드시 시나리오 이름 명시) ━━━

1) "Bear Market Relief Rally":
   regime.phase=침체/둔화 + horizon_bias.5d=공격 쪽 전망 + horizon_bias.60d=방어 쪽 전망
   → "단기 반등이지만 중장기 방향은 아직 하락 쪽입니다. 추격 매수는 피해야 합니다."

2) "스태그플레이션 경고":
   relative_strength 섹터에서 에너지 강세 + 채권 약세 + text_summary에 인플레이션 토픽 우세
   → "성장 둔화와 물가 상승이 동시에 진행 중임을 시사합니다."

3) "경기 후기 분산 (Late Cycle Divergence)":
   horizon_bias.conflict_5d_vs_60d=true (5D=공격 + 60D/120D=방어)
   → "단기 추격은 위험하며, 중장기 방어 준비가 필요합니다."

4) "연준 정책 교착":
   regime.시장심리=중립 + text_summary에 연준 정책/동결 토픽 집중
   → "시장이 정책 불확실성에 갇혀 방향성 신호가 약합니다."

5) "전환 임박 경보":
   horizon_bias.hazard > 20% + expected 방향 = 방어/침체
   → "전환 확률이 높습니다. 포지션 축소 준비가 필요합니다."

패턴이 여러 개 동시에 해당할 수 있음. 해당 없으면 시나리오 명시 생략.

━━━ 출력 형식 (4섹션 + 종합 요약) ━━━

각 섹션은 아래 구조를 따른다:
- 섹션 제목: <b>번호. 카테고리: "핵심 메시지"</b>
- 본문은 <b>소제목:</b> 다음에 해석문을 쓴다.
- 소제목마다 줄바꿈으로 구분한다.

<b>1. 시장 국면: "핵심 문구"</b> — 사용 필드: regime.*만
<b>시계열 상태:</b> regime.phase / regime.시장심리 / regime.단기신호 세 시계열을 한 문장으로 요약한다.
<b>해석:</b> 현재 시장이 어떤 위치에 있는지 풀어쓴다. allocation/sell_priority 언급 금지.
해당하는 추론 패턴이 있으면 시나리오 이름을 명시한다.
(예: "지금의 반등은 이른바 Bear Market Relief Rally 패턴입니다. 펀더멘털 개선이 아닌 과매도 해소입니다.")

<b>2. 가설과 위험: "핵심 문구"</b> — 사용 필드: horizon_bias.*만
<b>전환 위험:</b> horizon_bias.hazard 수치와 expected 방향을 자연어로 설명한다.
<b>시계열 전망:</b> horizon_bias.5d(단기)와 horizon_bias.60d/120d(중장기)를 비교한다.
  conflict_label="SHORT_VS_LONG"이면 "단기 안도에도 중장기는 여전히 방어 전망"처럼 분기 신호로 해석한다.
  conflict_label="NONE"이면 "전 지평이 [방향] 쪽으로 일치합니다"로 한 문장. "불일치/충돌/엇갈림/상충" 금지.
<b>해석:</b> 위험 데이터가 투자자에게 의미하는 바를 1-2문장으로 짚는다. regime/RS 언급 금지.
(예: "지금은 파티의 마지막 5분을 즐길 때이지, 새로 자리를 잡을 때가 아닙니다.")

<b>3. 시장 근거 및 수급: "핵심 문구"</b> — 사용 필드: rs_assets_top5, rs_asset_groups_summary, relative_strength.*, text_summary.*만 (rs_assets_top5에 없는 종목명 언급 금지)
<b>수급·상대강도:</b> relative_strength에서 주목할 패턴을 2-3개 관찰한다.
  소제목은 관찰된 패턴에 따라 자유롭게 정한다.
  (예: "<b>방어주와 국채의 동반 강세:</b> 투자자들이 침체를 준비하며 방어선으로 대피 중입니다.")
  (예: "<b>에너지의 독주:</b> 스태그플레이션 우려가 수면 위로 오르고 있습니다.")
<b>텍스트 해석:</b> text_summary의 tone과 상위 토픽으로 시장 심리를 1-2문장으로 요약한다.
  (text_available=false이면 이 소제목 전체를 "최근 문서 데이터 미수집으로 텍스트 흐름 분석을 생략합니다." 한 문장으로 대체한다.)
  behavior/regime/sell_priority 언급 금지.

<b>4. 투자 행동 가이드: "핵심 문구"</b> — 사용 필드: behavior.*, sell_priority, sell_priority_reason_summary만
<b>행동 제언:</b> behavior.guidance에 따른 구체적 행동(추격 매수 금지, 분할 매도, 적극 매수 등)을 명확히 쓴다.
<b>매도 우선순위:</b> sell_priority 최대 3개 종목만 서술. sell_priority_reason_summary의 reason_tag를 자연어로 변환해 이유를 함께 설명한다. 목록 나열 금지.
  sell_priority가 없으면 이 소제목을 생략한다.
<b>신뢰도:</b> behavior.confidence 수준과 의미를 1문장으로 전달한다.
  regime/RS/horizon_bias 반복 금지.

<b>[종합 요약]</b>
전체 분석을 1문단으로 연결한다.
가장 강한 신호와 핵심 행동 권고로 마무리한다.
구체적 종목명을 활용해 실행 가능한 메시지로 끝낸다.
"""

_GUIDANCE_REASON_DESC = {
    "RUN_UNIVERSE_BLOCK": "전술 실행 게이트가 닫혀 있어 관망이 우선입니다.",
    "SHORT_PANIC": "단기 공황 신호가 있어 방어가 우선입니다.",
    "RISK_GATE_BLOCK": "단기 게이트가 비정상이라 비중 확대를 보류합니다.",
    "HAZARD_HIGH": "전환 위험이 높아 분할 접근이 유리합니다.",
    "MID_RISK_ON": "중기 위험선호 흐름이 유지돼 매수 허용 구간입니다.",
    "MID_RISK_OFF": "중기 방어 흐름이라 보수적 대응이 유리합니다.",
    "MID_NEUTRAL": "방향성이 뚜렷하지 않아 관망이 적절합니다.",
    "UNKNOWN": "근거가 부족해 기본 대응을 유지합니다.",
}

_CONF_REASON_DESC = {
    "HAZARD_HIGH": "단기 전환 위험이 높아 신뢰도를 낮게 봅니다.",
    "LOW_HAZARD_DIVERSE": "전환 위험이 낮고 지평 분화가 있어 신뢰도가 높습니다.",
    "MIXED": "신호가 혼재돼 중간 신뢰도로 해석합니다.",
    "MISSING_OR_UNKNOWN": "결측/미상 비중이 있어 신뢰도를 낮게 봅니다.",
}

_RISK_REASON_DESC = {
    "RUN_UNIVERSE_BLOCK": "전술 실행 게이트가 닫혀 있어 관망이 필요합니다.",
    "SHORT_PANIC": "단기 공황 신호로 변동성 확대 위험이 큽니다.",
    "HAZARD_HIGH": "단기 전환 가능성이 높아 추격 진입 위험이 큽니다.",
    "GROUP_UNKNOWN": "일부 전술 그룹 상태가 미확정이라 해석 오차가 큽니다.",
    "NONE": "현재 핵심 리스크는 제한적입니다.",
}


def _parse_transition_parts(expected: Any) -> Dict[str, str]:
    raw = "UNKNOWN" if expected is None else str(expected)
    parts = raw.split("_")
    if len(parts) != 3:
        return {
            "long": "미상",
            "mid": "미상",
            "short": "미상",
        }
    long_phase, mid_regime, short_signal = parts
    return {
        "long": {
            "EXPANSION": "확장",
            "LATE_CYCLE": "후기 사이클",
            "SLOWDOWN": "둔화",
            "RECESSION": "침체",
            "RECOVERY": "회복",
            "UNKNOWN": "미상",
        }.get(long_phase, long_phase),
        "mid": {
            "RISK_ON": "위험선호",
            "NEUTRAL": "혼조",
            "RISK_OFF": "위험회피",
            "UNKNOWN": "미상",
        }.get(mid_regime, mid_regime),
        "short": {
            "PANIC": "공황",
            "STABLE": "안정",
            "RELIEF": "안도",
            "UNKNOWN": "미상",
        }.get(short_signal, short_signal),
    }


def format_transition_expected(expected: Any) -> str:
    """transition_expected를 사람이 읽기 쉬운 문장으로 변환한다."""
    raw = "UNKNOWN" if expected is None else str(expected)
    parts = raw.split("_")
    if len(parts) != 3:
        return raw

    long_phase, mid_regime, short_signal = parts
    long_ko = {
        "EXPANSION": "확장",
        "LATE_CYCLE": "후기",
        "SLOWDOWN": "둔화",
        "RECESSION": "침체",
        "RECOVERY": "회복",
        "UNKNOWN": "미상",
    }.get(long_phase, long_phase)
    mid_ko = {
        "RISK_ON": "위험선호",
        "NEUTRAL": "혼조",
        "RISK_OFF": "위험회피",
        "UNKNOWN": "미상",
    }.get(mid_regime, mid_regime)
    short_ko = {
        "PANIC": "공황",
        "STABLE": "안정",
        "RELIEF": "안도",
        "UNKNOWN": "미상",
    }.get(short_signal, short_signal)
    return (
        f"장기 {long_ko}({long_phase}) · "
        f"중기 {mid_ko}({mid_regime}) · "
        f"단기 {short_ko}({short_signal})"
    )
