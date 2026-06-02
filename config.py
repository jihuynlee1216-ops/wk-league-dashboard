"""
WK리그(여자축구) 단독 분석 설정.

WK리그의 검색 관심도·인구통계·유튜브 반응·여론·경기력을 공개 데이터로 추적하고,
데이터 기반으로 다음 타겟층과 실행 액션을 도출한다.
"""

LEAGUE_NAME = "WK리그"

# 검색 트렌드 메인 키워드 (네이버 데이터랩 키워드 그룹)
SEARCH_KEYWORDS = ["WK리그", "여자축구"]

# 구단별 키워드 — 어느 구단이 검색 관심을 끄는지 분리 추적 (2026 WK리그 8개 구단)
TEAM_KEYWORDS = {
    "인천현대제철": ["인천현대제철", "현대제철 여자축구"],
    "화천KSPO": ["화천KSPO", "화천 여자축구"],
    "수원FC위민": ["수원FC위민", "수원FC 위민"],
    "세종스포츠토토": ["세종스포츠토토 여자축구", "세종 여자축구"],
    "경주한수원WFC": ["경주한수원WFC", "경주한국수력원자력", "경주 여자축구"],
    "서울시청": ["서울시청 여자축구"],
    "강진스완스": ["강진스완스", "강진WFC", "강진 여자축구"],
    "상무여자축구단": ["상무여자축구단", "상무 여자축구"],
}

# 선수별 키워드 — 스타 선수 팬덤을 추적 (사용자가 채워넣으면 됨)
# 예: PLAYER_KEYWORDS = {"지소연": ["지소연"], "추효주": ["추효주"]}
PLAYER_KEYWORDS: dict[str, list[str]] = {}

# 국가대표 키워드 — WK리그 검색에서 '국대 스필오버' 효과를 분리(디트렌딩)하기 위함
NATIONAL_TEAM_KEYWORDS = ["여자축구 국가대표", "여자 국가대표", "여자축구 대표팀"]

# 유튜브 채널 — 한국여자축구연맹(KWFF), 현재 운영 중인 활성 채널
# (구 'WK-League' 채널 UCdJSYoCwbiN-CN8YZm_yc5w 는 2022년 12월 이후 방치됨)
YOUTUBE_CHANNEL_ID = "UCTKwSI8N9ObC6t0opgGnW4Q"

# YouTube 전체에서 검색할 키워드 (KWFF 채널 외 외부 영상 수집용)
YOUTUBE_SEARCH_QUERY = "WK리그"

# 위키피디아 페이지 (한국어판)
# 페이지 제목은 ko.wikipedia.org에서 정확히 일치해야 한다.
WIKI_ARTICLES = [
    "WK리그",
    "인천_현대제철_레드엔젤스",
    "수원_FC_위민",
    "화천_KSPO_여자축구단",
]

# 구글 트렌즈 키워드 (네이버와 cross-validation용)
GOOGLE_TRENDS_KEYWORDS = ["WK리그"]

# 인구통계 세그먼트
AGE_GROUPS = ["10대", "20대", "30대", "40대", "50대", "60대 이상"]
GENDERS = ["남성", "여성"]

# 유튜브 영상 포맷 분류 — 제목에 아래 키워드가 있으면 해당 포맷으로 분류.
# 순서 중요: 위에서부터 검사하므로 구체적인 포맷(HL·Goal)을 먼저, 풀경기를 마지막에.
VIDEO_FORMATS = {
    "하이라이트": ["하이라이트", "highlight", "hlㅣ", "ㅣhl", "hl ", "[hl]"],
    "골장면": ["goalㅣ", "ㅣgoal", "goal ", "골장면"],
    "골모음": ["골모음", "골 모음"],
    "인터뷰/회견": ["인터뷰", "interview", "기자회견", "미디어데이"],
    "선수/팀 소개": ["프로필", "드래프트", "신인선수", "선수소개"],
    "이벤트/시상": ["시상", "어워드", "발대식", "행사"],
    "풀경기": ["vs", "round", "라운드", "풀경기", "다시보기"],
}
DEFAULT_FORMAT = "기타"

# 스파이크 유형 분류 규칙 — 관련 뉴스 헤드라인에 아래 키워드가 있으면 해당 유형으로 태깅.
# 순서 중요: 위에서부터 검사.
SPIKE_TYPE_RULES = {
    "국가대표 이벤트": ["국가대표", "대표팀", "월드컵", "올림픽", "아시안컵", "awcl",
                   "아시아", "평가전", "벤투", "감독 선임"],
    "사건/사고/논란": ["논란", "사고", "징계", "폭행", "부상", "사망", "재정", "해체", "퇴출"],
    "선수 이슈": ["이적", "은퇴", "복귀", "계약", "영입", "mvp", "수상", "데뷔"],
    "명경기/경기 결과": ["역전", "우승", "승리", "패배", "무승부", "선두", "결승", "더비"],
    "행사/지역사회": ["축구교실", "행사", "캠페인", "기부", "팬", "유소년", "저변"],
}
DEFAULT_SPIKE_TYPE = "기타"

# 분석 기간 (일)
DEFAULT_PERIOD_DAYS = 90

# 변화율 계산 윈도우 (일)
GROWTH_WINDOW_DAYS = 14

# 스파이크 감지 임계 z-score
SPIKE_Z_THRESHOLD = 2.0

# Claude 모델
CLAUDE_MODEL = "claude-opus-4-7"

# 대시보드 색상 — WK리그 로고 그라데이션 팔레트 (스카이블루 → 퍼플 → 마젠타)
COLOR = "#BD5F9C"          # WK 마젠타 (메인)
COLOR_BLUE = "#85C2EB"     # WK 스카이블루 (보조)
COLOR_BLUE_DEEP = "#5BA8DD"  # 진한 스카이블루 (라인·텍스트 강조)
COLOR_PURPLE = "#9C99C5"   # WK 퍼플 (중간톤)
COLOR_DARK = "#2E2A4A"     # 본문 텍스트 (진남보라)

# 다계열 차트용 색상 시퀀스 (로고 그라데이션 순서)
PALETTE = ["#85C2EB", "#9C99C5", "#BD5F9C", "#5BA8DD", "#D78FC0", "#7B74B5", "#A8D5F0", "#E6A3CC"]

# 경기 기록 CSV 경로
MATCH_RECORDS_CSV = "data/match_records.csv"


def classify_video_format(title: str) -> str:
    """영상 제목으로 포맷 분류."""
    lowered = title.lower()
    for fmt, keywords in VIDEO_FORMATS.items():
        if any(kw.lower() in lowered for kw in keywords):
            return fmt
    return DEFAULT_FORMAT


def classify_spike_type(headlines: list[str]) -> str:
    """스파이크 관련 뉴스 헤드라인들로 스파이크 유형 분류."""
    joined = " ".join(headlines).lower()
    if not joined.strip():
        return DEFAULT_SPIKE_TYPE
    for spike_type, keywords in SPIKE_TYPE_RULES.items():
        if any(kw.lower() in joined for kw in keywords):
            return spike_type
    return DEFAULT_SPIKE_TYPE
