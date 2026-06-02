"""
WK리그 마케팅 인사이트 대시보드 (WK리그 단독 분석).

실행: streamlit run app.py
"""

from __future__ import annotations

import os

import streamlit as st

# Streamlit Cloud용: st.secrets에 설정된 API 키를 환경변수로 노출
# (로컬에선 .env가 dotenv로 로드되므로 영향 없음).
try:
    for _key in st.secrets:
        os.environ.setdefault(_key, str(st.secrets[_key]))
except Exception:
    pass

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

import analyzers
import collectors
import insights
from config import (
    COLOR,
    COLOR_BLUE,
    COLOR_BLUE_DEEP,
    COLOR_PURPLE,
    DEFAULT_PERIOD_DAYS,
    LEAGUE_NAME,
    PALETTE,
)

st.set_page_config(page_title="WK리그 마케팅 인사이트", page_icon="⚽", layout="wide")

# ---------- WK리그 브랜드 테마 ----------

LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "wk_logo_t.png")

st.markdown(
    f"""
    <style>
    /* 메인 타이틀 — 로고 그라데이션 텍스트 */
    h1 {{
        background: linear-gradient(90deg, {COLOR_BLUE_DEEP} 0%, {COLOR_PURPLE} 45%, {COLOR} 100%);
        -webkit-background-clip: text;
        background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 800 !important;
        width: fit-content;
    }}

    /* 섹션 헤더 (h2) — 그라데이션 칩 스타일 */
    h2 {{
        background: linear-gradient(90deg, rgba(133,194,235,0.18) 0%, rgba(189,95,156,0.14) 60%, rgba(189,95,156,0) 100%);
        border-radius: 10px;
        padding: 0.45rem 0.9rem !important;
        color: #2E2A4A;
    }}

    /* 메트릭 카드 */
    [data-testid="stMetric"] {{
        background: linear-gradient(135deg, #F2F8FD 0%, #FAF1F8 100%);
        border: 1px solid rgba(156,153,197,0.35);
        border-radius: 12px;
        padding: 0.8rem 1rem;
    }}
    [data-testid="stMetricValue"] {{
        color: {COLOR};
    }}

    /* 사이드바 — 로고 그라데이션 배경 */
    [data-testid="stSidebar"] {{
        background: linear-gradient(180deg, #EAF4FC 0%, #F2EFF8 55%, #F9EDF6 100%);
    }}

    /* 익스팬더 둥근 모서리 */
    [data-testid="stExpander"] {{
        border-radius: 12px;
        border: 1px solid rgba(156,153,197,0.4);
    }}
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------- 캐싱 ----------

@st.cache_data(ttl=3600, show_spinner="데이터 수집 중... (최초 1회 30초 내외)")
def get_raw_data(days: int) -> dict:
    return collectors.collect_all(days)


@st.cache_data(ttl=3600)
def get_analysis(raw: dict) -> dict:
    return analyzers.build_analysis_summary(raw)


@st.cache_data(ttl=3600, show_spinner="Claude 인사이트 생성 중...")
def get_insight(analysis: dict) -> str:
    return insights.generate_insight(analysis)


# ---------- 사이드바 ----------

st.sidebar.image(LOGO_PATH, width=150)
st.sidebar.title("분석 설정")

api_status = collectors.get_api_status()
st.sidebar.subheader("데이터 소스 상태")
st.sidebar.markdown(
    f"""
    - 네이버 (검색·뉴스·커뮤니티): {'✅' if api_status['naver'] else '❌ mock'}
    - YouTube: {'✅' if api_status['youtube'] else '❌ mock'}
    - 구글 트렌즈: ✅ (키 불필요)
    - 위키피디아: ✅ (키 불필요)
    - 빅카인즈: {'✅' if api_status.get('bigkinds') else '❌ mock'}
    - Claude (AI 리포트): {'✅' if api_status['anthropic'] else '❌ 템플릿'}
    """
)

period_days = st.sidebar.slider(
    "분석 기간 (일)", min_value=30, max_value=180, value=DEFAULT_PERIOD_DAYS, step=30
)

if st.sidebar.button("🔄 데이터 새로고침"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.caption(
    "검색·인구통계: 네이버 데이터랩 · 뉴스/커뮤니티: 네이버 검색 API · "
    "영상·댓글: YouTube Data API · 경기기록: data/match_records.csv"
)


# ---------- 데이터 로드 ----------

st.title(f"{LEAGUE_NAME} 마케팅 인사이트 대시보드")
st.markdown(
    "공개 데이터로 WK리그의 관심층을 추적하고, 데이터 기반으로 "
    "다음 타겟층과 실행 액션을 도출합니다."
)

raw = get_raw_data(period_days)
analysis = get_analysis(raw)

if raw.get("is_mock"):
    st.warning(
        "⚠️ 현재 데이터가 시뮬레이션(mock)입니다. "
        ".env 파일에 API 키를 설정하면 실제 데이터로 갱신됩니다."
    )


# ========== 섹션 1: 검색 트렌드 ==========

st.header("1️⃣ WK리그 검색 트렌드")
st.caption("네이버 검색 인덱스 — WK리그에 대한 대중 관심도의 추이입니다.")

search_df = analyzers.build_search_df(raw["search_trend"])
recent_df = analyzers.recent_window(search_df, period_days)

fig = px.area(
    recent_df, x="date", y="value",
    labels={"value": "검색 인덱스 (0-100)", "date": "날짜"},
    color_discrete_sequence=[COLOR],
)
fig.update_layout(height=300, hovermode="x unified")
st.plotly_chart(fig, width="stretch")

# 검색 인덱스 ≥ 50 한 날들의 원인 자동 매칭
high_days = analysis.get("high_days", [])
if high_days:
    with st.expander(f"📌 검색 인덱스 ≥ 50 이었던 날 {len(high_days)}건 — 왜 그랬을까?", expanded=True):
        st.caption("같은 날 경기·뉴스를 자동 매칭해 원인을 귀속합니다. '원인 불명'은 외부 이슈일 가능성 ↑.")
        for h in high_days:
            cause_icon = {"경기": "⚽", "뉴스 이슈": "📰", "경기 + 뉴스": "⚽📰", "원인 불명": "❓"}[h["cause"]]
            spike_tag = f" · 유형: **{h['spike_type']}**" if h.get("spike_type") else ""
            st.markdown(f"**{h['date']} ({h['weekday']}) — 검색 {h['value']}** · 원인: {cause_icon} **{h['cause']}**{spike_tag}")
            if h["matches"]:
                for m in h["matches"]:
                    st.markdown(f"&nbsp;&nbsp;⚽ {m}")
            if h["headlines"]:
                for hl in h["headlines"][:3]:
                    st.markdown(f"&nbsp;&nbsp;📰 {hl}")
            if not h["matches"] and not h["headlines"]:
                st.markdown("&nbsp;&nbsp;_매칭된 경기·뉴스 없음 — 검색 노이즈 또는 비공식 이벤트 가능성_")
            st.markdown("")

col1, col2 = st.columns(2)
with col1:
    st.subheader("요일별 검색 패턴")
    wd_breakdown = analysis.get("weekday_breakdown", [])
    wd_df = pd.DataFrame(wd_breakdown) if wd_breakdown else pd.DataFrame(analysis["weekday_pattern"])
    fig = px.bar(wd_df, x="weekday", y="avg_value",
                 labels={"avg_value": "평균 검색 인덱스", "weekday": "요일"},
                 color_discrete_sequence=[COLOR], text="avg_value")
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_layout(height=270, showlegend=False)
    st.plotly_chart(fig, width="stretch")

    # 가장 높은 요일의 이유 자동 설명
    if wd_breakdown:
        top_wd = max(wd_breakdown, key=lambda x: x["avg_value"])
        if top_wd["match_count"] > 0:
            ratio_pct = int(top_wd["match_day_ratio"] * 100)
            st.success(
                f"**{top_wd['weekday']}요일이 가장 높음 ({top_wd['avg_value']})** — "
                f"분석 기간 중 {top_wd['weekday']}요일 {top_wd['total_days']}일 중 "
                f"**{top_wd['match_days']}일에 경기**가 있었습니다 ({ratio_pct}%). "
                f"경기 {top_wd['match_count']}건: " + ", ".join(top_wd["examples"])
            )
        else:
            st.info(
                f"**{top_wd['weekday']}요일이 가장 높음 ({top_wd['avg_value']})** — "
                f"이 요일엔 경기가 없었습니다. 미디어 발행 패턴(주중 기사·예고편)이나 "
                f"공식 SNS 업로드 요일 효과 가능성이 큽니다."
            )

with col2:
    st.subheader("작년 동기 대비 (YoY)")
    yoy = analysis["yoy"]
    if yoy.get("available"):
        st.metric(
            label=f"최근 {period_days}일 평균 검색 인덱스",
            value=f"{yoy['this_year_avg']}",
            delta=f"{yoy['change_pct']:+.1f}% vs 작년 동기 ({yoy['last_year_avg']})",
        )
        st.caption(
            "네이버 검색 인덱스는 상대값이라 절대 크기 비교는 불가하지만, "
            "**작년 같은 기간과의 비교**로 관심도 증감을 판단할 수 있습니다."
        )
    else:
        st.info("작년 동기 데이터가 부족합니다.")

# 데이터 신뢰도 보강 — 네이버 vs 구글 + 위키 페이지뷰
st.markdown("##### 🔍 데이터 신뢰도 보강 (다중 소스 cross-validation)")
col1, col2 = st.columns(2)
with col1:
    xval = analysis.get("google_naver_xval", {})
    if xval.get("available"):
        corr = xval["correlation"]
        signal = "✅ 강한 일치" if corr >= 0.5 else ("⚠️ 약한 일치" if corr >= 0.2 else "❌ 불일치")
        st.metric(f"네이버 ↔ 구글 검색 트렌드 상관", f"{corr}", help="1에 가까울수록 두 검색 모집단이 같은 신호 → 결과 신뢰도 ↑")
        st.caption(f"{signal} · 공통 {xval['overlap_days']}일 비교")
        ser_df = pd.DataFrame(xval["series"])
        ser_df["date"] = pd.to_datetime(ser_df["date"])
        fig = px.line(ser_df, x="date", y=["naver", "google"],
                      labels={"value": "검색 인덱스", "date": "날짜", "variable": "소스"},
                      color_discrete_map={"naver": COLOR, "google": COLOR_BLUE_DEEP})
        fig.update_layout(height=200, legend={"orientation": "h", "y": -0.3})
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("구글 트렌즈 데이터 부족 (네이버와 cross-validation 불가)")
with col2:
    wiki = analysis.get("wiki", {})
    if wiki.get("available"):
        st.metric("위키피디아 페이지 총 조회수", f"{wiki['grand_total']:,}",
                  help="검색의 '도착점' — 정보를 찾으러 들어온 사람의 수, 깊은 관심의 프록시")
        st.caption(f"분석 기간 ko.wikipedia.org 페이지뷰")
        wiki_df = pd.DataFrame(wiki["page_totals"])
        st.dataframe(
            wiki_df.rename(columns={"page": "페이지", "total_views": "조회수"}),
            hide_index=True, width="stretch")
    else:
        st.info("위키 페이지뷰 데이터 부족")


# ========== 섹션 2: 키워드 세분화 & 국대 보정 ==========

st.header("2️⃣ 키워드 세분화 & 국가대표 보정")
st.caption("'WK리그' 관심을 구단·선수·국가대표로 분리해 신호의 출처를 가려냅니다.")

kb = analysis["keyword_breakdown"]
col1, col2 = st.columns(2)

with col1:
    st.subheader("구단별 검색 관심도")
    teams = kb.get("teams", [])
    if teams:
        team_df = pd.DataFrame(teams)
        fig = px.bar(team_df, x="avg", y="name", orientation="h",
                     labels={"avg": "평균 검색 인덱스", "name": "구단"},
                     color_discrete_sequence=[COLOR], text="avg")
        fig.update_traces(textposition="outside", cliponaxis=False)
        fig.update_layout(height=300, showlegend=False,
                          yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, width="stretch")
        st.caption("어느 구단이 검색 관심을 끄는지 — 팬덤이 편중된 구단을 보여줍니다.")
    if kb.get("players"):
        st.markdown("**선수별 검색:** " +
                    ", ".join(f"{p['name']}({p['avg']})" for p in kb["players"]))
    else:
        st.caption("💡 config.py의 PLAYER_KEYWORDS에 선수명을 추가하면 선수별 팬덤도 추적됩니다.")

with col2:
    st.subheader("국가대표 효과 보정")
    detrend = analysis["detrend"]
    if detrend.get("available"):
        st.metric(
            "WK리그 ↔ 국가대표 검색 상관계수",
            f"{detrend['correlation']}",
            help="1에 가까울수록 WK리그 관심이 국가대표 이벤트에 의존적",
        )
        st.markdown(
            f"WK리그 검색 변동의 **{detrend['explained_ratio']}%가** "
            f"국가대표 검색으로 설명됩니다."
        )
        dt_df = pd.DataFrame([
            {"date": p["date"], "검색 인덱스": p["value"], "구분": "WK리그 원본"}
            for p in detrend["wk_raw"]
        ] + [
            {"date": p["date"], "검색 인덱스": p["value"], "구분": "국대 효과 보정"}
            for p in detrend["adjusted"]
        ])
        dt_df["date"] = pd.to_datetime(dt_df["date"])
        fig = px.line(dt_df, x="date", y="검색 인덱스", color="구분",
                      color_discrete_map={"WK리그 원본": COLOR_BLUE, "국대 효과 보정": COLOR})
        fig.update_layout(height=240, hovermode="x unified",
                          legend={"orientation": "h", "y": -0.3})
        st.plotly_chart(fig, width="stretch")
        st.caption("'보정' 선은 국가대표와 함께 움직이는 변동을 제거한 순수 WK리그 관심도.")
    else:
        st.info("국대 보정 데이터가 부족합니다.")


# ========== 섹션 3: 변화 감지 & 스파이크 ==========

st.header("3️⃣ 변화 감지 및 스파이크 원인 분석")
st.caption("검색량의 급변을 자동 탐지하고, 같은 시점 뉴스로 원인과 유형을 추정합니다.")

growth = analysis["growth"]
col1, col2, col3 = st.columns(3)
if growth.get("available"):
    col1.metric("최근 14일 평균", f"{growth['recent_avg']}")
    col2.metric("직전 14일 평균", f"{growth['prev_avg']}")
    col3.metric("성장률", f"{growth['growth_pct']:+.1f}%")

# 빅카인즈 표본 확대 안내
bk = analysis.get("bigkinds", {})
if bk.get("available"):
    st.info(
        f"📰 **뉴스 표본 확대** — 분석 기간 빅카인즈 {bk['bigkinds_total']:,}건 "
        f"vs 네이버 뉴스 {bk['naver_news_total']:,}건 "
        f"(빅카인즈가 약 **{bk['multiplier']}배**). "
        "더 많은 헤드라인으로 스파이크 원인 추정 정확도 ↑"
    )

st.subheader("📈 검색 스파이크 + 유형 + 추정 원인")
spikes = analysis["spikes"]
if spikes:
    for s in spikes:
        title = (f"🔺 {s['date']}  ·  검색 {s['value']}  (z={s['z_score']})  "
                 f"·  유형: {s.get('spike_type', '기타')}")
        with st.expander(title):
            if s["related_headlines"]:
                st.markdown("**같은 시점 뉴스 헤드라인:**")
                for h in s["related_headlines"]:
                    st.markdown(f"- {h}")
            else:
                st.info("해당 시점의 관련 뉴스를 찾지 못했습니다.")
    st.caption("z-score 2.0 이상 = 평균에서 2 표준편차 이상 벗어난 급증. "
               "유형은 관련 뉴스 키워드로 자동 분류.")
else:
    st.info("분석 기간 내 감지된 스파이크가 없습니다.")


# ========== 섹션 4: 인구통계 ==========

st.header("4️⃣ 관심층 인구통계 & 변화")
st.caption("WK리그 검색층의 연령·성별 분포와, 기간에 따른 관심층 이동을 봅니다.")

demo = analysis["demographics"]
st.markdown(
    f"#### 핵심 관심층: **{demo['top_age']}** ({demo['top_age_pct']}%) · "
    f"**{demo['top_gender']}** ({demo['top_gender_pct']}%)"
)

col1, col2 = st.columns(2)
with col1:
    st.subheader("성별 분포")
    gender = demo["gender"]
    if gender:
        fig = px.pie(values=list(gender.values()), names=list(gender.keys()),
                     color=list(gender.keys()),
                     color_discrete_map={"남성": COLOR_BLUE_DEEP, "여성": COLOR},
                     hole=0.45)
        fig.update_layout(height=300)
        st.plotly_chart(fig, width="stretch")

with col2:
    st.subheader("연령대 분포")
    age = demo["age"]
    if age:
        age_order = ["10대", "20대", "30대", "40대", "50대", "60대 이상"]
        rows = [{"연령대": k, "비중": age.get(k, 0)} for k in age_order if k in age]
        fig = px.bar(pd.DataFrame(rows), x="연령대", y="비중",
                     color_discrete_sequence=[COLOR], text="비중")
        fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside", cliponaxis=False)
        fig.update_layout(height=300, showlegend=False, yaxis_title="비중 (%)")
        st.plotly_chart(fig, width="stretch")

evo = analysis.get("demographics_evolution", {})
if evo.get("available"):
    st.subheader("관심층 이동 — 연령대별 검색 비중 변화")
    rs, fs = evo["rising_segment"], evo["falling_segment"]
    c1, c2 = st.columns(2)
    c1.metric(f"📈 상승: {rs['age']}", f"{rs['late']}%",
              delta=f"{rs['change']:+.1f}pp (기간 전반 대비)")
    c2.metric(f"📉 하락: {fs['age']}", f"{fs['late']}%",
              delta=f"{fs['change']:+.1f}pp (기간 전반 대비)")

    share_ts = evo["age_share_timeseries"]
    rows = []
    for ageg, series in share_ts.items():
        for p in series:
            rows.append({"date": p["date"], "연령대": ageg, "비중": p["share"]})
    share_df = pd.DataFrame(rows)
    share_df["date"] = pd.to_datetime(share_df["date"])
    fig = px.line(share_df, x="date", y="비중", color="연령대",
                  labels={"비중": "검색 비중 (%)", "date": "날짜"},
                  color_discrete_sequence=PALETTE)
    fig.update_layout(height=300, hovermode="x unified")
    st.plotly_chart(fig, width="stretch")
    st.caption("어느 연령대가 새로 유입되고 어느 층이 빠지는지 — '다음 타겟' 도출의 핵심 근거.")

st.caption("⚠️ 검색층은 실제 관람객이 아닌 '관심층'입니다. 이들을 실제 팬으로 전환하는 것이 과제입니다.")


# ========== 섹션 5: 유튜브 ==========

st.header("5️⃣ WK리그 유튜브 콘텐츠 반응")
st.caption("공식 채널(한국여자축구연맹)의 영상 포맷별 반응을 분석합니다.")

meta = analysis["youtube_meta"]
col1, col2, col3 = st.columns(3)
col1.metric("구독자", f"{meta['subscribers']:,}")
col2.metric("총 영상 수", f"{meta['total_videos']:,}")
col3.metric("평균 조회수", f"{meta['avg_views']:,}")

col1, col2 = st.columns(2)
with col1:
    st.subheader("영상 포맷별 평균 조회수")
    fmt_df = pd.DataFrame(analysis["youtube_formats"])
    if not fmt_df.empty:
        fig = px.bar(fmt_df, x="format", y="avg_views",
                     color_discrete_sequence=[COLOR], text="avg_views",
                     labels={"avg_views": "평균 조회수", "format": "포맷"})
        fig.update_traces(texttemplate="%{text:,}", textposition="outside", cliponaxis=False)
        fig.update_layout(height=320, showlegend=False)
        st.plotly_chart(fig, width="stretch")
with col2:
    st.subheader("포맷별 상세")
    if not fmt_df.empty:
        st.dataframe(
            fmt_df.rename(columns={
                "format": "포맷", "video_count": "영상수", "avg_views": "평균조회",
                "avg_likes": "평균좋아요", "avg_comments": "평균댓글",
                "engagement_rate": "참여율(%)"}),
            hide_index=True, width="stretch")

# 1위 포맷이 왜 잘 됐는지 자동 설명
tf = analysis.get("top_format_explanation", {})
if tf.get("available"):
    st.success(
        f"🏆 **'{tf['top_format']}' 포맷이 1위** — 평균 {tf['avg_views']:,}회 "
        f"(2위 '{tf['second_format']}' {tf['second_avg_views']:,}회의 **{tf['multiplier']}배**). "
        f"이 포맷 영상 {tf['video_count']}개, 참여율 {tf['engagement_rate']}%"
    )
    if tf["examples"]:
        st.caption("**이 포맷 대표 영상:**")
        for ex in tf["examples"]:
            st.markdown(f"&nbsp;&nbsp;🎬 _{ex['title']}_ — {ex['views']:,}회")

st.subheader("조회수 상위 영상 (KWFF 공식 채널)")
ctx_videos = analysis.get("top_videos_context", [])
if ctx_videos:
    st.caption("각 영상의 업로드일 기준 ±3일 내 경기·뉴스·검색 스파이크를 자동 매칭 — 왜 이 영상이 잘 됐는지 추정합니다.")
    for i, v in enumerate(ctx_videos, 1):
        spike_tag = " 🔥" if v.get("search_spike_around") else ""
        s_around = f" · 검색 인덱스 ~{v['search_around']}" if v.get("search_around") is not None else ""
        st.markdown(
            f"**{i}. {v['title']}** — {v['views']:,}회 · {v['format']}{spike_tag}"
        )
        st.markdown(
            f"&nbsp;&nbsp;📅 업로드 {v['upload_date']}{s_around}"
        )
        for m in v["nearby_matches"]:
            st.markdown(f"&nbsp;&nbsp;⚽ {m}")
        for hl in v["nearby_headlines"]:
            st.markdown(f"&nbsp;&nbsp;📰 {hl}")
        if not v["nearby_matches"] and not v["nearby_headlines"]:
            st.markdown("&nbsp;&nbsp;_매칭된 경기·뉴스 없음 — 콘텐츠 자체 매력(편집·썸네일)이 동인일 가능성_")
        st.markdown("")

# 외부 채널 (KWFF 이외)
ext = analysis.get("external_youtube", {})
st.subheader("외부 채널의 WK리그 커버리지 (KWFF 외)")
if ext.get("available"):
    st.caption(f"YouTube 전체에서 'WK리그' 검색 결과 (공식 채널 제외) — "
               f"외부 콘텐츠 생태계 활성도를 보여줍니다.")
    col1, col2 = st.columns(2)
    col1.metric("외부 영상 수", f"{ext['video_count']}개")
    col2.metric("외부 영상 총 조회수", f"{ext['total_views']:,}")
    if ext["top_channels"]:
        st.markdown("**상위 외부 채널:**")
        ch_df = pd.DataFrame(ext["top_channels"]).rename(columns={
            "channel": "채널", "video_count": "영상수", "total_views": "총조회수"})
        st.dataframe(ch_df, hide_index=True, width="stretch")
else:
    st.info("외부 채널 데이터 부족.")


# ========== 섹션 6: 여론 감성 ==========

st.header("6️⃣ 여론 감성 분석")
st.caption("유튜브 댓글의 긍·부정을 분석합니다 — 관심의 '양'이 아닌 '질'을 봅니다.")

sent = analysis["sentiment"]
if sent.get("available"):
    src = sent.get("source_counts", {})
    src_str = " · ".join(f"{k} {v}개" for k, v in src.items())
    st.caption(f"분석 표본: {sent['total']}개 ({src_str})")
    if sent.get("low_sample"):
        st.warning(f"⚠️ 분석 표본이 {sent['total']}개로 적어 해석에 주의가 필요합니다.")
    col1, col2 = st.columns([1, 1])
    with col1:
        fig = px.pie(
            values=[sent["positive"], sent["neutral"], sent["negative"]],
            names=["긍정", "중립", "부정"], color=["긍정", "중립", "부정"],
            color_discrete_map={"긍정": COLOR_BLUE_DEEP, "중립": "#C9CBD8", "부정": COLOR},
            hole=0.45)
        fig.update_layout(height=300)
        st.plotly_chart(fig, width="stretch")
    with col2:
        st.metric("긍정", f"{sent['positive_pct']}%")
        st.metric("부정", f"{sent['negative_pct']}%")
        st.metric("분석 댓글 수", f"{sent['total']}개")
    ex = sent.get("examples", {})
    if ex.get("positive"):
        st.markdown("**긍정 댓글 예시:** " + " / ".join(f"\"{t}\"" for t in ex["positive"]))
    if ex.get("negative"):
        st.markdown("**부정 댓글 예시:** " + " / ".join(f"\"{t}\"" for t in ex["negative"]))
else:
    st.info("감성 분석할 댓글 데이터가 없습니다.")


# ========== 섹션 7: 경기력 ↔ 관심도 ==========

st.header("7️⃣ 경기력 ↔ 관심도 연결")
st.caption("중계 여부·접전 여부가 검색 관심에 주는 영향을 분석합니다.")

m = analysis["matches"]
if m.get("available"):
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**중계 여부별 경기 주변 검색량**")
        c1, c2 = st.columns(2)
        c1.metric(f"중계 O ({m['broadcast_on_count']}경기)",
                  f"{m['broadcast_on_avg']}" if m['broadcast_on_avg'] is not None else "—")
        c2.metric(f"중계 X ({m['broadcast_off_count']}경기)",
                  f"{m['broadcast_off_avg']}" if m['broadcast_off_avg'] is not None else "—")
    with col2:
        st.markdown("**경기 양상별 경기 주변 검색량**")
        c1, c2 = st.columns(2)
        c1.metric("접전 (점수차 ≤1)",
                  f"{m['close_avg']}" if m['close_avg'] is not None else "—")
        c2.metric("일방적 경기",
                  f"{m['blowout_avg']}" if m['blowout_avg'] is not None else "—")

    st.subheader("경기 기록")
    mt_df = pd.DataFrame(m["matches"])
    if not mt_df.empty:
        mt_df["스코어"] = mt_df["home_score"].astype(str) + " : " + mt_df["away_score"].astype(str)
        show = mt_df[["date", "round", "home", "away", "스코어", "broadcast", "search_around"]]
        show = show.rename(columns={
            "date": "날짜", "round": "라운드", "home": "홈", "away": "원정",
            "broadcast": "중계", "search_around": "경기 주변 검색"})
        st.dataframe(show, hide_index=True, width="stretch")
    st.caption("⚠️ 경기·중계 데이터는 data/match_records.csv 수동 입력입니다. "
               "실제 값으로 교체하면 정확도가 올라갑니다.")
else:
    st.info("경기 기록 데이터가 없습니다.")


# ========== 섹션 8: AI 인사이트 리포트 ==========

st.header("8️⃣ AI 자동 인사이트 리포트")
st.caption("Claude가 위 1~7번 데이터를 종합해 다음 타겟·실행 액션을 도출합니다.")

if st.button("🧠 인사이트 리포트 생성", type="primary"):
    st.markdown(get_insight(analysis))
else:
    st.info("버튼을 클릭하면 분석 결과를 종합한 자연어 리포트를 생성합니다.")


st.markdown("---")
st.caption(
    "이 대시보드는 공개 데이터만으로 WK리그의 관심층을 추적하는 반복 가능한 분석 체계입니다. "
    "연맹·구단의 내부 데이터(관중·티켓·SNS 인구통계)가 연동되면 '관심→유입→전환' 전체 퍼널로 확장 가능합니다."
)
