"""
KBO 크롤러 — koreabaseball.com 기반
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
ALL_TEAMS = ["KIA", "삼성", "LG", "두산", "KT", "SSG", "롯데", "한화", "NC", "키움"]


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


def get_today_schedule(team: str) -> dict:
    """오늘 해당 팀 예정 경기 - smsScore div 기반"""
    today = date.today().strftime("%Y%m%d")
    try:
        res = requests.get(
            f"{BASE}/Schedule/ScoreBoard.aspx",
            params={"gameDate": today},
            headers=HEADERS, timeout=10
        )
        soup = BeautifulSoup(res.text, "html.parser")
        VENUE_LIST = ["잠실","고척","수원","대전","광주","인천","창원","대구","사직","포항","청주"]

        for box in soup.select("div.smsScore"):
            box_text = box.get_text()
            teams_in = [t for t in ALL_TEAMS if t in box_text]
            if team in teams_in and len(teams_in) >= 2:
                opponent = next((t for t in teams_in if t != team), "")
                venues = [v for v in VENUE_LIST if v in box_text]
                venue = venues[0] if venues else ""
                times = re.findall(r'\d{2}:\d{2}', box_text)
                game_time = times[0] if times else "18:30"
                return {
                    "scheduled": True,
                    "opponent": opponent,
                    "time": game_time,
                    "venue": venue,
                    "note": f"오늘 {game_time} vs {opponent} ({venue})"
                }

        return {"scheduled": False, "note": "오늘 경기 없음"}
    except:
        return {"scheduled": False, "note": "일정 조회 실패"}


def get_last_season_stats(player_id: str, is_pitcher: bool) -> dict:
    """작년 시즌 스탯"""
    last_year = date.today().year - 1
    try:
        if is_pitcher:
            referer = f"{BASE}/Record/Player/PitcherBasic/Basic1.aspx"
            endpoint = f"{BASE}/Record/Player/PitcherBasic/Basic1.aspx/GetPitcherBasicRecords"
        else:
            referer = f"{BASE}/Record/Player/HitterBasic/Basic1.aspx"
            endpoint = f"{BASE}/Record/Player/HitterBasic/Basic1.aspx/GetHitterBasicRecords"

        for page in range(1, 20):
            res = requests.post(
                endpoint,
                data={"seasonId": str(last_year), "leagueId": "1", "teamId": "0", "pageNo": str(page)},
                headers={**HEADERS, "Referer": referer},
                timeout=10
            )
            soup = BeautifulSoup(res.text, "html.parser")
            table = soup.select_one("table")
            if not table:
                break
            col_headers = [th.get_text(strip=True) for th in table.select("thead th")]
            rows = table.select("tbody tr")
            if not rows:
                break
            for row in rows:
                cells = [td.get_text(strip=True) for td in row.select("td")]
                link = row.select_one("a")
                if not cells:
                    continue
                row_id = ""
                if link:
                    m = re.search(r"playerId=(\d+)", link.get("href", ""))
                    if m:
                        row_id = m.group(1)
                if row_id == player_id:
                    return dict(zip(col_headers, cells))
        return {}
    except:
        return {}


def interpret_stats(stats: dict, is_pitcher: bool, games: int, last_stats: dict = None) -> dict:
    """스탯 한글 해석"""
    result = {}
    last_stats = last_stats or {}
    try:
        if is_pitcher:
            era = float(stats.get("ERA", 0) or 0)
            whip = float(stats.get("WHIP", 0) or 0)
            wins = int(stats.get("W", 0) or 0)
            losses = int(stats.get("L", 0) or 0)

            result["labels"] = {"ERA": "평균자책점", "G": "등판", "W": "승", "L": "패", "IP": "이닝", "SO": "탈삼진", "WHIP": "이닝당출루"}
            result["descs"] = {
                "ERA": f"이닝당 {era:.2f}점" + (" 🟢 우수" if era < 3.5 else " 🟡 보통" if era < 5.0 else " 🔴 불안"),
                "WHIP": f"이닝당 {whip:.2f}명 출루허용" + (" 🟢" if whip < 1.2 else " 🟡" if whip < 1.5 else " 🔴"),
                "W": f"{wins}승 {losses}패",
            }
            if last_stats.get("ERA"):
                last_era = float(last_stats.get("ERA", 0) or 0)
                diff = era - last_era
                result["vs_last"] = f"작년 ERA {last_era:.2f} → 올해 {era:.2f} ({'+' if diff>0 else ''}{diff:.2f})"
        else:
            avg = float(stats.get("AVG", 0) or 0)
            hr = int(stats.get("HR", 0) or 0)
            rbi = int(stats.get("RBI", 0) or 0)
            obp = float(stats.get("OBP", 0) or 0)
            slg = float(stats.get("SLG", 0) or 0)
            hr_pace = round(hr / games * 144) if games > 0 else 0

            result["labels"] = {"AVG": "타율", "G": "경기", "HR": "홈런", "RBI": "타점", "OBP": "출루율", "SLG": "장타율"}
            result["descs"] = {
                "AVG": f"10타석에 {avg*10:.1f}개 안타" + (" 🟢 상위권" if avg >= 0.300 else " 🟡 평균" if avg >= 0.260 else " 🔴 하위권"),
                "HR": f"{games}경기 {hr}개 → 시즌 {hr_pace}개 페이스",
                "RBI": f"팀 득점에 {rbi}점 기여",
                "OBP": f"타석의 {obp*100:.0f}% 출루" + (" 🟢" if obp >= 0.380 else " 🟡" if obp >= 0.330 else " 🔴"),
                "SLG": f"장타력 {slg:.3f}" + (" 🟢 강타자" if slg >= 0.500 else " 🟡" if slg >= 0.380 else " 🔴"),
            }
            if last_stats.get("AVG"):
                last_avg = float(last_stats.get("AVG", 0) or 0)
                last_hr = int(last_stats.get("HR", 0) or 0)
                last_g = int(last_stats.get("G", 1) or 1)
                last_hr_pace = round(last_hr / last_g * 144) if last_g > 0 else 0
                avg_diff = avg - last_avg
                result["vs_last"] = (
                    f"작년 타율 {last_avg:.3f} → 올해 {avg:.3f} ({'+' if avg_diff>=0 else ''}{avg_diff:.3f}) | "
                    f"홈런 페이스 작년 {last_hr_pace}개 → 올해 {hr_pace}개"
                )
    except Exception as e:
        print(f"[스탯 해석 오류] {e}")
    return result


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
    interp = data.get("stat_interpretation", {})
    schedule = data.get("today_schedule", {})

    stats_str = ", ".join(f"{k}: {v}" for k, v in stats.items())
    today_str = " ".join(f"{k}:{v}" for k, v in today.items() if k not in ["played","note","일자","상대"]) if today.get("played") else "오늘 미출전"
    vs_last = interp.get("vs_last", "작년 데이터 없음")
    schedule_str = schedule.get("note", "오늘 경기 없음")

    prompt = f"""KBO 구단의 독설 인사팀장으로서 아래 선수의 인사평가 총평을 2~3문장으로 작성하세요.

선수: {data.get('name')} ({data.get('team')}, {data.get('position')})
연봉: {data.get('salary_display')} / 경기당 인건비: {data.get('daily_wage_display')}
시즌 성적: {stats_str}
작년 대비: {vs_last}
오늘 성적: {today_str}
오늘 일정: {schedule_str}
종합 등급: {sg.get('grade')}등급 ({sg.get('grade_label')}) / 가성비 {sg.get('score')}점

규칙:
- 팩트 기반, 연봉 대비 성과 직접 언급
- 작년 대비 변화 언급 (데이터 있을 때만)
- D/C: 강도 높은 쓴소리 (방출/특타 가능)
- S/A: 칭찬하되 기대감 포함
- B: 분발 촉구
- 경어체, 인사팀 공문 스타일, 텍스트만"""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}]
        )
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

    player_id = player_info["player_id"]
    is_pitcher = player_info["is_pitcher"]
    team = player_info["team"]

    today_schedule = get_today_schedule(team)
    last_season_stats = get_last_season_stats(player_id, is_pitcher)
    games = int(season_stats.get("G", 0) or 0)
    stat_interpretation = interpret_stats(season_stats, is_pitcher, games, last_season_stats)

    salary = SALARY_DB.get(name, 30000)
    salary_display = f"{salary // 10000}억" if salary >= 10000 else f"{salary:,}만원"
    if salary >= 10000 and salary % 10000:
        salary_display = f"{salary // 10000}억 {salary % 10000:,}만원"

    season_grade = calculate_season_grade(season_stats, salary, is_pitcher)
    today_grade = calculate_today_grade(today_stats, is_pitcher)

    display_keys = ["ERA","G","W","L","IP","SO","WHIP"] if is_pitcher else ["AVG","G","HR","RBI","OBP","SLG"]
    display_stats = {k: season_stats[k] for k in display_keys if k in season_stats}

    year = date.today().year
    photo_url = f"https://6ptotvmi5753.edge.naverncp.com/KBO_IMAGE/person/middle/{year}/{player_id}.jpg"

    data = {
        "name": player_info["name"], "team": team,
        "position": player_info["position"], "is_pitcher": is_pitcher,
        "salary": salary, "salary_display": salary_display,
        "daily_wage_display": f"{season_grade['daily_wage']:,}만원",
        "season_stats": display_stats,
        "season_grade": season_grade,
        "today_stats": today_stats,
        "today_grade": today_grade,
        "today_schedule": today_schedule,
        "last_season_stats": last_season_stats,
        "stat_interpretation": stat_interpretation,
        "photo_url": photo_url,
        "player_id": player_id,
        "crawled_at": date.today().isoformat(),
    }

    comment = generate_ai_comment(data)
    if comment:
        data["ai_comment"] = comment

    return data
