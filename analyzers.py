"""
수집된 WK리그 원시 데이터를 인사이트가 추출 가능한 형태로 가공한다.

분석 항목:
- 검색 트렌드: 요일 패턴, 작년 동기 대비(YoY)
- 키워드 세분화: WK리그 / 국가대표 / 구단 / 선수 분리
- 국대 보정: 국가대표 검색량을 제거한 '순수 WK리그 관심도'
- 변화 감지: 성장률, 스파이크(z-score) + 뉴스 원인 + 유형 분류
- 인구통계: 핵심 타겟 + 시간에 따른 관심층 변화
- 유튜브: 영상 포맷별 반응
- 여론 감성: 댓글 긍/부정 분석
- 커뮤니티: 블로그·카페 능동 언급량
- 경기력-관심도: 중계·접전 여부와 검색량 연결
"""

from __future__ import annotations

import statistics
from datetime import date, timedelta

import pandas as pd

from config import (
    GROWTH_WINDOW_DAYS,
    PLAYER_KEYWORDS,
    SPIKE_Z_THRESHOLD,
    TEAM_KEYWORDS,
    classify_spike_type,
    classify_video_format,
)

WEEKDAY_NAMES = ["월", "화", "수", "목", "금", "토", "일"]

# 감성 분석 어휘 사전 (명확히 긍/부정 의미를 갖는 단어 위주)
POSITIVE_WORDS = [
    "재밌", "재미있", "꿀잼", "최고", "멋있", "멋지", "좋아", "좋다", "좋네", "응원",
    "사랑", "감동", "대박", "화이팅", "파이팅", "기대", "예쁘", "잘한다", "잘하", "발전",
    "흥행", "감사", "고맙", "행복", "짱", "명경기", "역대급",
]
NEGATIVE_WORDS = [
    "아쉽", "별로", "안좋", "안 좋", "최악", "실망", "노잼", "재미없", "부족", "지루",
    "심하", "엉망", "화나", "짜증", "문제", "위기", "해체", "걱정", "답답", "안타깝",
]


def _to_native(obj):
    """numpy/pandas 스칼라를 순수 파이썬 타입으로 변환 (JSON 직렬화 안전)."""
    if isinstance(obj, dict):
        return {k: _to_native(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_native(v) for v in obj]
    if hasattr(obj, "item"):
        return obj.item()
    return obj


def _mean(values: list) -> float:
    return statistics.mean(values) if values else 0.0


# ---------- 검색 트렌드 ----------

def build_search_df(trend: list[dict]) -> pd.DataFrame:
    """검색 트렌드 리스트 → DataFrame (date, value, weekday)."""
    df = pd.DataFrame(trend)
    df["date"] = pd.to_datetime(df["date"])
    df["weekday"] = df["date"].dt.weekday
    return df.sort_values("date").reset_index(drop=True)


def recent_window(df: pd.DataFrame, days: int) -> pd.DataFrame:
    """표시 기간(최근 days일)만 잘라낸다."""
    return df.iloc[-days:].reset_index(drop=True)


def weekday_pattern(df: pd.DataFrame, days: int) -> list[dict]:
    """표시 기간 내 요일별 평균 검색 인덱스."""
    sub = recent_window(df, days)
    avg = sub.groupby("weekday")["value"].mean()
    return [{"weekday": WEEKDAY_NAMES[wd], "avg_value": round(float(avg.get(wd, 0)), 1)}
            for wd in range(7)]


def explain_high_days(
    df: pd.DataFrame,
    days: int,
    matches: list[dict],
    articles: list[dict],
    threshold: float = 50.0,
    news_window: int = 1,
) -> list[dict]:
    """검색 인덱스가 threshold 이상이었던 날들에 원인(경기/뉴스)을 자동으로 매칭.

    각 날짜에 대해:
    - 같은 날 진행된 경기 (match_records.csv)
    - ±news_window 일 이내 뉴스 헤드라인
    - 자동 귀속: '경기' / '뉴스 이슈' / '복합' / '원인 불명'
    """
    sub = recent_window(df, days)
    high = sub[sub["value"] >= threshold].sort_values("value", ascending=False)
    if high.empty:
        return []

    match_by_date: dict[str, list[dict]] = {}
    for m in matches:
        match_by_date.setdefault(m.get("date", ""), []).append(m)

    results = []
    for d, v in zip(high["date"], high["value"]):
        d_iso = d.strftime("%Y-%m-%d")
        d0 = d.date()
        day_matches = match_by_date.get(d_iso, [])
        nearby_news = []
        for art in articles:
            try:
                a_date = date.fromisoformat(art["date"])
            except Exception:
                continue
            if abs((a_date - d0).days) <= news_window:
                nearby_news.append(art["title"])

        spike_type = classify_spike_type(nearby_news) if nearby_news else None
        if day_matches and nearby_news:
            cause = "경기 + 뉴스"
        elif day_matches:
            cause = "경기"
        elif nearby_news:
            cause = "뉴스 이슈"
        else:
            cause = "원인 불명"

        results.append({
            "date": d_iso,
            "weekday": WEEKDAY_NAMES[d.weekday()],
            "value": round(float(v), 1),
            "cause": cause,
            "spike_type": spike_type,
            "matches": [
                f"{m['round']} {m['home']} {m['home_score']}-{m['away_score']} {m['away']}"
                + (f" ({m['broadcast']})" if m.get("broadcast") and m.get("broadcast") != "없음" else "")
                for m in day_matches
            ],
            "headlines": nearby_news[:5],
        })
    return results


def weekday_breakdown(
    df: pd.DataFrame, days: int, matches: list[dict],
) -> list[dict]:
    """요일별 평균 검색 인덱스 + 해당 요일에 열린 경기 수·예시.

    이 요일이 왜 높은지(경기가 몰렸는지 아닌지) 설명할 수 있게 한다.
    """
    sub = recent_window(df, days).copy()
    period_dates = {d.date() for d in sub["date"]}

    match_dates_by_wd: dict[int, list[dict]] = {wd: [] for wd in range(7)}
    for m in matches:
        try:
            d0 = date.fromisoformat(m["date"])
        except Exception:
            continue
        if d0 not in period_dates:
            continue
        match_dates_by_wd[d0.weekday()].append(m)

    avg = sub.groupby("weekday")["value"].mean()
    total_days_by_wd = sub.groupby("weekday").size()

    out = []
    for wd in range(7):
        ms = match_dates_by_wd[wd]
        match_days = len({m["date"] for m in ms})
        total_days = int(total_days_by_wd.get(wd, 0))
        examples = [f"{m['round']} {m['home']} vs {m['away']}" for m in ms[:3]]
        out.append({
            "weekday": WEEKDAY_NAMES[wd],
            "avg_value": round(float(avg.get(wd, 0)), 1),
            "match_count": len(ms),
            "match_days": match_days,
            "total_days": total_days,
            "match_day_ratio": round(match_days / total_days, 2) if total_days else 0,
            "examples": examples,
        })
    return out


def yoy_comparison(df: pd.DataFrame, days: int) -> dict:
    """작년 동기 대비. 트렌드 (days+365)일치 중 앞 days = 작년, 뒤 days = 올해."""
    if len(df) < days * 2:
        return {"available": False}
    last_year = float(df["value"].iloc[:days].mean())
    this_year = float(df["value"].iloc[-days:].mean())
    change = ((this_year - last_year) / last_year * 100) if last_year > 0 else 0
    return {
        "available": True,
        "this_year_avg": round(this_year, 1),
        "last_year_avg": round(last_year, 1),
        "change_pct": round(change, 1),
    }


def compute_growth(df: pd.DataFrame, days: int, window: int = GROWTH_WINDOW_DAYS) -> dict:
    """표시 기간 내 최근 window일 vs 직전 window일 검색량 변화."""
    sub = recent_window(df, days)
    if len(sub) < window * 2:
        return {"available": False}
    recent = float(sub["value"].iloc[-window:].mean())
    prev = float(sub["value"].iloc[-window * 2:-window].mean())
    growth = ((recent - prev) / prev * 100) if prev > 0 else 0
    return {
        "available": True, "window_days": window,
        "recent_avg": round(recent, 2), "prev_avg": round(prev, 2),
        "growth_pct": round(growth, 1),
    }


def detect_spikes(df: pd.DataFrame, days: int, z_threshold: float = SPIKE_Z_THRESHOLD) -> list[dict]:
    """표시 기간 내 z-score 기반 검색량 스파이크 감지."""
    sub = recent_window(df, days).copy()
    if len(sub) < 7:
        return []
    mean = sub["value"].mean()
    std = sub["value"].std()
    if std == 0:
        return []
    sub["z"] = (sub["value"] - mean) / std
    spikes = sub[sub["z"] >= z_threshold]
    return [{"date": d.strftime("%Y-%m-%d"), "value": round(float(v), 1), "z_score": round(float(z), 2)}
            for d, v, z in zip(spikes["date"], spikes["value"], spikes["z"])]


def attach_news_to_spikes(spikes: list[dict], articles: list[dict], window_days: int = 2) -> list[dict]:
    """각 스파이크에 ±window_days 뉴스 헤드라인을 붙이고 유형을 분류한다."""
    result = []
    for spike in spikes:
        s_date = date.fromisoformat(spike["date"])
        near = []
        for art in articles:
            try:
                a_date = date.fromisoformat(art["date"])
            except Exception:
                continue
            if abs((a_date - s_date).days) <= window_days:
                near.append(art["title"])
        result.append({
            **spike,
            "related_headlines": near[:5],
            "spike_type": classify_spike_type(near),
        })
    return result


# ---------- 키워드 세분화 + 국대 보정 ----------

def keyword_breakdown(keyword_trends: dict) -> dict:
    """WK리그 / 국가대표 / 구단 / 선수별 평균 검색 인덱스."""
    def avg(label):
        s = keyword_trends.get(label, [])
        return round(_mean([p["value"] for p in s]), 2)

    teams = sorted(
        [{"name": t, "avg": avg(t)} for t in TEAM_KEYWORDS if t in keyword_trends],
        key=lambda x: x["avg"], reverse=True,
    )
    players = sorted(
        [{"name": p, "avg": avg(p)} for p in PLAYER_KEYWORDS if p in keyword_trends],
        key=lambda x: x["avg"], reverse=True,
    )
    return {
        "wk_avg": avg("WK리그"),
        "national_avg": avg("여자축구 국가대표"),
        "teams": teams,
        "players": players,
    }


def detrend_national(keyword_trends: dict) -> dict:
    """
    국가대표 검색량으로 WK리그 검색을 회귀해 '국대 효과'를 제거한다.
    보정된 관심도 = WK리그 검색에서 국가대표와 함께 움직이는 부분을 뺀 것.
    """
    w_series = keyword_trends.get("WK리그", [])
    n_series = keyword_trends.get("여자축구 국가대표", [])
    if len(w_series) != len(n_series) or len(w_series) < 5:
        return {"available": False}

    dates = [p["date"] for p in w_series]
    w = [p["value"] for p in w_series]
    n = [p["value"] for p in n_series]
    wbar, nbar = _mean(w), _mean(n)

    s_nn = sum((x - nbar) ** 2 for x in n)
    s_ww = sum((x - wbar) ** 2 for x in w)
    s_nw = sum((n[i] - nbar) * (w[i] - wbar) for i in range(len(w)))
    if s_nn == 0 or s_ww == 0:
        return {"available": False}

    b = s_nw / s_nn  # 회귀 기울기
    r = s_nw / ((s_nn * s_ww) ** 0.5)  # 상관계수

    # 보정 = WK리그에서 국대와 함께 움직이는 변동을 제거 (평균은 유지)
    adjusted = [
        {"date": dates[i], "value": round(w[i] - b * (n[i] - nbar), 2)}
        for i in range(len(w))
    ]
    return {
        "available": True,
        "correlation": round(r, 3),
        "explained_ratio": round(r * r * 100, 1),  # 국대로 설명되는 변동 비율(%)
        "adjusted": adjusted,
        "wk_raw": [{"date": dates[i], "value": w[i]} for i in range(len(w))],
        "national": [{"date": dates[i], "value": n[i]} for i in range(len(n))],
    }


# ---------- 인구통계 ----------

def demographics_summary(demographics: dict) -> dict:
    """검색층 핵심 타겟 요약."""
    gender = demographics.get("gender", {})
    age = demographics.get("age", {})
    top_gender = max(gender, key=gender.get) if gender else None
    top_age = max(age, key=age.get) if age else None
    return {
        "top_gender": top_gender,
        "top_gender_pct": round(gender.get(top_gender, 0) * 100, 1) if top_gender else 0,
        "top_age": top_age,
        "top_age_pct": round(age.get(top_age, 0) * 100, 1) if top_age else 0,
        "gender": {k: round(v * 100, 1) for k, v in gender.items()},
        "age": {k: round(v * 100, 1) for k, v in age.items()},
    }


def demographics_evolution(demographics: dict) -> dict:
    """
    연령대별 검색 비중의 시간 변화.
    기간 전반(앞 1/3) vs 후반(뒤 1/3) 비중을 비교해 관심층 이동을 포착.
    """
    age_ts = demographics.get("age_timeseries", {})
    if not age_ts or not any(age_ts.values()):
        return {"available": False}

    ages = list(age_ts.keys())
    n = min(len(s) for s in age_ts.values())
    dates = [p["date"] for p in age_ts[ages[0]]][:n]

    share_ts = {a: [] for a in ages}
    for i in range(n):
        total = sum(age_ts[a][i]["value"] for a in ages)
        for a in ages:
            share = (age_ts[a][i]["value"] / total * 100) if total else 0
            share_ts[a].append({"date": dates[i], "share": round(share, 2)})

    third = max(1, n // 3)
    shifts = {}
    for a in ages:
        early = _mean([s["share"] for s in share_ts[a][:third]])
        late = _mean([s["share"] for s in share_ts[a][-third:]])
        shifts[a] = {"early": round(early, 1), "late": round(late, 1),
                     "change": round(late - early, 1)}

    rising = max(shifts.items(), key=lambda x: x[1]["change"])
    falling = min(shifts.items(), key=lambda x: x[1]["change"])
    return {
        "available": True,
        "age_share_timeseries": share_ts,
        "shifts": shifts,
        "rising_segment": {"age": rising[0], **rising[1]},
        "falling_segment": {"age": falling[0], **falling[1]},
    }


# ---------- 유튜브 ----------

def youtube_format_analysis(youtube: dict) -> list[dict]:
    """영상을 포맷별로 분류하고 평균 반응을 집계."""
    videos = youtube.get("videos", [])
    rows = [{"format": classify_video_format(v["title"]), "views": v["views"],
             "likes": v["likes"], "comments": v["comments"]} for v in videos]
    if not rows:
        return []
    df = pd.DataFrame(rows)
    agg = df.groupby("format").agg(
        video_count=("views", "size"),
        avg_views=("views", "mean"),
        avg_likes=("likes", "mean"),
        avg_comments=("comments", "mean"),
    ).reset_index()
    agg["engagement_rate"] = ((agg["avg_likes"] + agg["avg_comments"])
                              / agg["avg_views"].clip(lower=1) * 100)
    for col in ["avg_views", "avg_likes", "avg_comments"]:
        agg[col] = agg[col].round(0).astype(int)
    agg["engagement_rate"] = agg["engagement_rate"].round(2)
    agg = agg.sort_values("avg_views", ascending=False).reset_index(drop=True)
    return agg.to_dict("records")


def top_videos(youtube: dict, n: int = 5) -> list[dict]:
    """조회수 상위 영상."""
    videos = sorted(youtube.get("videos", []), key=lambda v: v["views"], reverse=True)
    return [{**v, "format": classify_video_format(v["title"])} for v in videos[:n]]


def explain_top_format(youtube_formats: list[dict], youtube: dict) -> dict:
    """가장 잘 나간 포맷이 왜 1위인지 자동 설명 (2위 대비 배수 + 대표 영상)."""
    if not youtube_formats or len(youtube_formats) < 2:
        return {"available": False}
    top, second = youtube_formats[0], youtube_formats[1]
    mult = round(top["avg_views"] / max(second["avg_views"], 1), 1)
    top_fmt_videos = sorted(
        [v for v in youtube.get("videos", [])
         if classify_video_format(v["title"]) == top["format"]],
        key=lambda v: v["views"], reverse=True,
    )[:3]
    return {
        "available": True,
        "top_format": top["format"],
        "avg_views": top["avg_views"],
        "second_format": second["format"],
        "second_avg_views": second["avg_views"],
        "multiplier": mult,
        "video_count": top["video_count"],
        "engagement_rate": top["engagement_rate"],
        "examples": [{"title": v["title"], "views": v["views"]} for v in top_fmt_videos],
    }


def top_videos_with_context(
    youtube: dict, matches: list[dict], search_df: pd.DataFrame,
    articles: list[dict], n: int = 5, window: int = 3,
) -> list[dict]:
    """조회수 상위 영상에 업로드일·관련 경기·뉴스 헤드라인을 자동 매칭.

    영상이 잘 된 이유를 ‘같은 주에 무엇이 있었나’로 귀속한다.
    """
    today = date.today()
    videos = sorted(youtube.get("videos", []), key=lambda v: v["views"], reverse=True)[:n]
    val_by_date = {d.date(): float(v) for d, v in zip(search_df["date"], search_df["value"])}
    s_mean = float(search_df["value"].mean()) if len(search_df) else 0
    s_std = float(search_df["value"].std()) if len(search_df) > 1 else 0

    enriched = []
    for v in videos:
        upload = today - timedelta(days=v.get("published_days_ago", 0))
        nearby_matches = []
        for m in matches:
            try:
                m_date = date.fromisoformat(m["date"])
            except Exception:
                continue
            if abs((m_date - upload).days) <= window:
                nearby_matches.append(
                    f"{m['round']} {m['home']} {m['home_score']}-{m['away_score']} {m['away']}"
                )
        nearby_news = []
        for art in articles:
            try:
                a_date = date.fromisoformat(art["date"])
            except Exception:
                continue
            if abs((a_date - upload).days) <= 2:
                nearby_news.append(art["title"])

        max_val = None
        spike = False
        for k in range(-1, 3):
            day = upload + timedelta(days=k)
            day_val = val_by_date.get(day)
            if day_val is None:
                continue
            max_val = day_val if max_val is None else max(max_val, day_val)
            if s_std > 0 and (day_val - s_mean) / s_std >= 1.5:
                spike = True

        enriched.append({
            **v,
            "format": classify_video_format(v["title"]),
            "upload_date": upload.isoformat(),
            "nearby_matches": nearby_matches[:2],
            "nearby_headlines": nearby_news[:2],
            "search_around": round(max_val, 1) if max_val is not None else None,
            "search_spike_around": spike,
        })
    return enriched


# ---------- 여론 감성 분석 ----------

def sentiment_analysis(youtube: dict, community: dict | None = None) -> dict:
    """유튜브 댓글 + 블로그·카페 본문 발췌를 합쳐 긍/부정/중립을 분류."""
    texts = [{"text": c.get("text", ""), "source": "유튜브"}
             for c in youtube.get("comments_sample", [])]
    if community:
        for ex in community.get("excerpts", []):
            src = "블로그" if ex.get("source") == "blog" else "카페"
            texts.append({"text": ex.get("text", ""), "source": src})

    pos = neg = neu = 0
    examples = {"positive": [], "negative": []}
    source_counts = {}
    for item in texts:
        text = item["text"]
        source_counts[item["source"]] = source_counts.get(item["source"], 0) + 1
        p = sum(1 for w in POSITIVE_WORDS if w in text)
        nv = sum(1 for w in NEGATIVE_WORDS if w in text)
        if p > nv:
            pos += 1
            if len(examples["positive"]) < 3:
                examples["positive"].append(text[:80])
        elif nv > p:
            neg += 1
            if len(examples["negative"]) < 3:
                examples["negative"].append(text[:80])
        else:
            neu += 1
    total = pos + neg + neu
    if total == 0:
        return {"available": False}
    return {
        "available": True,
        "total": total,
        "low_sample": total < 30,
        "source_counts": source_counts,
        "positive": pos, "negative": neg, "neutral": neu,
        "positive_pct": round(pos / total * 100, 1),
        "negative_pct": round(neg / total * 100, 1),
        "neutral_pct": round(neu / total * 100, 1),
        "examples": examples,
    }


# ---------- 커뮤니티 ----------

def community_analysis(community: dict) -> dict:
    """블로그·카페 능동 언급량 요약."""
    blog_daily = community.get("blog_daily", [])
    return {
        "blog_total": community.get("blog_total", 0),
        "cafe_total": community.get("cafe_total", 0),
        "blog_daily": blog_daily,
        "blog_recent_total": sum(p["count"] for p in blog_daily),
    }


# ---------- 경기력 - 관심도 연결 ----------

def match_interest_analysis(matches: list[dict], search_df: pd.DataFrame, days: int) -> dict:
    """경기 속성(중계 여부·접전 여부·득점)과 검색량의 관계를 분석."""
    recent = recent_window(search_df, days)
    date_to_val = {d.strftime("%Y-%m-%d"): float(v)
                   for d, v in zip(recent["date"], recent["value"])}

    enriched = []
    for m in matches:
        total_goals = m["home_score"] + m["away_score"]
        margin = abs(m["home_score"] - m["away_score"])
        has_broadcast = m.get("broadcast", "") not in ("", "없음")
        try:
            d0 = date.fromisoformat(m["date"])
        except Exception:
            continue
        vals = [date_to_val.get((d0 + timedelta(days=k)).isoformat()) for k in (0, 1)]
        vals = [v for v in vals if v is not None]
        search_around = round(_mean(vals), 1) if vals else None
        enriched.append({
            **m, "total_goals": total_goals, "margin": margin,
            "is_close": margin <= 1, "has_broadcast": has_broadcast,
            "search_around": search_around,
        })

    scored = [m for m in enriched if m["search_around"] is not None]

    def avg(subset):
        return round(_mean([m["search_around"] for m in subset]), 1) if subset else None

    b_on = [m for m in scored if m["has_broadcast"]]
    b_off = [m for m in scored if not m["has_broadcast"]]
    close = [m for m in scored if m["is_close"]]
    blowout = [m for m in scored if not m["is_close"]]

    return {
        "available": bool(scored),
        "matches": enriched,
        "match_count": len(matches),
        "broadcast_on_avg": avg(b_on),
        "broadcast_off_avg": avg(b_off),
        "broadcast_on_count": len(b_on),
        "broadcast_off_count": len(b_off),
        "close_avg": avg(close),
        "blowout_avg": avg(blowout),
    }


# ---------- 검색 cross-validation (네이버 vs 구글) ----------

def search_cross_validation(naver_series: list[dict], google_series: list[dict]) -> dict:
    """
    네이버 검색과 구글 트렌즈의 추세가 얼마나 일치하는지 본다.
    상관이 높으면 두 검색층에서 같은 신호 → 결과 신뢰도 ↑.
    """
    if not naver_series or not google_series:
        return {"available": False}
    n_map = {p["date"]: p["value"] for p in naver_series}
    g_map = {p["date"]: p["value"] for p in google_series}
    common = sorted(set(n_map) & set(g_map))
    if len(common) < 7:
        return {"available": False}
    n = [n_map[d] for d in common]
    g = [g_map[d] for d in common]
    nbar, gbar = _mean(n), _mean(g)
    s_nn = sum((x - nbar) ** 2 for x in n)
    s_gg = sum((x - gbar) ** 2 for x in g)
    s_ng = sum((n[i] - nbar) * (g[i] - gbar) for i in range(len(n)))
    if s_nn == 0 or s_gg == 0:
        return {"available": False}
    r = s_ng / ((s_nn * s_gg) ** 0.5)
    return {
        "available": True,
        "correlation": round(r, 3),
        "naver_avg": round(nbar, 2),
        "google_avg": round(gbar, 2),
        "overlap_days": len(common),
        "series": [{"date": common[i], "naver": n[i], "google": g[i]} for i in range(len(common))],
    }


# ---------- 위키피디아 페이지뷰 ----------

def wiki_summary(wiki_pageviews: dict) -> dict:
    """페이지별 총 조회수 + 일별 합계."""
    if not wiki_pageviews:
        return {"available": False}
    page_totals = []
    daily_total: dict[str, int] = {}
    for page, series in wiki_pageviews.items():
        total = sum(p["views"] for p in series)
        page_totals.append({"page": page.replace("_", " "), "total_views": total})
        for p in series:
            daily_total[p["date"]] = daily_total.get(p["date"], 0) + p["views"]
    page_totals.sort(key=lambda x: x["total_views"], reverse=True)
    daily = [{"date": d, "views": v} for d, v in sorted(daily_total.items())]
    return {
        "available": True,
        "page_totals": page_totals,
        "grand_total": sum(p["total_views"] for p in page_totals),
        "daily_total": daily,
    }


# ---------- 빅카인즈 vs 네이버 뉴스 비교 ----------

def bigkinds_summary(bigkinds: dict, naver_news_total: int) -> dict:
    """빅카인즈와 네이버 뉴스의 표본 크기 비교."""
    bk_total = bigkinds.get("total", 0) if bigkinds else 0
    if bk_total == 0:
        return {"available": False}
    multiplier = round(bk_total / naver_news_total, 1) if naver_news_total > 0 else None
    return {
        "available": True,
        "bigkinds_total": bk_total,
        "naver_news_total": naver_news_total,
        "multiplier": multiplier,
        "daily": bigkinds.get("daily", []),
    }


# ---------- 외부 유튜브 채널 ----------

def external_youtube_summary(videos: list[dict], top_n: int = 5) -> dict:
    """KWFF 외 채널들의 WK리그 관련 영상 요약."""
    if not videos:
        return {"available": False}
    # 채널별 집계
    by_channel: dict[str, dict] = {}
    for v in videos:
        ch = v.get("channel", "(미상)")
        if ch not in by_channel:
            by_channel[ch] = {"channel": ch, "video_count": 0, "total_views": 0}
        by_channel[ch]["video_count"] += 1
        by_channel[ch]["total_views"] += v.get("views", 0)
    top_channels = sorted(by_channel.values(), key=lambda x: x["total_views"], reverse=True)[:top_n]
    top_vids = sorted(videos, key=lambda v: v.get("views", 0), reverse=True)[:top_n]
    return {
        "available": True,
        "video_count": len(videos),
        "total_views": sum(v.get("views", 0) for v in videos),
        "top_channels": top_channels,
        "top_videos": top_vids,
    }


# ---------- 통합 ----------

def build_analysis_summary(raw: dict) -> dict:
    """수집된 raw 데이터 → 분석 결과 묶음 (대시보드 + Claude 입력용)."""
    days = raw.get("display_days", 90)
    search_df = build_search_df(raw["search_trend"])

    spikes = detect_spikes(search_df, days)
    spikes_with_news = attach_news_to_spikes(spikes, raw["news"].get("articles", []))

    summary = {
        "weekday_pattern": weekday_pattern(search_df, days),
        "weekday_breakdown": weekday_breakdown(search_df, days, raw["matches"]),
        "high_days": explain_high_days(
            search_df, days, raw["matches"], raw["news"].get("articles", []),
        ),
        "yoy": yoy_comparison(search_df, days),
        "growth": compute_growth(search_df, days),
        "spikes": spikes_with_news,
        "keyword_breakdown": keyword_breakdown(raw["keyword_trends"]),
        "detrend": detrend_national(raw["keyword_trends"]),
        "demographics": demographics_summary(raw["demographics"]),
        "demographics_evolution": demographics_evolution(raw["demographics"]),
        "youtube_formats": youtube_format_analysis(raw["youtube"]),
        "top_videos": top_videos(raw["youtube"]),
        "top_format_explanation": explain_top_format(
            youtube_format_analysis(raw["youtube"]), raw["youtube"],
        ),
        "top_videos_context": top_videos_with_context(
            raw["youtube"], raw["matches"], search_df, raw["news"].get("articles", []),
        ),
        "youtube_meta": {
            "subscribers": raw["youtube"].get("subscribers", 0),
            "total_videos": raw["youtube"].get("total_videos", 0),
            "avg_views": raw["youtube"].get("avg_views", 0),
        },
        "sentiment": sentiment_analysis(raw["youtube"], raw.get("community")),
        "community": community_analysis(raw["community"]),
        "matches": match_interest_analysis(raw["matches"], search_df, days),
        "news_total": sum(d["count"] for d in raw["news"].get("daily", [])),
        "google_naver_xval": search_cross_validation(
            [{"date": p["date"], "value": p["value"]} for p in raw["search_trend"][-days:]],
            raw.get("google_trends", []),
        ),
        "wiki": wiki_summary(raw.get("wiki_pageviews", {})),
        "bigkinds": bigkinds_summary(
            raw.get("bigkinds", {}),
            sum(d["count"] for d in raw["news"].get("daily", [])),
        ),
        "external_youtube": external_youtube_summary(raw.get("external_youtube", [])),
        "is_mock": raw.get("is_mock", False),
        "display_days": days,
    }
    return _to_native(summary)
