"""Public Saha site scope, URL deduplication and robots wildcard matching."""
import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

SITE_SEEDS = ["https://www.saha.go.kr" + path for path in (
    "/main.do", "/portal/guide/siteMap.do?mId=0703000000",
    "/tour/main.do", "/health/main.do", "/hadanlib/main.do",
    "/dadaelib/main.do", "/eulsukdo/main.do", "/reserve/main.do",
    "/news/main.do", "/comm/main.do", "/photo/main.do",
    "/happyedu/main.do", "/startup/main.do",
)]
FILE_EXTENSIONS = (".pdf", ".hwp", ".hwpx", ".doc", ".docx", ".xls", ".xlsx",
                   ".ppt", ".pptx", ".zip", ".txt", ".csv", ".jpg", ".jpeg",
                   ".png", ".gif", ".webp", ".svg", ".mp4", ".mp3")
TRACKING = {"utm_source", "utm_medium", "utm_campaign", "fbclid", "gclid", "jsessionid"}
PRIVATE = re.compile(r"/(?:cert|login|logout|join|member|mypage|admin|auth)(?:/|\.)|"
                     r"/(?:write|insert|delete|update|save|inRealName)\.(?:do|jsp)", re.I)


def official_host(host: str) -> bool:
    return host == "saha.go.kr" or host.endswith(".saha.go.kr")


def canonical_url(value: str, base: str = SITE_SEEDS[0]) -> str | None:
    value = (value or "").strip()
    if not value or value.startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
        return None
    try:
        p = urlsplit(urljoin(base, value))
        host = (p.hostname or "").lower()
        port = p.port
    except ValueError:
        return None
    if p.scheme not in ("http", "https") or not official_host(host) or p.username or p.password:
        return None
    if port not in (None, 80, 443):
        return None
    if host == "saha.go.kr":
        host = "www.saha.go.kr"
    path = re.sub(r";jsessionid=[^/;?]*", "", p.path or "/", flags=re.I)
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=False)
             if k.lower() not in TRACKING and k.lower() not in ("backurl", "returnurl")]
    # The article identifier is sufficient; issue-navigation context otherwise
    # creates many URLs for the same newspaper article.
    if any(k in ("nIdx", "bIdx") for k, _ in query):
        query = [(k, v) for k, v in query if k not in ("curHo", "pageIndex", "page", "searchKeyword", "searchType")]
    return urlunsplit(("https", host, path, urlencode(sorted(set(query))), ""))


def is_attachment(url: str) -> bool:
    p = urlsplit(url)
    return p.path.lower().endswith(FILE_EXTENSIONS) or any(
        hint in p.path.lower() for hint in ("filedown", "download", "/fms/"))


def skip_reason(url: str) -> str | None:
    p = urlsplit(url)
    if PRIVATE.search(p.path):
        return "authentication_or_write_endpoint"
    if re.search(r"/(?:search|integratedSearch)\.", p.path, re.I):
        return "search_navigation"
    if re.search(r'calendar|schedule|booking', p.path, re.I) and any(
            k.lower() in ("year", "month", "date", "startdate", "enddate", "searchdate", "searchmonth", "searchyear")
            for k, _ in parse_qsl(p.query)):
        return "calendar_or_date_navigation"
    return None


class RobotsRules:
    """Implement * and $ which urllib.robotparser treats as literal text.

    Unknown/failed policies are deferred, not silently treated as permission.
    """
    def __init__(self, text: str):
        self.rules = []
        agents = []
        seen_rule = False
        for line in text.splitlines():
            line = line.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, value = (part.strip() for part in line.split(":", 1))
            key = key.lower()
            if key == "user-agent":
                if seen_rule:
                    agents, seen_rule = [], False
                agents.append(value.lower())
            elif key in ("allow", "disallow"):
                seen_rule = True
                if value and any(a in ("*", "sahaknowledgebot") for a in agents):
                    anchored = value.endswith("$")
                    expression = re.escape(value[:-1] if anchored else value).replace(r"\*", ".*")
                    self.rules.append((len(value.replace("*", "")), key == "allow",
                                       re.compile("^" + expression + ("$" if anchored else ""))))

    def allowed(self, url: str) -> bool:
        p = urlsplit(url)
        target = p.path + ("?" + p.query if p.query else "")
        matches = [(length, allow) for length, allow, pattern in self.rules if pattern.search(target)]
        return max(matches, default=(0, True))[1]


def site_category(url: str) -> str:
    p = urlsplit(url)
    prefix = p.path.strip("/").split("/")[0]
    categories = {"tour": "문화관광", "health": "보건소", "hadanlib": "하단도서관",
                  "dadaelib": "다대도서관", "eulsukdo": "을숙도문화회관", "reserve": "통합예약",
                  "news": "사하구보", "comm": "소통공감", "photo": "사하사진첩",
                  "happyedu": "평생학습", "startup": "창업지원"}
    if prefix in categories:
        return categories[prefix]
    mid = dict(parse_qsl(p.query)).get("mId", "")[:2]
    return {"01": "전자민원", "02": "구민참여", "03": "정보공개", "04": "분야별정보",
            "05": "사하복지", "06": "사하소개"}.get(mid, "공식홈페이지")
