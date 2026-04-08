"""
KBO 크롤러 — koreabaseball.com 기반
kbo_v4.py 로직을 FastAPI용으로 모듈화
"""
import requests
import os
import re
from bs4 import BeautifulSoup
from datetime import date

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

BASE = "https://www.koreabaseball.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Referer": BASE,
}

SALARY_DB = {
    "양의지": 420000, "김재환": 130000, "정수빈": 80000, "허경민": 80000,
    "최정": 220000, "박성한": 80000, "최지훈": 50000, "한유섬": 80000,
    "고영표": 260000, "강백호": 100000, "박영현": 50000, "소형준": 60000,
    "류현진": 210000, "노시환": 160000, "문동주": 100000, "채은성": 80000,
    "양현종": 150000, "나성범": 150000, "김도영": 80000, "이의리": 90000,
    "오지환": 140000, "홍창기": 80000, "임찬규": 40000, "김현수": 60000,
    "구자욱": 200000, "오승환": 60000, "강민호": 70000, "원태인": 90000,
    "박세웅": 210000, "전준우": 80000,
    "구창모": 90000, "박민우": 80000, "손아섭": 70000,
    "안우진": 70000, "김혜성": 60000, "송성문": 50000,
    "박동원": 50000, "유영찬": 40000, "백정현": 45000,
    "권희동": 22500, "김형준": 11000, "이용규": 20000,
}

SEASON_GAMES = 144


def search_player(name: str) -> dict:
    res = requests.get(f"{BASE}/Player/Search.aspx", params={"searchWord": name}, headers=HEADERS, timeout=10)
    soup = BeautifulSoup(res.text, "html.parser")
    table = soup.select_one("table")
    if not table:
        return {}
    for row in table.select("tbody tr"):
        cells = [td.get_text(strip=True) for td in row.select("td")]
        link = row.select_one("a")
        if not link or len(cells) < 4:
            continue
        if cells[1] == name:
            href = link.get("href", "")
            pid = re.search(r"playerId=(\d+)", href)
            return {
                "player_id": pid.group(1) if pid else "",
                "name": cells[1], "team": cells[2],
                "position": cells[3], "is_pitcher": "투수" in cells[3],
            }
    return {}


def get_player_detail(player_info: dict) -> dict:
    pid = player_info["player_id"]
    is_pitcher = player_info["is_pitcher"]
    url = f"{BASE}/Record/Player/{'Pitcher' if is_pitcher else 'Hitter'}Detail/Basic.aspx"
    res = requests.get(url, params={"playerId": pid}, headers={**HEADERS, "Referer": f"{BASE}/Record/Player/"}, timeout=10)
    soup = BeautifulSoup(res.text, "html.parser")
    tables = soup.select("table")
    season_stats, daily_records = {}, []

    if is_pitcher:
        if len(tables) > 0:
            t = tables[0]
            cols = [th.get_text(strip=True) for th in t.select("th")]
            rows = t.select("tbody tr")
            if rows:
                season_stats = dict(zip(cols, [td.get_text(strip=True) for td in rows[0].select("td")]))
        if len(tables) > 2:
            t = tables[2]
            cols = [th.get_text(strip=True) for th in t.select("th")]
            for row in t.select("tbody tr"):
                vals = [td.get_text(strip=True) for td in row.select("td")]
                if vals: daily_records.append(dict(zip(cols, vals)))
    else:
        for i in range(min(2, len(tables))):
            t = tables[i]
            cols = [th.get_text(strip=True) for th in t.select("th")]
            rows = t.select("tbody tr")
            if rows:
                season_stats.update(dict(zip(cols, [td.get_text(strip=True) for td in rows[0].select("td")])))
        if len(tables) > 2:
            t = tables[2]
            cols = [th.get_text(strip=True) for th in t.select("th")]
            for row in t.select("tbody tr"):
                vals = [td.get_text(strip=True) for td in row.select("td")]
                if vals: daily_records.append(dict(zip(cols, vals)))

    return {"season_stats": season_stats, "daily_records": daily_records}


def get_today_stats(daily_records: list) -> dict:
    today = date.today()
    today_str = today.strftime("%m.%d")
    for record in daily_records:
        if record.get("일자", "") == today_str:
            return {**record, "played": True}
    return {"played": False, "note": f"오늘({today_str}) 경기 없음"}


def calculate_season_grade(stats: dict, salary: int, is_pitcher: bool) -> dict:
    daily_wage = round(salary / SEASON_GAMES)
    score = 50.0
    try:
        games = int(stats.get("G", 1) or 1)
        progress = min(max(games / SEASON_GAMES, 0.1), 1.0)
        if is_pitcher:
            era = float(stats.get("ERA", 9.99) or 9.99)
            whip = float(stats.get("WHIP", 2.0) or 2.0)
            wins = int(stats.get("W", 0) or 0)
            raw = max(0, (5.0 - era) * 12) * 0.5 + max(0, (1.5 - whip) * 25) * 0.3 + min(wins * 3, 30) * 0.2
        else:
            avg = float(stats.get("AVG", 0.25) or 0.25)
            hr = int(stats.get("HR", 0) or 0)
            rbi = int(stats.get("RBI", 0) or 0)
            raw = max(0, (avg - 0.2) * 250) * 0.5 + min(hr * 1.2, 36) * 0.3 + min(rbi * 0.4, 24) * 0.2
        score = max(0, min(100, raw - min((salary / 500000) * 15, 20) * progress + 40))
    except: pass

    if score >= 85: g, l = "S", "탁월한 성과 (Superb)"
    elif score >= 70: g, l = "A", "기대 초과 (Exceeds)"
    elif score >= 55: g, l = "B", "보통 (Met Expectations)"
    elif score >= 40: g, l = "C", "성과 미흡 (Below)"
    else: g, l = "D", "심각한 부진 — 방출 검토"
    return {"score": round(score, 1), "grade": g, "grade_label": l, "daily_wage": daily_wage}


def calculate_today_grade(today_stats: dict, is_pitcher: bool) -> dict:
    if not today_stats.get("played"):
        return {"grade": "-", "grade_label": "출전 없음", "score": 0}
    score = 50.0
    try:
        if is_pitcher:
            score = max(0, min(100, (5.0 - float(today_stats.get("ERA", 4.5) or 4.5)) * 20 + 50))
        else:
            h = int(today_stats.get("H", 0) or 0)
            ab = int(today_stats.get("AB", 4) or 4)
            hr = int(today_stats.get("HR", 0) or 0)
            rbi = int(today_stats.get("RBI", 0) or 0)
            score = min(100, (h / ab if ab else 0) * 100 + hr * 15 + rbi * 5 + 20)
    except: pass
    if score >= 80: g, l = "S", "오늘은 레전드급"
    elif score >= 65: g, l = "A", "오늘은 제 몫 이상"
    elif score >= 50: g, l = "B", "그럭저럭 평타"
    elif score >= 35: g, l = "C", "오늘도 애매한 하루"
    else: g, l = "D", "오늘도 연봉이 아깝다"
    return {"grade": g, "grade_label": l, "score": round(score, 1)}


def generate_ai_comment(data: dict) -> str:
    if not ANTHROPIC_AVAILABLE: return ""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key: return ""
    sg = data.get("season_grade", {})
    stats = data.get("season_stats", {})
    today = data.get("today_stats", {})
    stats_str = ", ".join(f"{k}: {v}" for k, v in stats.items())
    today_str = " ".join(f"{k}:{v}" for k, v in today.items() if k not in ["played","note","일자","상대"]) if today.get("played") else "오늘 미출전"
    prompt = f"""KBO 구단 독설 인사팀장으로서 아래 선수의 인사평가 총평을 2~3문장으로 작성하세요.

선수: {data.get('name')} ({data.get('team')}, {data.get('position')})
연봉: {data.get('salary_display')} / 경기당: {data.get('daily_wage_display')}
시즌 성적: {stats_str}
오늘: {today_str}
등급: {sg.get('grade')}등급 ({sg.get('grade_label')}) / {sg.get('score')}점

규칙: 팩트 기반, 연봉 대비 성과 직접 언급, D/C는 쓴소리, S/A는 칭찬+기대, 경어체, 인사팀 공문 스타일, 텍스트만 출력"""
    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(model="claude-sonnet-4-20250514", max_tokens=300, messages=[{"role":"user","content":prompt}])
        return msg.content[0].text.strip()
    except Exception as e:
        print(f"[AI 총평 오류] {e}")
        return ""


def crawl_player(name: str) -> dict:
    player_info = search_player(name)
    if not player_info.get("player_id"):
        return {}

    detail = get_player_detail(player_info)
    season_stats = detail["season_stats"]
    daily_records = detail["daily_records"]
    today_stats = get_today_stats(daily_records)

    salary = SALARY_DB.get(name, 30000)
    salary_display = f"{salary // 10000}억" if salary >= 10000 else f"{salary:,}만원"
    if salary >= 10000 and salary % 10000:
        salary_display = f"{salary // 10000}억 {salary % 10000:,}만원"

    is_pitcher = player_info["is_pitcher"]
    season_grade = calculate_season_grade(season_stats, salary, is_pitcher)
    today_grade = calculate_today_grade(today_stats, is_pitcher)

    display_keys = ["ERA","G","W","L","IP","SO","WHIP"] if is_pitcher else ["AVG","G","HR","RBI","OBP","SLG"]
    display_stats = {k: season_stats[k] for k in display_keys if k in season_stats}

    year = date.today().year
    photo_url = f"https://6ptotvmi5753.edge.naverncp.com/KBO_IMAGE/person/middle/{year}/{player_info['player_id']}.jpg"

    data = {
        "name": player_info["name"], "team": player_info["team"],
        "position": player_info["position"], "is_pitcher": is_pitcher,
        "salary": salary, "salary_display": salary_display,
        "daily_wage_display": f"{season_grade['daily_wage']:,}만원",
        "season_stats": display_stats, "season_grade": season_grade,
        "today_stats": today_stats, "today_grade": today_grade,
        "photo_url": photo_url, "crawled_at": date.today().isoformat(),
    }

    comment = generate_ai_comment(data)
    if comment:
        data["ai_comment"] = comment

    return data
