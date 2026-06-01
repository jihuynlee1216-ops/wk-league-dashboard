"""
WK리그 데이터를 외부 공개 API에서 수집한다.
API 키가 없거나 호출이 실패하면 mock_data로 폴백.

데이터 소스:
- 네이버 데이터랩 검색어 트렌드 API (검색 인덱스 + 키워드별 + 연령/성별 세그먼트)
- 네이버 검색 API (뉴스·블로그·카페 헤드라인/노출량)
- YouTube Data API v3 (채널·영상·댓글)
- 경기 기록 CSV (수동 입력)
"""

from __future__ import annotations

import csv
import os
from datetime import date, timedelta

import requests
from dotenv import load_dotenv

import mock_data
from config import (
    GOOGLE_TRENDS_KEYWORDS,
    MATCH_RECORDS_CSV,
    NATIONAL_TEAM_KEYWORDS,
    PLAYER_KEYWORDS,
    SEARCH_KEYWORDS,
    TEAM_KEYWORDS,
    WIKI_ARTICLES,
    YOUTUBE_CHANNEL_ID,
    YOUTUBE_SEARCH_QUERY,
)

load_dotenv()

NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
BIGKINDS_ACCESS_KEY = os.getenv("BIGKINDS_ACCESS_KEY", "")

DATALAB_URL = "https://openapi.naver.com/v1/datalab/search"
NEWS_SEARCH_URL = "https://openapi.naver.com/v1/search/news.json"
BLOG_SEARCH_URL = "https://openapi.naver.com/v1/search/blog.json"
CAFE_SEARCH_URL = "https://openapi.naver.com/v1/search/cafearticle.json"
YOUTUBE_CHANNEL_URL = "https://www.googleapis.com/youtube/v3/channels"
YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
YOUTUBE_COMMENTS_URL = "https://www.googleapis.com/youtube/v3/commentThreads"
WIKI_PAGEVIEWS_URL = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/ko.wikipedia/all-access/all-agents"
BIGKINDS_URL = "https://tools.kinds.or.kr/search/news"

_MONTHS = {"Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04", "May": "05", "Jun": "06",
           "Jul": "07", "Aug": "08", "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12"}


def _naver_headers() -> dict:
    return {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
        "Content-Type": "application/json",
    }


def _has_naver_keys() -> bool:
    return bool(NAVER_CLIENT_ID and NAVER_CLIENT_SECRET)


def _has_youtube_key() -> bool:
    return bool(YOUTUBE_API_KEY)


def _clean_html(text: str) -> str:
    """검색 API 응답의 HTML 태그·엔티티 제거."""
    for tag in ("<b>", "</b>"):
        text = text.replace(tag, "")
    for ent, ch in (("&quot;", '"'), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&#39;", "'")):
        text = text.replace(ent, ch)
    return text.strip()


# ---------- 네이버 데이터랩: 검색 트렌드 (YoY 위해 days+365 조회) ----------

def fetch_search_trend(days: int = 90) -> list[dict]:
    """WK리그 일별 검색 인덱스. 작년 동기 비교용으로 (days+365)일치 반환."""
    spike_idx = mock_data._spike_day_indices(days)
    if not _has_naver_keys():
        return mock_data.generate_search_trend(days, spike_idx)

    total = days + 365
    end = date.today()
    start = end - timedelta(days=total - 1)
    body = {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "timeUnit": "date",
        "keywordGroups": [{"groupName": "WK리그", "keywords": SEARCH_KEYWORDS}],
    }
    try:
        r = requests.post(DATALAB_URL, json=body, headers=_naver_headers(), timeout=20)
        r.raise_for_status()
        rows = r.json()["results"][0]["data"]
        return [{"date": row["period"], "value": row["ratio"]} for row in rows]
    except Exception as e:
        print(f"[fetch_search_trend] 실패, mock 폴백: {e}")
        return mock_data.generate_search_trend(days, spike_idx)


# ---------- 네이버 데이터랩: 키워드별 트렌드 (구단·선수·국대) ----------

def _datalab_request(groups: list[tuple[str, list[str]]], days: int) -> dict:
    """키워드 그룹 묶음(최대 5개)을 조회 → {label: [{date,value}]}."""
    end = date.today()
    start = end - timedelta(days=days - 1)
    body = {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "timeUnit": "date",
        "keywordGroups": [{"groupName": name, "keywords": kws} for name, kws in groups],
    }
    r = requests.post(DATALAB_URL, json=body, headers=_naver_headers(), timeout=20)
    r.raise_for_status()
    out = {}
    for res in r.json()["results"]:
        out[res["title"]] = [{"date": d["period"], "value": d["ratio"]} for d in res["data"]]
    return out


def fetch_keyword_trends(days: int = 90) -> dict:
    """
    WK리그·국가대표·구단·선수의 검색 트렌드를 분리 추적.
    WK리그를 앵커로 매 배치에 포함시켜 배치 간 스케일을 보정한다.
    """
    if not _has_naver_keys():
        return mock_data.generate_keyword_trends(days)

    anchor = ("WK리그", SEARCH_KEYWORDS)
    rest: list[tuple[str, list[str]]] = [("여자축구 국가대표", NATIONAL_TEAM_KEYWORDS)]
    rest += list(TEAM_KEYWORDS.items())
    rest += list(PLAYER_KEYWORDS.items())

    result: dict[str, list[dict]] = {}
    anchor_ref_mean = None
    try:
        for i in range(0, len(rest), 4):  # 앵커 1 + 4 = 배치당 5개
            batch = [anchor] + rest[i:i + 4]
            data = _datalab_request(batch, days)
            a_series = data.get("WK리그", [])
            a_mean = sum(p["value"] for p in a_series) / len(a_series) if a_series else 0
            if anchor_ref_mean is None:
                anchor_ref_mean = a_mean
                scale = 1.0
                result["WK리그"] = a_series
            else:
                scale = (anchor_ref_mean / a_mean) if a_mean else 1.0
            for label, series in data.items():
                if label == "WK리그":
                    continue
                result[label] = [{"date": p["date"], "value": round(p["value"] * scale, 2)}
                                  for p in series]
        return result
    except Exception as e:
        print(f"[fetch_keyword_trends] 실패, mock 폴백: {e}")
        return mock_data.generate_keyword_trends(days)


# ---------- 네이버 데이터랩: 인구통계 (시계열 포함) ----------

def fetch_demographics(days: int = 90) -> dict:
    """
    연령대·성별 세그먼트별 검색 인덱스.
    기간 평균(비율)과 일별 시계열을 함께 반환.
    """
    if not _has_naver_keys():
        return mock_data.generate_demographics(days)

    end = date.today()
    start = end - timedelta(days=days - 1)
    age_codes = {
        "10대": ["2"], "20대": ["3", "4"], "30대": ["5", "6"],
        "40대": ["7", "8"], "50대": ["9", "10"], "60대 이상": ["11"],
    }
    gender_codes = {"남성": "m", "여성": "f"}

    def _segment_series(ages=None, gender=None) -> list[dict]:
        body = {
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "timeUnit": "date",
            "keywordGroups": [{"groupName": "WK리그", "keywords": SEARCH_KEYWORDS}],
        }
        if ages:
            body["ages"] = ages
        if gender:
            body["gender"] = gender
        for attempt in range(2):
            try:
                r = requests.post(DATALAB_URL, json=body, headers=_naver_headers(), timeout=35)
                r.raise_for_status()
                rows = r.json()["results"][0]["data"]
                return [{"date": d["period"], "value": d["ratio"]} for d in rows]
            except Exception as e:
                if attempt == 1:
                    print(f"[fetch_demographics] 세그먼트 실패: {e}")
                    return []
        return []

    age_ts = {age: _segment_series(ages=codes) for age, codes in age_codes.items()}
    gender_ts = {g: _segment_series(gender=code) for g, code in gender_codes.items()}

    if not any(age_ts.values()) or not any(gender_ts.values()):
        return mock_data.generate_demographics(days)

    def _avg(series: list[dict]) -> float:
        return sum(p["value"] for p in series) / len(series) if series else 0.0

    def _normalize(d: dict) -> dict:
        total = sum(d.values())
        return {k: round(v / total, 4) for k, v in d.items()} if total else d

    age_avg = _normalize({a: _avg(s) for a, s in age_ts.items()})
    gender_avg = _normalize({g: _avg(s) for g, s in gender_ts.items()})

    return {
        "age": age_avg,
        "gender": gender_avg,
        "age_timeseries": age_ts,
        "gender_timeseries": gender_ts,
    }


# ---------- 네이버 뉴스 ----------

def fetch_news(days: int = 90) -> dict:
    """일별 기사 노출량 + 헤드라인 목록 (스파이크 원인 추정용)."""
    if not _has_naver_keys():
        spike_idx = mock_data._spike_day_indices(days)
        return mock_data.generate_news(days, spike_idx)

    keyword = SEARCH_KEYWORDS[0]
    counts: dict[str, int] = {}
    articles: list[dict] = []
    try:
        for start_idx in range(1, 1001, 100):
            r = requests.get(
                NEWS_SEARCH_URL,
                headers=_naver_headers(),
                params={"query": keyword, "display": 100, "start": start_idx, "sort": "date"},
                timeout=20,
            )
            r.raise_for_status()
            items = r.json().get("items", [])
            if not items:
                break
            for item in items:
                pub = item.get("pubDate", "")
                try:
                    p = pub.split(" ")
                    d_str = f"{p[3]}-{_MONTHS[p[2]]}-{p[1].zfill(2)}"
                except Exception:
                    continue
                counts[d_str] = counts.get(d_str, 0) + 1
                articles.append({"date": d_str, "title": _clean_html(item.get("title", ""))})
    except Exception as e:
        print(f"[fetch_news] 실패, mock 폴백: {e}")
        spike_idx = mock_data._spike_day_indices(days)
        return mock_data.generate_news(days, spike_idx)

    end = date.today()
    start = end - timedelta(days=days - 1)
    daily = [{"date": (start + timedelta(days=i)).isoformat(),
              "count": counts.get((start + timedelta(days=i)).isoformat(), 0)}
             for i in range(days)]
    valid = {row["date"] for row in daily}
    articles = [a for a in articles if a["date"] in valid]
    return {"daily": daily, "articles": articles}


# ---------- 네이버 블로그·카페 (커뮤니티 능동 언급) ----------

def fetch_community(days: int = 90) -> dict:
    """
    블로그·카페 검색으로 '능동적 언급량'을 측정.
    description 필드를 본문 발췌로 수집해 감성 분석 표본도 확대한다.
    """
    if not _has_naver_keys():
        return mock_data.generate_community(days)

    keyword = SEARCH_KEYWORDS[0]
    end = date.today()
    start = end - timedelta(days=days - 1)

    blog_counts: dict[str, int] = {}
    blog_total = 0
    cafe_total = 0
    excerpts: list[dict] = []
    try:
        for start_idx in range(1, 401, 100):
            r = requests.get(
                BLOG_SEARCH_URL, headers=_naver_headers(),
                params={"query": keyword, "display": 100, "start": start_idx, "sort": "date"},
                timeout=20,
            )
            r.raise_for_status()
            data = r.json()
            blog_total = data.get("total", blog_total)
            items = data.get("items", [])
            if not items:
                break
            for item in items:
                pd = item.get("postdate", "")
                if len(pd) == 8:
                    d_str = f"{pd[:4]}-{pd[4:6]}-{pd[6:]}"
                    blog_counts[d_str] = blog_counts.get(d_str, 0) + 1
                desc = _clean_html(item.get("description", ""))
                if desc:
                    excerpts.append({"text": desc, "source": "blog"})
        # 카페: total + 본문 발췌 수집
        for start_idx in range(1, 301, 100):
            rc = requests.get(
                CAFE_SEARCH_URL, headers=_naver_headers(),
                params={"query": keyword, "display": 100, "start": start_idx, "sort": "date"},
                timeout=20,
            )
            rc.raise_for_status()
            cdata = rc.json()
            cafe_total = cdata.get("total", cafe_total)
            for item in cdata.get("items", []):
                desc = _clean_html(item.get("description", ""))
                if desc:
                    excerpts.append({"text": desc, "source": "cafe"})
    except Exception as e:
        print(f"[fetch_community] 실패, mock 폴백: {e}")
        return mock_data.generate_community(days)

    blog_daily = [{"date": (start + timedelta(days=i)).isoformat(),
                   "count": blog_counts.get((start + timedelta(days=i)).isoformat(), 0)}
                  for i in range(days)]
    return {
        "blog_daily": blog_daily,
        "blog_total": blog_total,
        "cafe_total": cafe_total,
        "excerpts": excerpts,
    }


# ---------- 구글 트렌즈 (네이버와 cross-validation) ----------

def fetch_google_trends(days: int = 90) -> list[dict]:
    """구글 검색 트렌드 — 네이버에 안 잡히는 검색층을 보완."""
    try:
        from pytrends.request import TrendReq
    except ImportError:
        return mock_data.generate_google_trends(days)
    try:
        pt = TrendReq(hl="ko-KR", tz=540, timeout=(10, 30))
        end = date.today()
        start = end - timedelta(days=days - 1)
        timeframe = f"{start.isoformat()} {end.isoformat()}"
        pt.build_payload(GOOGLE_TRENDS_KEYWORDS, timeframe=timeframe, geo="KR")
        df = pt.interest_over_time()
        if df.empty or GOOGLE_TRENDS_KEYWORDS[0] not in df.columns:
            return mock_data.generate_google_trends(days)
        return [{"date": idx.strftime("%Y-%m-%d"), "value": float(row[GOOGLE_TRENDS_KEYWORDS[0]])}
                for idx, row in df.iterrows()]
    except Exception as e:
        print(f"[fetch_google_trends] 실패, mock 폴백: {e}")
        return mock_data.generate_google_trends(days)


# ---------- 위키피디아 페이지뷰 ----------

def fetch_wiki_pageviews(days: int = 90) -> dict:
    """WK리그·구단 위키 페이지 일별 조회수. '깊은 관심' 신호."""
    end = date.today()
    start = end - timedelta(days=days - 1)
    pages: dict[str, list[dict]] = {}
    headers = {"User-Agent": "WK-League-Dashboard/1.0 (research)"}
    for article in WIKI_ARTICLES:
        try:
            url = (f"{WIKI_PAGEVIEWS_URL}/{requests.utils.quote(article, safe='')}"
                   f"/daily/{start.strftime('%Y%m%d')}/{end.strftime('%Y%m%d')}")
            r = requests.get(url, headers=headers, timeout=20)
            if r.status_code == 404:
                continue  # 페이지 없음
            r.raise_for_status()
            items = r.json().get("items", [])
            series = [{
                "date": f"{it['timestamp'][:4]}-{it['timestamp'][4:6]}-{it['timestamp'][6:8]}",
                "views": int(it.get("views", 0)),
            } for it in items]
            if series:
                pages[article] = series
        except Exception as e:
            print(f"[fetch_wiki_pageviews] {article} 실패: {e}")
            continue
    if not pages:
        return mock_data.generate_wiki_pageviews(days)
    return pages


# ---------- 빅카인즈 (한국언론진흥재단) ----------

def fetch_bigkinds(days: int = 90) -> dict:
    """빅카인즈 뉴스 빅데이터 — 네이버 뉴스 대비 표본 ~10배."""
    if not BIGKINDS_ACCESS_KEY:
        return mock_data.generate_bigkinds(days)
    end = date.today()
    start = end - timedelta(days=days - 1)
    body = {
        "access_key": BIGKINDS_ACCESS_KEY,
        "argument": {
            "query": SEARCH_KEYWORDS[0],
            "published_at": {"from": start.isoformat(), "until": end.isoformat()},
            "fields": ["published_at", "title"],
            "return_size": 1000,
            "return_from": 0,
        },
    }
    try:
        r = requests.post(BIGKINDS_URL, json=body, timeout=30)
        r.raise_for_status()
        result = r.json().get("return_object", {})
        documents = result.get("documents", [])
        counts: dict[str, int] = {}
        for d in documents:
            pub = d.get("published_at", "")[:10]
            if pub:
                counts[pub] = counts.get(pub, 0) + 1
        daily = [{"date": (start + timedelta(days=i)).isoformat(),
                  "count": counts.get((start + timedelta(days=i)).isoformat(), 0)}
                 for i in range(days)]
        total = result.get("total_hits") or sum(p["count"] for p in daily)
        return {"daily": daily, "total": total}
    except Exception as e:
        print(f"[fetch_bigkinds] 실패, mock 폴백: {e}")
        return mock_data.generate_bigkinds(days)


# ---------- KWFF 외 유튜브 채널 ----------

def fetch_external_youtube(max_results: int = 30) -> list[dict]:
    """KWFF 공식 채널 외에서 'WK리그' 키워드로 검색되는 영상들."""
    if not _has_youtube_key():
        return mock_data.generate_external_youtube(max_results)
    try:
        r = requests.get(YOUTUBE_SEARCH_URL, params={
            "part": "snippet", "q": YOUTUBE_SEARCH_QUERY, "order": "relevance",
            "maxResults": min(max_results, 50), "type": "video", "key": YOUTUBE_API_KEY,
        }, timeout=20)
        r.raise_for_status()
        items = r.json().get("items", [])
        video_ids = [it["id"]["videoId"] for it in items]
        if not video_ids:
            return mock_data.generate_external_youtube(max_results)
        v = requests.get(YOUTUBE_VIDEOS_URL, params={
            "part": "snippet,statistics", "id": ",".join(video_ids), "key": YOUTUBE_API_KEY,
        }, timeout=20)
        v.raise_for_status()
        today = date.today()
        result = []
        for item in v.json().get("items", []):
            # KWFF 채널은 제외 (이미 fetch_youtube가 잡음)
            if item["snippet"].get("channelId", "") == YOUTUBE_CHANNEL_ID:
                continue
            pub = item["snippet"].get("publishedAt", "")[:10]
            try:
                days_ago = (today - date.fromisoformat(pub)).days
            except Exception:
                days_ago = 0
            result.append({
                "title": item["snippet"]["title"],
                "channel": item["snippet"].get("channelTitle", ""),
                "views": int(item["statistics"].get("viewCount", 0)),
                "likes": int(item["statistics"].get("likeCount", 0)),
                "comments": int(item["statistics"].get("commentCount", 0)),
                "published_days_ago": days_ago,
            })
        result.sort(key=lambda x: x["views"], reverse=True)
        return result
    except Exception as e:
        print(f"[fetch_external_youtube] 실패, mock 폴백: {e}")
        return mock_data.generate_external_youtube(max_results)


# ---------- YouTube (채널·영상·댓글) ----------

def _fetch_youtube_comments(video_ids: list[str], per_video: int = 30) -> list[dict]:
    """영상별 최신 댓글 일부를 수집 (감성 분석용)."""
    comments = []
    for vid in video_ids[:40]:
        try:
            r = requests.get(
                YOUTUBE_COMMENTS_URL,
                params={
                    "part": "snippet", "videoId": vid, "maxResults": per_video,
                    "order": "relevance", "textFormat": "plainText", "key": YOUTUBE_API_KEY,
                },
                timeout=20,
            )
            if r.status_code != 200:
                continue  # 댓글 비활성화 등
            for it in r.json().get("items", []):
                sn = it["snippet"]["topLevelComment"]["snippet"]
                comments.append({
                    "text": sn.get("textDisplay", ""),
                    "likes": int(sn.get("likeCount", 0)),
                })
        except Exception as e:
            print(f"[_fetch_youtube_comments] {vid} 실패: {e}")
            continue
    return comments


def fetch_youtube(max_videos: int = 50) -> dict:
    """채널 통계 + 최근 영상 목록 + 댓글 샘플."""
    if not _has_youtube_key() or not YOUTUBE_CHANNEL_ID:
        return mock_data.generate_youtube()

    try:
        ch = requests.get(
            YOUTUBE_CHANNEL_URL,
            params={"part": "statistics", "id": YOUTUBE_CHANNEL_ID, "key": YOUTUBE_API_KEY},
            timeout=20,
        )
        ch.raise_for_status()
        ch_items = ch.json().get("items", [])
        if not ch_items:
            return mock_data.generate_youtube()
        stats = ch_items[0]["statistics"]
        subs = int(stats.get("subscriberCount", 0))
        total_videos = int(stats.get("videoCount", 0))

        search = requests.get(
            YOUTUBE_SEARCH_URL,
            params={
                "part": "snippet", "channelId": YOUTUBE_CHANNEL_ID, "order": "date",
                "maxResults": min(max_videos, 50), "type": "video", "key": YOUTUBE_API_KEY,
            },
            timeout=20,
        )
        search.raise_for_status()
        video_ids = [it["id"]["videoId"] for it in search.json().get("items", [])]

        videos = []
        if video_ids:
            v = requests.get(
                YOUTUBE_VIDEOS_URL,
                params={"part": "snippet,statistics", "id": ",".join(video_ids), "key": YOUTUBE_API_KEY},
                timeout=20,
            )
            v.raise_for_status()
            today = date.today()
            for item in v.json().get("items", []):
                pub = item["snippet"].get("publishedAt", "")[:10]
                try:
                    days_ago = (today - date.fromisoformat(pub)).days
                except Exception:
                    days_ago = 0
                videos.append({
                    "title": item["snippet"]["title"],
                    "views": int(item["statistics"].get("viewCount", 0)),
                    "likes": int(item["statistics"].get("likeCount", 0)),
                    "comments": int(item["statistics"].get("commentCount", 0)),
                    "published_days_ago": days_ago,
                })
        videos.sort(key=lambda x: x["published_days_ago"])
        avg_views = (sum(x["views"] for x in videos) // max(len(videos), 1)) if videos else 0

        comments_sample = _fetch_youtube_comments(video_ids)
        return {
            "subscribers": subs,
            "total_videos": total_videos,
            "avg_views": avg_views,
            "videos": videos,
            "comments_sample": comments_sample,
        }
    except Exception as e:
        print(f"[fetch_youtube] 실패, mock 폴백: {e}")
        return mock_data.generate_youtube()


# ---------- 경기 기록 CSV ----------

def load_matches() -> list[dict]:
    """경기 기록 CSV를 읽는다. 없으면 mock."""
    if not os.path.exists(MATCH_RECORDS_CSV):
        return mock_data.generate_matches()
    try:
        with open(MATCH_RECORDS_CSV, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        matches = []
        for row in rows:
            try:
                hs, aws = int(row["home_score"]), int(row["away_score"])
            except (ValueError, KeyError):
                continue
            matches.append({
                "date": row["date"].strip(),
                "round": row.get("round", "").strip(),
                "home": row.get("home", "").strip(),
                "away": row.get("away", "").strip(),
                "home_score": hs,
                "away_score": aws,
                "broadcast": row.get("broadcast", "").strip(),
            })
        return matches if matches else mock_data.generate_matches()
    except Exception as e:
        print(f"[load_matches] 실패, mock 폴백: {e}")
        return mock_data.generate_matches()


# ---------- 통합 ----------

def collect_all(days: int = 90) -> dict:
    """대시보드에 필요한 WK리그 전체 데이터 수집."""
    return {
        "search_trend": fetch_search_trend(days),
        "keyword_trends": fetch_keyword_trends(days),
        "demographics": fetch_demographics(days),
        "youtube": fetch_youtube(),
        "external_youtube": fetch_external_youtube(),
        "news": fetch_news(days),
        "community": fetch_community(days),
        "matches": load_matches(),
        "google_trends": fetch_google_trends(days),
        "wiki_pageviews": fetch_wiki_pageviews(days),
        "bigkinds": fetch_bigkinds(days),
        "is_mock": not (_has_naver_keys() or _has_youtube_key()),
        "display_days": days,
    }


def get_api_status() -> dict:
    return {
        "naver": _has_naver_keys(),
        "youtube": _has_youtube_key(),
        "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
        "bigkinds": bool(BIGKINDS_ACCESS_KEY),
    }
