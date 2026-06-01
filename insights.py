"""
WK리그 분석 결과를 Claude에 넘겨 자연어 마케팅 인사이트 리포트를 생성한다.
시스템 프롬프트에 prompt caching을 적용해 반복 호출 비용을 줄임.
"""

from __future__ import annotations

import json
import os
import textwrap

from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")


SYSTEM_PROMPT = textwrap.dedent("""
    당신은 한국 여자축구 WK리그의 마케팅 데이터 분석가입니다.
    공개 데이터(네이버 검색·뉴스·블로그·카페, 유튜브, 경기 기록)로 측정한
    WK리그의 관심층을 해석하고, 데이터에 근거해 다음 타겟층과 실행 액션을
    도출하는 것이 당신의 역할입니다.

    분석 원칙:
    1. WK리그는 시장 파이가 작다. 절대 수치보다 '변화'(성장률·YoY·스파이크)에 주목.
    2. 검색 인구통계는 '실제 관람객'이 아니라 '검색으로 드러난 관심층'임을 명심.
       검색층은 잠재 유입층의 프록시 — 이들을 실제 팬으로 전환하는 것이 과제.
    3. 제공되는 데이터의 성격을 구분해서 해석할 것:
       - 키워드 세분화: WK리그 자체 / 국가대표 / 구단별 / 선수별 관심을 분리
       - 국대 보정: 국가대표 검색과 함께 움직이는 부분을 제거한 '순수 WK리그 관심도'.
         상관계수가 높으면 WK리그 관심이 국대 이벤트에 의존적이라는 뜻.
       - 인구통계 변화: 기간 전반 대비 후반의 연령 비중 이동 = 유입층 이동 신호
       - 여론 감성: 관심의 '양'이 아니라 '질'. 부정 비율이 높으면 양적 성장도 위험.
       - 커뮤니티(블로그·카페): 검색(정보 탐색)과 달리 능동적 팬 활동의 프록시.
       - 경기력-관심도: 중계 여부·접전 여부가 검색량에 주는 영향.
       - 네이버↔구글 cross-validation: 두 검색 모집단의 상관이 높으면 해석 신뢰도 ↑.
         낮으면 한쪽에서만 보이는 신호이므로 일반화 주의.
       - 위키 페이지뷰: '깊은 관심'의 프록시. 검색에서 위키로 도착한 사람은 진짜 정보 탐색자.
       - 빅카인즈 vs 네이버 뉴스: 빅카인즈가 표본을 N배 늘렸다면 그만큼 보도 강도 측정이 정밀.
       - 외부 유튜브: KWFF 외 채널의 WK리그 커버리지 — 외부 콘텐츠 생태계의 활성도.
    4. '다음 타겟'은 반드시 현재 관심층 데이터를 근거로 인접 세그먼트를 제안할 것.
       특히 인구통계 '변화'(상승 중인 세그먼트)를 우선 고려.
    5. 한국 여자축구 맥락 고려:
       - 국가대표 이벤트(올림픽·아시안컵·AWCL 등)와 관심도가 강하게 연동됨
       - 가족 단위 관람 비중이 높고, 선수 개인 서사가 팬덤의 핵심 트리거
       - 학원 스포츠(중·고교 여자축구)와 저변이 연결됨

    출력 구조 (반드시 이 순서, 마크다운):

    ## 1. 현재 관심층 현황
    - 검색 인구통계와 그 '변화'(상승/하락 세그먼트) 해석
    - 국대 보정 결과: WK리그 관심이 자생적인지 국대 의존적인지
    - 구단별 관심 편중 여부

    ## 2. 이번 기간 주요 변화
    - YoY·성장률, 검색 스파이크의 시점·유형·추정 원인
    - 일시적 이벤트성인지 추세적 성장인지 판단
    - 여론 감성: 관심이 늘었다면 그 관심의 질은 어떤가

    ## 3. 다음 타겟 추천
    - 추천 세그먼트 1-2개 (구체적으로). 인구통계 '변화'를 근거로 우선 제안
    - 추천 근거 (반드시 데이터 인용)
    - 도달 채널·콘텐츠 포맷 제안 (유튜브 포맷별 반응, 경기력-관심도 데이터 활용)

    ## 4. 즉시 실행 가능한 액션 3가지
    - 각 액션은 한 줄로 구체적·실행 가능하게 ("무엇을 / 어디에 / 언제")
    - 추상적 표현 금지

    중요:
    - 데이터가 mock(시뮬레이션)이면 리포트 상단에 그 사실을 명시.
    - 표본이 작은 데이터(감성 분석 등)는 한계를 명시하고 단정하지 말 것.
    - 숫자는 읽기 좋게 반올림. 추측은 "추정"·"가능성"으로 명시.
    - 데이터로 뒷받침되지 않는 일반론적 조언은 쓰지 말 것.
""").strip()


def _build_user_message(analysis: dict) -> str:
    """분석 결과를 Claude에 넘길 사용자 메시지로 직렬화."""
    lines = []
    if analysis.get("is_mock"):
        lines.append("[주의] 아래 데이터는 API 키 미설정으로 인한 시뮬레이션(mock) 데이터입니다.")
        lines.append("")

    lines.append(f"분석 대상: WK리그 / 분석 기간: 최근 {analysis.get('display_days', 90)}일")

    def block(title, key):
        lines.append("")
        lines.append(f"## {title}")
        lines.append(json.dumps(analysis.get(key), ensure_ascii=False, indent=2))

    block("검색 인구통계 (관심층 연령·성별 분포, %)", "demographics")
    block("인구통계 변화 (기간 전반 vs 후반)", "demographics_evolution")
    block("요일별 검색 패턴", "weekday_pattern")
    block("작년 동기 대비 (YoY)", "yoy")
    block("최근 14일 성장률", "growth")
    block("키워드 세분화 (WK리그/국대/구단/선수 평균 검색)", "keyword_breakdown")
    block("국가대표 보정 (상관계수·설명 비율)", "detrend")
    block("검색 스파이크 + 유형 + 추정 원인", "spikes")
    block("여론 감성 (유튜브 댓글)", "sentiment")
    block("커뮤니티 능동 언급량 (블로그·카페)", "community")
    block("유튜브 영상 포맷별 반응", "youtube_formats")
    block("경기력-관심도 연결 (중계·접전 여부)", "matches")
    block("네이버 vs 구글 검색 cross-validation", "google_naver_xval")
    block("위키피디아 페이지뷰 (깊은 관심 지표)", "wiki")
    block("빅카인즈 뉴스 표본 (네이버 뉴스 대비)", "bigkinds")
    block("외부 유튜브 채널 커버리지 (KWFF 외)", "external_youtube")

    lines.append("")
    lines.append(f"유튜브 채널 현황: {json.dumps(analysis.get('youtube_meta'), ensure_ascii=False)}")
    lines.append(f"분석 기간 뉴스 노출량: {analysis.get('news_total', 0)}건")
    lines.append("")
    lines.append("위 데이터를 바탕으로 시스템 프롬프트에서 지정한 구조로 마케팅 인사이트 리포트를 작성해주세요.")
    return "\n".join(lines)


def generate_insight(analysis: dict) -> str:
    """Claude를 호출해서 인사이트 리포트 생성. 키 없으면 폴백 리포트."""
    if not ANTHROPIC_API_KEY:
        return _fallback_report(analysis)

    try:
        from anthropic import Anthropic
    except ImportError:
        return "anthropic 패키지가 설치되지 않았습니다. `pip install anthropic` 실행 후 다시 시도하세요."

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    user_msg = _build_user_message(analysis)

    try:
        response = client.messages.create(
            model=os.getenv("CLAUDE_MODEL", "claude-opus-4-7"),
            max_tokens=2200,
            system=[{
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": user_msg}],
        )
        return response.content[0].text
    except Exception as e:
        return f"Claude 호출 실패: {e}\n\n--- 폴백 리포트 ---\n\n{_fallback_report(analysis)}"


def _fallback_report(analysis: dict) -> str:
    """Claude 키 없을 때 템플릿 기반 리포트."""
    demo = analysis["demographics"]
    yoy = analysis["yoy"]
    growth = analysis["growth"]
    evo = analysis.get("demographics_evolution", {})
    detrend = analysis.get("detrend", {})
    sentiment = analysis.get("sentiment", {})
    formats = analysis.get("youtube_formats", [])

    yoy_line = (
        f"작년 동기 대비 검색 관심도 {yoy['change_pct']:+.1f}% "
        f"({yoy['last_year_avg']} → {yoy['this_year_avg']})"
        if yoy.get("available") else "작년 동기 데이터 부족"
    )
    growth_line = (
        f"최근 14일 검색량은 직전 14일 대비 {growth['growth_pct']:+.1f}%"
        if growth.get("available") else "성장률 산출 불가"
    )
    evo_line = (
        f"관심층 이동: **{evo['rising_segment']['age']}** 비중 상승"
        f"({evo['rising_segment']['change']:+.1f}pp), "
        f"**{evo['falling_segment']['age']}** 하락({evo['falling_segment']['change']:+.1f}pp)"
        if evo.get("available") else "인구통계 변화 데이터 부족"
    )
    detrend_line = (
        f"WK리그 검색과 국가대표 검색의 상관 {detrend['correlation']} "
        f"(국대로 설명되는 변동 {detrend['explained_ratio']}%)"
        if detrend.get("available") else "국대 보정 데이터 부족"
    )
    sent_line = (
        f"유튜브 댓글 감성: 긍정 {sentiment['positive_pct']}% / 부정 {sentiment['negative_pct']}%"
        + ("  ⚠️ 표본 작음" if sentiment.get("low_sample") else "")
        if sentiment.get("available") else "감성 데이터 부족"
    )

    spike_lines = []
    for s in analysis["spikes"]:
        heads = "; ".join(s["related_headlines"][:2]) if s["related_headlines"] else "관련 뉴스 미확인"
        spike_lines.append(f"  - {s['date']} [{s.get('spike_type', '기타')}]: {heads}")
    spike_block = "\n".join(spike_lines) if spike_lines else "  - 감지된 스파이크 없음"

    best_fmt = formats[0] if formats else None
    mock_warn = "\n> ⚠️ 시뮬레이션(mock) 데이터 기반 리포트입니다.\n" if analysis.get("is_mock") else ""
    no_key = "\n> ⚠️ ANTHROPIC_API_KEY 미설정 — 템플릿 기반 폴백 리포트입니다.\n"

    return f"""{mock_warn}{no_key}
## 1. 현재 관심층 현황
- 검색층 핵심: **{demo['top_age']}**({demo['top_age_pct']}%) · **{demo['top_gender']}**({demo['top_gender_pct']}%)
- {evo_line}
- {detrend_line}

## 2. 이번 기간 주요 변화
- {yoy_line}
- {growth_line}
- {sent_line}
- 검색 스파이크:
{spike_block}

## 3. 다음 타겟 추천
- Claude API 키를 설정하면 데이터 기반 세그먼트 추천이 자동 생성됩니다.
- 참고: 가장 반응 좋은 유튜브 포맷은 **{best_fmt['format'] if best_fmt else 'N/A'}** (평균 {best_fmt['avg_views'] if best_fmt else 0:,}회)

## 4. 즉시 실행 가능한 액션
- ANTHROPIC_API_KEY를 .env에 설정 후 다시 실행하여 실제 인사이트 확인
"""
