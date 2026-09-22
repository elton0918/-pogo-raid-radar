import re
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
import httpx
from bs4 import BeautifulSoup

import app.data.pokemon_data as pokemon_data
from app.data.pokemon_data import (
    translate_pokemon_name,
    clean_pokemon_name,
    get_pokemon_image_url
)

logger = logging.getLogger(__name__)

TAIPEI_TZ = timezone(timedelta(hours=8))
WEEKDAYS_ZH = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]

EVENT_TAG_MAPPINGS = {
    "raid day": ("⚔️ 團體戰日", "#DC2626"),
    "raid hour": ("⚔️ 團體戰晚餐會", "#EA580C"),
    "raid battles": ("⚔️ 團體戰輪替", "#2563EB"),
    "max mondays": ("💥 極巨星期一", "#7C3AED"),
    "max monday": ("💥 極巨星期一", "#7C3AED"),
    "max battles": ("💥 極巨對戰", "#7C3AED"),
    "max battle day": ("💥 極巨對戰日", "#7C3AED"),
    "community day": ("🎉 社群日", "#059669"),
    "pokémon spotlight hour": ("✨ 寶可夢聚焦時刻", "#D97706"),
    "spotlight hour": ("✨ 寶可夢聚焦時刻", "#D97706"),
    "hatch day": ("🥚 孵化日", "#2563EB"),
    "event": ("🎁 限時活動", "#4F46E5"),
    "wild area": ("🌐 曠野地帶", "#0D9488"),
    "season": ("🍂 賽季活動", "#6B7280"),
    "go battle league": ("🥊 對戰聯盟", "#B91C1C"),
    "research": ("📜 調查課題", "#475569"),
    "timed research": ("📜 限時調查", "#475569"),
    "special research": ("📜 特殊調查", "#475569"),
    "go pass": ("🎫 GO 通行證", "#0891B2"),
    "choose your path": ("🧭 冒險路線", "#059669"),
}

class EventsService:
    """
    Niantic / LeekDuck 官方活動即時抓取與解析模組
    
    支援：
    1. 爬取 LeekDuck 最新活動（進行中與即將到來）
    2. 自動繁體中文化標籤、活動標題與時間說明
    3. 辨識團體戰日 (Raid Day)、晚餐會 (Raid Hour)、極巨星期一 (Max Mondays)
    4. 提取主打寶可夢名稱，支援直接聯動 5km 雷達搜尋與今日頭目列表
    5. 記憶體快取 (TTL 30分鐘)，避免重複造訪
    6. 離線備援防斷線機制
    """

    def __init__(self):
        self.cache_ttl_seconds = 1800  # 30 分鐘快取
        self._cached_data: Optional[Dict[str, Any]] = None
        self._cache_expires_at: Optional[datetime] = None

    def _normalize_tag(self, raw_tag: str) -> tuple[str, str]:
        """格式化活動標籤與代表色: 返回 (繁中標籤, 色碼)"""
        tag_lower = raw_tag.strip().lower()
        for key, (zh, color) in EVENT_TAG_MAPPINGS.items():
            if key in tag_lower:
                return (zh, color)
        return ("📌 官方活動", "#4B5563")

    def _translate_event_title(self, title_en: str) -> tuple[str, List[str]]:
        """
        將英文活動標題翻譯為繁體中文，並提取其中主打的寶可夢名稱
        返回: (繁中標題, 主打寶可夢中文名列表)
        """
        pokemon_data._load_database()
        res = title_en
        featured_pokemon = []

        # 1. 完整專屬活動與合作活動片語優先替換 (長片語優先)
        special_phrases = [
            ("Pokémon Horizons: The Series Celebration Event", "《寶可夢地平線：系列》慶祝活動"),
            ("Pokémon Horizons Bonus Timed Research", "《寶可夢地平線》加碼限時調查"),
            ("LEGO Stores and Pokémon GO", "樂高門市 x Pokémon GO 合作活動"),
            ("LEGO Stores & Pokémon GO", "樂高門市 x Pokémon GO 合作活動"),
            ("LEGO Stores", "樂高門市"),
            ("Choose Your Path: Twilight Trails", "選擇你的道路：秋暮小徑"),
            ("Choose Your Path", "選擇你的道路"),
            ("Patterns of the Wild", "狂野圖騰"),
            ("Fall Marathon: Buddy Trek", "秋季馬拉松：夥伴健行"),
            ("World Space Week", "世界太空週"),
            ("Harvest Festival 2026: Applin Picking", "豐收祭 2026：採收啃果蟲"),
            ("Harvest Festival: Taken Over", "豐收祭：火箭隊佔領"),
            ("Harvest Festival", "豐收祭"),
            ("Applin Picking", "採收啃果蟲"),
            ("Super Mega Raid Day", "極致超級團體戰日"),
            ("Mega Raid Day", "超級團體戰日"),
            ("Raid Day", "團體戰日"),
            ("Raid Hour", "團體戰晚餐會"),
            ("Max Battle Day", "極巨對戰日"),
            ("Max Battles", "極巨對戰"),
            ("Max Mondays", "極巨星期一"),
            ("Max Monday", "極巨星期一"),
            ("Pokémon Spotlight Hour", "寶可夢聚焦時刻"),
            ("Spotlight Hour", "聚焦時刻"),
            ("Community Day", "社群日"),
            ("Catch Mastery", "捕捉精通"),
            ("Hatch Day", "孵化日"),
            ("Wild Area 2026: Sendai • Tohoku", "曠野地帶 2026：仙台・東北"),
            ("Wild Area 2026: Mexico City", "曠野地帶 2026：墨西哥城"),
            ("Wild Area 2026: Global", "曠野地帶 2026：全球"),
            ("Sendai • Tohoku", "仙台・東北"),
            ("Mexico City", "墨西哥城"),
            ("Wild Area", "曠野地帶"),
            ("Twilight Trails", "秋暮小徑"),
            ("GO Pass", "GO 通行證"),
            ("Bonus Timed Research", "加碼限時調查"),
            ("Timed Research", "限時調查"),
            ("Special Research", "特殊調查"),
            ("Field Research", "田野調查"),
            ("Research Day", "調查日"),
            ("Celebration Event", "慶祝活動"),
            ("Celebration", "慶祝活動"),
            ("in 5-star Raid Battles", "5星傳奇團體戰"),
            ("in 5-star Raids", "5星傳奇團體戰"),
            ("in Mega Raids", "超級團體戰"),
            ("in Shadow Raids", "暗影團體戰"),
            ("during", " "),
            ("Taken Over", "火箭隊佔領"),
            ("Great League: Mega Edition", "超級聯盟：超級進化版"),
            ("Ultra League: Mega Edition", "高級聯盟：超級進化版"),
            ("Master League: Mega Edition", "大師聯盟：超級進化版"),
            ("Great League Edition", "超級聯盟版"),
            ("Ultra League Edition", "高級聯盟版"),
            ("Master League Edition", "大師聯盟版"),
            ("Great League", "超級聯盟"),
            ("Ultra League", "高級聯盟"),
            ("Master League", "大師聯盟"),
            ("Mega Edition", "超級進化版"),
            ("Willpower Cup", "意志盃"),
            ("Retro Cup", "復古盃"),
            ("Mega Color Cup", "超級色彩盃"),
            ("Color Cup", "色彩盃"),
            ("Mega Halloween Cup", "超級萬聖節盃"),
            ("Halloween Cup", "萬聖節盃"),
            ("Fantasy Cup", "奇幻盃"),
            ("Mega Catch Cup", "超級捕捉盃"),
            ("Catch Cup", "捕捉盃"),
            ("Little Cup", "小小盃"),
            ("2026 GO LAIC Cup", "2026 GO 拉丁美洲國際錦標賽盃 (LAIC)"),
            ("Halloween", "萬聖節活動"),
            ("Part II", "第 2 部分"),
            ("Part I", "第 1 部分"),
            ("Global", "全球"),
            ("January", "1月"), ("February", "2月"), ("March", "3月"),
            ("April", "4月"), ("May", "5月"), ("June", "6月"),
            ("July", "7月"), ("August", "8月"), ("September", "9月"),
            ("October", "10月"), ("November", "11月"), ("December", "12月"),
            ("Local Time", "當地時間"),
        ]
        for en_p, zh_p in special_phrases:
            res = re.sub(re.escape(en_p), zh_p, res, flags=re.I)

        # 2. 形態括號比對替換
        form_map = {
            r'\(Hero of Many Battles\)': '(百戰勇者)',
            r'\(Hero\)': '(百戰勇者)',
            r'\(Incarnate Forme\)': '(化身形態)',
            r'\(Incarnate\)': '(化身形態)',
            r'\(Therian Forme\)': '(靈獸形態)',
            r'\(Therian\)': '(靈獸形態)',
            r'\(Origin Forme\)': '(起源形態)',
            r'\(Origin\)': '(起源形態)',
            r'\(Altered Forme\)': '(別種形態)',
            r'\(Altered\)': '(別種形態)',
            r'\(Crowned Sword\)': '(劍之王)',
            r'\(Crowned Shield\)': '(盾之王)',
            r'\(Dawn Wings\)': '(拂曉之翼)',
            r'\(Dusk Mane\)': '(黃昏之鬃)',
            r'\(Standard Forme\)': '(一般形態)',
            r'\(Standard\)': '(一般形態)',
        }
        for en_f, zh_f in form_map.items():
            res = re.sub(en_f, zh_f, res, flags=re.I)

        # 3. 優先由長到短比對英文寶可夢名稱，替換為中文並記錄主打寶可夢
        sorted_en = sorted(pokemon_data.EN_TO_ZH_DICT.keys(), key=lambda x: len(x), reverse=True)
        for en in sorted_en:
            pattern = r'\b' + re.escape(en) + r'\b'
            if re.search(pattern, res, re.I):
                zh = pokemon_data.EN_TO_ZH_DICT[en]
                if zh not in featured_pokemon:
                    featured_pokemon.append(zh)
                res = re.sub(pattern, zh, res, flags=re.I)

        # 4. 前綴字眼與多餘空白修正 (超級、暗影、極巨化無縫銜接寶可夢中文名)
        prefix_fixes = [
            (r'\bMega\b', '超級'),
            (r'\bShadow\b', '暗影'),
            (r'\bDynamax\b', '極巨化'),
            (r'\bGigantamax\b', '超極巨化'),
            (r'超級\s+', '超級'),
            (r'暗影\s+', '暗影'),
            (r'極巨化\s+', '極巨化'),
            (r'超極巨化\s+', '超極巨化'),
            (r'超級噴火龍\s+X', '超級噴火龍X'),
            (r'超級噴火龍\s+Y', '超級噴火龍Y'),
            (r'極巨化\s*極巨對戰日', '極巨對戰日'),
            (r'(\d+月)\s*社群日', r'\1社群日'),
        ]
        for p_en, p_zh in prefix_fixes:
            res = re.sub(p_en, p_zh, res, flags=re.I)

        # 5. 連接詞與標點符號標準化 (全中文頓號、全形冒號、全形直槓)
        res = re.sub(r',\s*and\s+', '、', res, flags=re.I)
        res = re.sub(r'\s+and\s+', '、', res, flags=re.I)
        res = re.sub(r',\s*', '、', res)
        res = re.sub(r'\s*\|\s*', '｜', res)
        res = re.sub(r'\s*:\s*', '：', res)
        res = re.sub(r'\s+', ' ', res).strip()

        return res, featured_pokemon

    def _translate_time_str(self, time_str: str) -> str:
        """轉換英文時間標記為易讀繁中 (例如 Sat, Sep 19, at 5:00 PM Local Time)"""
        if not time_str or time_str.lower() == "calculating...":
            return "時間請見遊戲內公告"

        t = time_str
        days_map = {
            "Mon": "週一", "Tue": "週二", "Wed": "週三", "Thu": "週四",
            "Fri": "週五", "Sat": "週六", "Sun": "週日"
        }
        months_map = {
            "Jan": "1月", "Feb": "2月", "Mar": "3月", "Apr": "4月",
            "May": "5月", "Jun": "6月", "Jul": "7月", "Aug": "8月",
            "Sep": "9月", "Oct": "10月", "Nov": "11月", "Dec": "12月"
        }

        for en_d, zh_d in days_map.items():
            t = re.sub(r'\b' + en_d + r'\b', zh_d, t)
        for en_m, zh_m in months_map.items():
            t = re.sub(r'\b' + en_m + r'\b', zh_m, t)

        t = t.replace("at", "於").replace("Local Time", "當地時間")
        return t.strip()

    def _parse_iso_datetime(self, iso_str: Optional[str]) -> Optional[datetime]:
        """解析 ISO 時間字串為台灣時區 (UTC+8) datetime"""
        if not iso_str:
            return None
        try:
            if "+" in iso_str or iso_str.endswith("Z"):
                dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
                return dt.astimezone(TAIPEI_TZ)
            else:
                dt = datetime.fromisoformat(iso_str)
                return dt.replace(tzinfo=TAIPEI_TZ)
        except Exception:
            return None

    def _format_event_date_zh(self, start_dt: Optional[datetime], end_dt: Optional[datetime], now_dt: datetime) -> str:
        """
        產生活動舉辦日期的繁體中文說明（如「今日進行中 (至 21:00 結束)」、「9月23日 (週三) 18:00 ～ 19:00」）
        """
        today = now_dt.date()
        if start_dt and end_dt:
            s_date = start_dt.date()
            e_date = end_dt.date()
            s_w = WEEKDAYS_ZH[start_dt.weekday()]
            e_w = WEEKDAYS_ZH[end_dt.weekday()]
            if s_date == e_date:
                if s_date == today:
                    if start_dt <= now_dt <= end_dt:
                        return f"🔥 今日進行中 (至 {end_dt.strftime('%H:%M')} 結束)"
                    elif now_dt < start_dt:
                        return f"⏰ 今日 {start_dt.strftime('%H:%M')} ～ {end_dt.strftime('%H:%M')}"
                    else:
                        return f"已於今日 {end_dt.strftime('%H:%M')} 結束"
                else:
                    return f"📅 {s_date.month}月{s_date.day}日 ({s_w}) {start_dt.strftime('%H:%M')} ～ {end_dt.strftime('%H:%M')}"
            else:
                if s_date <= today <= e_date:
                    return f"🔥 進行中 (至 {e_date.month}/{e_date.day} {e_w} {end_dt.strftime('%H:%M')} 結束)"
                elif today < s_date:
                    return f"📅 {s_date.month}/{s_date.day} ({s_w}) ～ {e_date.month}/{e_date.day} ({e_w})"
                else:
                    return f"已結束"
        elif end_dt:
            e_date = end_dt.date()
            e_w = WEEKDAYS_ZH[end_dt.weekday()]
            if e_date == today:
                if now_dt <= end_dt:
                    return f"🔥 今日進行中 (至 {end_dt.strftime('%H:%M')} 結束)"
                else:
                    return f"已於今日 {end_dt.strftime('%H:%M')} 結束"
            elif today < e_date:
                return f"🔥 進行中 (至 {e_date.month}/{e_date.day} {e_w} {end_dt.strftime('%H:%M')} 結束)"
            else:
                return f"已結束"
        elif start_dt:
            s_date = start_dt.date()
            s_w = WEEKDAYS_ZH[start_dt.weekday()]
            if s_date == today:
                return f"⏰ 今日 {start_dt.strftime('%H:%M')} 開始"
            else:
                return f"📅 {s_date.month}月{s_date.day}日 ({s_w}) {start_dt.strftime('%H:%M')} 開始"
        return "詳情請見遊戲內公告"

    def _get_event_priority(self, raw_tag: str) -> int:
        """計算活動排序權重，快閃與焦點活動置頂"""
        tag = raw_tag.lower()
        if "raid day" in tag: return 100
        if "raid hour" in tag: return 90
        if "max mondays" in tag or "max monday" in tag: return 80
        if "community day" in tag: return 75
        if "spotlight hour" in tag: return 70
        if "hatch day" in tag: return 65
        if "event" in tag: return 50
        if "raid battles" in tag or "mega" in tag: return 40
        return 10

    def _parse_leekduck_events_html(self, html: str) -> Dict[str, Any]:
        """
        解析 LeekDuck Events 頁面內容：
        1. 聚合開始與結束時間
        2. 剔除已經結束的活動 (end_dt < now)
        3. 格式化舉辦日期中文說明
        4. 精準劃分為「今日進行中」與「之後即將到來」活動
        """
        soup = BeautifulSoup(html, "html.parser")
        now = datetime.now(TAIPEI_TZ)
        today_date = now.date()

        events_by_href = {}

        # 遍歷頁面中所有活動卡片
        for a in soup.select("a.event-item-link"):
            href = a.get("href")
            if not href:
                continue

            h2 = a.select_one("h2")
            if not h2:
                continue
            title_en = h2.get_text(strip=True)
            if not title_en:
                continue

            badge = a.select_one(".event-tag-badge")
            raw_tag = badge.get_text(strip=True) if badge else "Event"
            p = a.select_one("p")
            raw_time = p.get_text(strip=True) if p else ""
            cd = a.select_one(".event-countdown")
            cd_to = cd.get("data-countdown-to", "") if cd else ""
            cd_val = cd.get("data-countdown", "") if cd else ""
            img = a.select_one("img")
            image_url = img.get("src", "") if img else ""

            if href not in events_by_href:
                tag_zh, theme_color = self._normalize_tag(raw_tag)
                title_zh, featured_pokemon = self._translate_event_title(title_en)
                time_zh = self._translate_time_str(raw_time)

                if not image_url:
                    if featured_pokemon:
                        image_url = get_pokemon_image_url(featured_pokemon[0])
                    else:
                        image_url = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/25.png"

                is_raid_event = any(k in raw_tag.lower() for k in ["raid day", "raid hour", "raid battles"]) or "raid" in title_en.lower()

                events_by_href[href] = {
                    "href": href,
                    "title_en": title_en,
                    "title_zh": title_zh,
                    "raw_tag": raw_tag,
                    "tag_zh": tag_zh,
                    "theme_color": theme_color,
                    "raw_time": raw_time,
                    "time_zh": time_zh,
                    "image_url": image_url,
                    "is_raid_event": is_raid_event,
                    "featured_pokemon": featured_pokemon,
                    "start_time": None,
                    "end_time": None
                }

            if cd_to == "start" and cd_val:
                events_by_href[href]["start_time"] = cd_val
            elif cd_to == "end" and cd_val:
                events_by_href[href]["end_time"] = cd_val

        today_events = []
        upcoming_events = []

        for href, ev in events_by_href.items():
            start_dt = self._parse_iso_datetime(ev["start_time"])
            end_dt = self._parse_iso_datetime(ev["end_time"])
            ev["start_dt"] = start_dt
            ev["end_dt"] = end_dt

            # 1. 核心過濾：已結束活動徹底拿掉 (以當前時間判定)
            if end_dt and end_dt < now:
                continue

            # 2. 核心標示：產生明確舉辦日期/時間
            date_label = self._format_event_date_zh(start_dt, end_dt, now)
            ev["date_label"] = date_label
            ev["priority"] = self._get_event_priority(ev["raw_tag"])

            # 3. 核心劃分：只留今天 (今日進行中) 與之後的活動 (近期即將到來)
            if (start_dt and start_dt.date() == today_date) or (end_dt and end_dt.date() == today_date):
                ev["status_type"] = "current"
                today_events.append(ev)
            elif (start_dt is None or start_dt.date() <= today_date) and (end_dt and end_dt.date() >= today_date):
                ev["status_type"] = "current"
                today_events.append(ev)
            elif start_dt and start_dt.date() > today_date:
                ev["status_type"] = "upcoming"
                upcoming_events.append(ev)
            else:
                ev["status_type"] = "upcoming"
                upcoming_events.append(ev)

        # 今日活動優先依重要性/快閃排序
        today_events.sort(key=lambda x: x["priority"], reverse=True)
        # 之後的活動依舉辦日期由近到遠排序，同日以重要度排序
        upcoming_events.sort(key=lambda x: (x["start_dt"].date() if x["start_dt"] else datetime.max.date(), -x["priority"]))

        return {
            "current_events": today_events,
            "upcoming_events": upcoming_events,
            "total_count": len(today_events) + len(upcoming_events)
        }

    def _get_fallback_events(self) -> Dict[str, Any]:
        """離線內建備援活動名單（確保無已結束項目）"""
        now = datetime.now(TAIPEI_TZ)
        return {
            "current_events": [
                {
                    "status_type": "current",
                    "title_en": "Dynamax Articuno, Zapdos, and Moltres during Max Monday",
                    "title_zh": "急凍鳥、閃電鳥、火焰鳥 極巨星期一",
                    "raw_tag": "Max Mondays",
                    "tag_zh": "💥 極巨星期一",
                    "theme_color": "#7C3AED",
                    "raw_time": "18:00 - 21:00",
                    "time_zh": "18:00 - 21:00 (當地時間)",
                    "date_label": "🔥 今日進行中 (至 21:00 結束)",
                    "countdown_iso": "",
                    "countdown_to": "end",
                    "image_url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/144.png",
                    "is_raid_event": True,
                    "featured_pokemon": ["急凍鳥", "閃電鳥", "火焰鳥"]
                }
            ],
            "upcoming_events": [
                {
                    "status_type": "upcoming",
                    "title_en": "Xurkitree, Pheromosa, and Buzzwole Raid Hour",
                    "title_zh": "電束木、費洛美螂、爆肌蚊 團體戰晚餐會",
                    "raw_tag": "Raid Hour",
                    "tag_zh": "⚔️ 團體戰晚餐會",
                    "theme_color": "#EA580C",
                    "raw_time": "Wed, 18:00 - 19:00",
                    "time_zh": "週三 18:00 - 19:00 (當地時間)",
                    "date_label": "📅 9月23日 (週三) 18:00 ～ 19:00",
                    "countdown_iso": "",
                    "countdown_to": "start",
                    "image_url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/796.png",
                    "is_raid_event": True,
                    "featured_pokemon": ["電束木", "費洛美螂", "爆肌蚊"]
                }
            ],
            "total_count": 2
        }

    def get_events(self, force_refresh: bool = False) -> Dict[str, Any]:
        """[同步方法] 取得當前與即將到來的活動名單"""
        now = datetime.now(TAIPEI_TZ)
        if not force_refresh and self._cached_data and self._cache_expires_at and self._cache_expires_at > now:
            logger.info("⚡ [Events Cache Hit] 命中最新活動快取")
            return self._cached_data

        url = "https://leekduck.com/events/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }

        parsed_data = None
        source = "leekduck_live"

        try:
            with httpx.Client(verify=False, timeout=8.0, follow_redirects=True) as client:
                resp = client.get(url, headers=headers)
                if resp.status_code == 200:
                    parsed_data = self._parse_leekduck_events_html(resp.text)
        except Exception as e:
            logger.warning(f"爬取 LeekDuck Events 失敗: {e}")

        if not parsed_data or parsed_data.get("total_count", 0) == 0:
            logger.warning("LeekDuck Events 解析無資料，切換為離線備援活動")
            parsed_data = self._get_fallback_events()
            source = "offline_fallback"

        result = {
            "source": source,
            "updated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "current_events": parsed_data.get("current_events", []),
            "upcoming_events": parsed_data.get("upcoming_events", []),
            "total_count": parsed_data.get("total_count", 0)
        }

        self._cached_data = result
        self._cache_expires_at = now + timedelta(seconds=self.cache_ttl_seconds)
        return result

    async def get_events_async(self, force_refresh: bool = False) -> Dict[str, Any]:
        """[非同步方法] 取得當前與即將到來的活動名單"""
        now = datetime.now(TAIPEI_TZ)
        if not force_refresh and self._cached_data and self._cache_expires_at and self._cache_expires_at > now:
            return self._cached_data

        url = "https://leekduck.com/events/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        parsed_data = None
        source = "leekduck_live"

        try:
            async with httpx.AsyncClient(verify=False, timeout=8.0, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    parsed_data = self._parse_leekduck_events_html(resp.text)
        except Exception as e:
            logger.warning(f"非同步爬取 LeekDuck Events 失敗: {e}")

        if not parsed_data or parsed_data.get("total_count", 0) == 0:
            parsed_data = self._get_fallback_events()
            source = "offline_fallback"

        result = {
            "source": source,
            "updated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "current_events": parsed_data.get("current_events", []),
            "upcoming_events": parsed_data.get("upcoming_events", []),
            "total_count": parsed_data.get("total_count", 0)
        }

        self._cached_data = result
        self._cache_expires_at = now + timedelta(seconds=self.cache_ttl_seconds)
        return result

    def get_active_raid_events(self) -> List[Dict[str, Any]]:
        """
        取得目前正在進行中的「團體戰日 (Raid Day)」或「晚餐會 (Raid Hour)」活動，
        供 today_raids_service 自動將快閃活動頭目置頂整併進團體戰清單。
        """
        events_data = self.get_events()
        active_raids = []
        for ev in events_data.get("current_events", []):
            if ev.get("is_raid_event") and ev.get("featured_pokemon"):
                active_raids.append(ev)
        return active_raids

events_service = EventsService()
