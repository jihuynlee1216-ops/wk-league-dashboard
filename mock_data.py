"""
API 키가 없을 때 사용하는 WK리그 더미 데이터.

검색·키워드별·인구통계·유튜브·뉴스·커뮤니티·경기기록을 현실적으로 모사한다.
스파이크 날짜를 한 번 정해서 검색·뉴스에 동일 반영 → 데이터 간 일관성 유지.
"""

import math
import random
from datetime import date, timedelta

from config import NATIONAL_TEAM_KEYWORDS, PLAYER_KEYWORDS, TEAM_KEYWORDS

RNG = random.Random(20260521)

BASELINE = 12  # WK리그 검색 베이스라인 (네이버 데이터랩 상대 인덱스 0~100)

# 검색층 인구통계 (네이버 실측 경향: 10대·여성 비중 높음)
DEMOGRAPHICS = {
    "gender": {"남성": 0.46, "여성": 0.54},
    "age": {"10대": 0.245, "20대": 0.188, "30대": 0.170,
            "40대": 0.144, "50대": 0.134, "60대 이상": 0.119},
}

# 구단별 검색 베이스라인 (인천현대제철이 가장 높음)
TEAM_BASELINES = {
    "인천현대제철": 7.0, "화천KSPO": 3.2, "수원FC위민": 3.8, "세종스포츠토토": 2.5,
    "경주한수원WFC": 2.8, "서울시청": 2.2, "강진스완스": 2.0, "상무여자축구단": 3.0,
}

SPIKE_HEADLINES = [
    "여자축구 국가대표 차출 명단 발표, WK리그 선수 대거 포함",
    "여자축구 대표팀 평가전 승리… WK리그도 주목",
    "WK리그 {team} 극적 역전승, 여자축구 관심 집중",
    "{team}, WK리그 선두 등극… 시즌 판도 흔들",
    "WK리그 올스타전 흥행, 관중 동원 신기록",
]
NORMAL_HEADLINES = [
    "WK리그 {round}라운드 경기 결과 정리",
    "{team} 감독 \"다음 경기 준비 만전\"",
    "WK리그 주간 MVP에 {team} 선수 선정",
    "여자축구 유소년 축구교실 개최",
    "WK리그 일정 안내 및 중계 정보",
]
TEAMS = list(TEAM_BASELINES.keys())

POSITIVE_COMMENTS = [
    "경기 너무 재밌어요 응원합니다", "선수들 멋있다 최고", "여자축구 매력있네요 잘 봤습니다",
    "골 장면 대박 ㅠㅠ 감동", "다음 경기도 기대됩니다", "현장 직관 갔는데 분위기 좋았어요",
    "우리 팀 화이팅 사랑해요", "수준 높아졌다 재밌게 봄",
]
NEGATIVE_COMMENTS = [
    "중계 화질이 너무 안 좋아요", "왜 이렇게 홍보가 안 되나요 아쉽다", "경기장 접근성이 별로네요",
    "심판 판정 아쉽다", "관중이 너무 적어서 아쉬워요", "일정 정보 찾기가 너무 힘들다",
]
NEUTRAL_COMMENTS = [
    "다음 경기 언제인가요", "중계 어디서 봐요", "선수 명단 어디서 확인하나요",
    "티켓 예매 방법 알려주세요", "경기 결과 정리 감사합니다",
]

BROADCASTS = ["유튜브 중계", "유튜브 중계", "쿠팡플레이", "없음", "없음", "없음"]


def _spike_day_indices(days: int) -> list[int]:
    """표시 기간(최근 days일) 안에서 스파이크가 발생할 날의 인덱스."""
    n_spikes = max(2, days // 30)
    return sorted(RNG.sample(range(days), k=n_spikes))


def generate_search_trend(days: int, spike_idx: list[int]) -> list[dict]:
    """일별 검색 인덱스. YoY 비교 위해 (days+365)일치 생성."""
    total = days + 365
    end = date.today()
    start = end - timedelta(days=total - 1)
    spike_abs = {365 + i for i in spike_idx}
    series = []
    for i in range(total):
        d = start + timedelta(days=i)
        seasonal = math.sin(i / 365 * 2 * math.pi) * BASELINE * 0.18
        weekend = BASELINE * 0.30 if d.weekday() in (5, 6) else 0
        noise = RNG.gauss(0, BASELINE * 0.13)
        spike = BASELINE * RNG.uniform(2.5, 5.0) if i in spike_abs else 0
        value = max(0.0, min(100.0, BASELINE + seasonal + weekend + noise + spike))
        series.append({"date": d.isoformat(), "value": round(value, 1)})
    return series


def _simple_series(days: int, baseline: float, spike_idx: list[int], spike_mult: float = 3.0) -> list[dict]:
    """범용 일별 시계열 생성기."""
    end = date.today()
    start = end - timedelta(days=days - 1)
    spike_set = set(spike_idx)
    series = []
    for i in range(days):
        d = start + timedelta(days=i)
        weekend = baseline * 0.25 if d.weekday() in (5, 6) else 0
        noise = RNG.gauss(0, baseline * 0.15)
        spike = baseline * RNG.uniform(spike_mult * 0.6, spike_mult) if i in spike_set else 0
        value = max(0.0, round(baseline + weekend + noise + spike, 2))
        series.append({"date": d.isoformat(), "value": value})
    return series


def generate_keyword_trends(days: int) -> dict:
    """WK리그·국가대표·구단·선수별 검색 트렌드."""
    spike_idx = _spike_day_indices(days)
    result = {}
    # WK리그 (표시 기간만)
    result["WK리그"] = _simple_series(days, BASELINE, spike_idx, spike_mult=3.5)
    # 국가대표 — 베이스라인 높고 스파이크가 WK리그와 상당 부분 겹침 (스필오버 모사)
    natl_spikes = spike_idx + RNG.sample(range(days), k=2)
    result["여자축구 국가대표"] = _simple_series(days, BASELINE * 2.6, natl_spikes, spike_mult=4.0)
    # 구단별
    for team, base in TEAM_BASELINES.items():
        result[team] = _simple_series(days, base, RNG.sample(range(days), k=2), spike_mult=2.5)
    # 선수별 (config에 등록된 경우만)
    for player in PLAYER_KEYWORDS:
        result[player] = _simple_series(days, RNG.uniform(2, 6), RNG.sample(range(days), k=2))
    return result


def generate_demographics(days: int) -> dict:
    """검색층 인구통계 — 기간 평균 + 일별 시계열. 10대 비중이 점차 상승하도록 설정."""
    end = date.today()
    start = end - timedelta(days=days - 1)

    # 연령대별 베이스 인덱스 (10대는 기간에 걸쳐 상승)
    age_base = {"10대": 16, "20대": 20, "30대": 18, "40대": 15, "50대": 14, "60대 이상": 11}
    age_ts = {}
    for age, base in age_base.items():
        series = []
        for i in range(days):
            d = start + timedelta(days=i)
            drift = (i / days) * 12 if age == "10대" else 0  # 10대만 점진 상승
            noise = RNG.gauss(0, base * 0.12)
            series.append({"date": d.isoformat(), "value": max(0.0, round(base + drift + noise, 2))})
        age_ts[age] = series

    gender_base = {"남성": 17, "여성": 20}
    gender_ts = {}
    for g, base in gender_base.items():
        series = []
        for i in range(days):
            d = start + timedelta(days=i)
            noise = RNG.gauss(0, base * 0.12)
            series.append({"date": d.isoformat(), "value": max(0.0, round(base + noise, 2))})
        gender_ts[g] = series

    def _avg_norm(ts: dict) -> dict:
        avgs = {k: sum(p["value"] for p in s) / len(s) for k, s in ts.items()}
        total = sum(avgs.values())
        return {k: round(v / total, 4) for k, v in avgs.items()}

    return {
        "age": _avg_norm(age_ts),
        "gender": _avg_norm(gender_ts),
        "age_timeseries": age_ts,
        "gender_timeseries": gender_ts,
    }


def generate_youtube(n_videos: int = 40) -> dict:
    """채널 통계 + 영상별 데이터 + 댓글 샘플."""
    from config import VIDEO_FORMATS
    formats = list(VIDEO_FORMATS.keys())
    fmt_view_mult = {
        "하이라이트": 1.0, "골장면": 0.25, "골모음": 0.4,
        "인터뷰/회견": 1.1, "선수/팀 소개": 1.4, "이벤트/시상": 0.8, "풀경기": 3.5,
    }
    base_view = 1200
    videos = []
    for _ in range(n_videos):
        fmt = RNG.choice(formats)
        kw = RNG.choice(VIDEO_FORMATS[fmt])
        team = RNG.choice(TEAMS)
        rnd = RNG.randint(1, 12)
        title = f"[2026 WK리그] {team} {kw} {rnd}R"
        views = int(base_view * fmt_view_mult.get(fmt, 1.0) * RNG.uniform(0.4, 2.0))
        videos.append({
            "title": title,
            "views": views,
            "likes": int(views * RNG.uniform(0.015, 0.04)),
            "comments": int(views * RNG.uniform(0.002, 0.008)),
            "published_days_ago": RNG.randint(1, 150),
        })
    videos.sort(key=lambda v: v["published_days_ago"])
    avg_views = sum(v["views"] for v in videos) // max(len(videos), 1)

    # 댓글 샘플 (긍정 우세, 부정·중립 섞임)
    comments = []
    for _ in range(150):
        r = RNG.random()
        if r < 0.5:
            text = RNG.choice(POSITIVE_COMMENTS)
        elif r < 0.78:
            text = RNG.choice(NEUTRAL_COMMENTS)
        else:
            text = RNG.choice(NEGATIVE_COMMENTS)
        comments.append({"text": text, "likes": RNG.randint(0, 25)})

    return {
        "subscribers": 2610,
        "total_videos": 208,
        "avg_views": avg_views,
        "videos": videos,
        "comments_sample": comments,
    }


def generate_news(days: int, spike_idx: list[int]) -> dict:
    """일별 뉴스 기사 수 + 헤드라인 목록."""
    end = date.today()
    start = end - timedelta(days=days - 1)
    spike_set = set(spike_idx)
    daily, articles = [], []
    for i in range(days):
        d = start + timedelta(days=i)
        near_spike = any(abs(i - s) <= 1 for s in spike_set)
        count = RNG.randint(2, 6) + (RNG.randint(8, 18) if near_spike else 0)
        daily.append({"date": d.isoformat(), "count": count})
        n_headlines = 2 if i in spike_set else (1 if RNG.random() < 0.25 else 0)
        for _ in range(n_headlines):
            pool = SPIKE_HEADLINES if near_spike else NORMAL_HEADLINES
            tmpl = RNG.choice(pool)
            articles.append({"date": d.isoformat(),
                             "title": tmpl.format(team=RNG.choice(TEAMS), round=RNG.randint(1, 12))})
    return {"daily": daily, "articles": articles}


def generate_community(days: int) -> dict:
    """블로그·카페 능동 언급량 + 본문 발췌(감성 분석 보강용)."""
    spike_idx = _spike_day_indices(days)
    blog_daily = _simple_series(days, 3.0, spike_idx, spike_mult=2.0)
    blog_daily = [{"date": p["date"], "count": int(round(p["value"]))} for p in blog_daily]
    # 본문 발췌 (긍정 우세)
    excerpts = []
    pool = POSITIVE_COMMENTS * 3 + NEUTRAL_COMMENTS * 2 + NEGATIVE_COMMENTS
    for _ in range(60):
        excerpts.append({"text": RNG.choice(pool), "source": RNG.choice(["blog", "cafe"])})
    return {
        "blog_daily": blog_daily,
        "blog_total": sum(p["count"] for p in blog_daily) * RNG.randint(8, 15),
        "cafe_total": sum(p["count"] for p in blog_daily) * RNG.randint(4, 9),
        "excerpts": excerpts,
    }


def generate_google_trends(days: int) -> list[dict]:
    """구글 트렌즈 일별 인덱스 — 네이버와 비슷한 형태지만 약간 다른 스파이크 위치."""
    spike_idx = _spike_day_indices(days)
    # 구글은 네이버와 사용자층이 달라 스파이크 시점이 살짝 어긋남
    shifted = [(i + RNG.randint(-1, 1)) % days for i in spike_idx]
    return _simple_series(days, BASELINE * 0.7, shifted, spike_mult=3.5)


def generate_wiki_pageviews(days: int) -> dict:
    """위키피디아 페이지뷰 — 작지만 깊은 관심의 프록시."""
    spike_idx = _spike_day_indices(days)
    pages = {}
    page_baselines = {
        "WK리그": 12, "인천_현대제철_레드엔젤스": 4,
        "수원_FC_위민": 3, "화천_KSPO_여자축구단": 2,
    }
    for page, base in page_baselines.items():
        series = _simple_series(days, base, spike_idx, spike_mult=4.0)
        pages[page] = [{"date": p["date"], "views": int(round(p["value"]))} for p in series]
    return pages


def generate_bigkinds(days: int) -> dict:
    """빅카인즈 — 네이버 뉴스보다 표본 10배 큰 한국 언론 기사."""
    end = date.today()
    start = end - timedelta(days=days - 1)
    spike_set = set(_spike_day_indices(days))
    daily = []
    for i in range(days):
        d = start + timedelta(days=i)
        near_spike = any(abs(i - s) <= 1 for s in spike_set)
        # 네이버 뉴스 mock 대비 10배 가량
        count = RNG.randint(15, 40) + (RNG.randint(80, 160) if near_spike else 0)
        daily.append({"date": d.isoformat(), "count": count})
    return {
        "daily": daily,
        "total": sum(p["count"] for p in daily),
    }


def generate_external_youtube(n: int = 30) -> list[dict]:
    """KWFF 외 채널들이 만든 'WK리그' 관련 영상."""
    channel_pool = [
        "스포츠타임", "여자축구 매니아", "축구 하이라이트 채널", "K스포츠 TV",
        "WK리그 팬", "축구 분석가", "여축 뉴스", "스포츠 ON",
    ]
    videos = []
    for i in range(n):
        ch = RNG.choice(channel_pool)
        team = RNG.choice(TEAMS)
        templates = [f"{team} 화제의 장면", f"WK리그 {team} 분석", f"여자축구 {team} 인터뷰"]
        videos.append({
            "title": RNG.choice(templates) + f" #{i+1}",
            "channel": ch,
            "views": RNG.randint(200, 8000),
            "published_days_ago": RNG.randint(1, 120),
        })
    videos.sort(key=lambda v: v["published_days_ago"])
    return videos


def generate_matches() -> list[dict]:
    """경기 기록 — 최근 90일간 약 30경기."""
    end = date.today()
    matches = []
    rnd = 1
    for week in range(13):
        match_date = end - timedelta(days=week * 7 + RNG.randint(0, 2))
        teams = TEAMS.copy()
        RNG.shuffle(teams)
        for j in range(0, min(len(teams) - 1, 4), 2):
            home, away = teams[j], teams[j + 1]
            hs, aws = RNG.randint(0, 4), RNG.randint(0, 4)
            matches.append({
                "date": match_date.isoformat(),
                "round": f"{13 - week}R",
                "home": home,
                "away": away,
                "home_score": hs,
                "away_score": aws,
                "broadcast": RNG.choice(BROADCASTS),
            })
        rnd += 1
    matches.sort(key=lambda m: m["date"])
    return matches


def collect_all_mock(days: int = 90) -> dict:
    """대시보드에 필요한 WK리그 전체 더미 데이터."""
    spike_idx = _spike_day_indices(days)
    return {
        "search_trend": generate_search_trend(days, spike_idx),
        "keyword_trends": generate_keyword_trends(days),
        "demographics": generate_demographics(days),
        "youtube": generate_youtube(),
        "external_youtube": generate_external_youtube(),
        "news": generate_news(days, spike_idx),
        "community": generate_community(days),
        "matches": generate_matches(),
        "google_trends": generate_google_trends(days),
        "wiki_pageviews": generate_wiki_pageviews(days),
        "bigkinds": generate_bigkinds(days),
        "is_mock": True,
        "display_days": days,
    }


if __name__ == "__main__":
    data = collect_all_mock(90)
    print("검색 트렌드 길이:", len(data["search_trend"]))
    print("키워드 트렌드:", list(data["keyword_trends"].keys()))
    print("인구통계 시계열 연령:", list(data["demographics"]["age_timeseries"].keys()))
    print("유튜브 댓글 수:", len(data["youtube"]["comments_sample"]))
    print("커뮤니티:", {k: v for k, v in data["community"].items() if k != "blog_daily"})
    print("경기 수:", len(data["matches"]))
