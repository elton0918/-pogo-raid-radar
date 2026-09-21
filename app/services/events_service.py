import re
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import httpx
from bs4 import BeautifulSoup

import app.data.pokemon_data as pokemon_data
from app.data.pokemon_data import (
    translate_pokemon_name,
    clean_pokemon_name,
    get_pokemon_image_url
)

logger = logging.getLogger(__name__)

EVENT_TAG_MAPPINGS = {
    "raid day": ("⚔️ 團體戰日", "#DC2626"),
    "raid hour": ("⚔️ 團體戰晚餐會", "#EA580C"),
    "raid battles": ("⚔️ 團體戰輪替", "#2563EB"),
    "max mondays": ("💥 極巨星期一", "#7C3AED"),
    "max battles": ("💥 極巨對戰", "#7C3AED"),
    "community day": ("🎉 社群日", "#059669"),
    "pokémon spotlight hour": ("✨ 寶可夢聚焦時刻", "#D97706"),
    "spotlight hour": ("✨ 寶可夢聚焦時刻", "#D97706"),
    "hatch day": ("🥚 孵化日", "#2563EB"),
    "event": ("🎁 限時活動", "#4F46E5"),
    "wild area": ("🌐 曠野地帶", "#0D9488"),
    "season": ("🍂 賽季活動", "#6B7280"),
    "go battle league": ("🥊 對戰聯盟", "#B91C1C"),
    "research": ("📜 調查課題", "#475569"),
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
        return (f"📌 {raw_tag.strip()}", "#4B5563")

    def _translate_event_title(self, title_en: str) -> tuple[str, List[str]]:
        """
        將英文活動標題翻譯為繁體中文，並提取其中主打的寶可夢名稱
        返回: (繁中標題, 主打寶可夢中文名列表)
        """
        pokemon_data._load_database()
        res = title_en
        featured_pokemon = []

        # 優先由長到短比對英文寶可夢名稱，替換為中文並記錄
        sorted_en = sorted(pokemon_data.EN_TO_ZH_DICT.keys(), key=lambda x: len(x), reverse=True)
        for en in sorted_en:
            pattern = r'\b' + re.escape(en) + r'\b'
            if re.search(pattern, res, re.I):
                zh = pokemon_data.EN_TO_ZH_DICT[en]
                if zh not in featured_pokemon:
                    featured_pokemon.append(zh)
                res = re.sub(pattern, zh, res, flags=re.I)

        # 替換常見活動字眼
        replacements = [
            ("Super Mega Raid Day", "極致超級團體戰日"),
            ("Mega Raid Day", "超級團體戰日"),
            ("Raid Day", "團體戰日"),
            ("Raid Hour", "團體戰晚餐會"),
            ("Max Mondays", "極巨星期一"),
            ("Max Monday", "極巨星期一"),
            ("Max Battle Day", "極巨對戰日"),
            ("Max Battles", "極巨對戰"),
            ("Pokémon Spotlight Hour", "聚焦時刻"),
            ("Spotlight Hour", "聚焦時刻"),
            ("Community Day", "社群日"),
            ("in 5-star Raid Battles", "5星傳奇團體戰"),
            ("in 5-star Raids", "5星傳奇團體戰"),
            ("in Mega Raids", "超級團體戰"),
            ("in Shadow Raids", "暗影團體戰"),
            ("Catch Mastery", "捕捉精通"),
            ("Harvest Festival", "豐收祭"),
            ("Taken Over", "火箭隊佔領"),
            ("Halloween", "萬聖節活動"),
            ("Hatch Day", "孵化日"),
            ("Wild Area", "曠野地帶"),
            ("Great League", "超級聯盟"),
            ("Ultra League", "高級聯盟"),
            ("Master League", "大師聯盟"),
            ("Mega Edition", "超級進化版本"),
            ("during", "期間"),
            ("Dynamax", "極巨化"),
            ("Gigantamax", "超極巨化"),
            ("Shadow", "暗影"),
            ("Mega", "超級"),
            ("Local Time", "當地時間"),
        ]

        for en_phrase, zh_phrase in replacements:
            res = re.sub(re.escape(en_phrase), zh_phrase, res, flags=re.I)

        # 清理多餘空白與逗號連接
        res = re.sub(r'\s+,', ',', res)
        res = re.sub(r',\s*and\s+', '、', res, flags=re.I)
        res = re.sub(r'\s+and\s+', '、', res, flags=re.I)
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

    def _parse_event_item(self, item_el, status_type: str = "current") -> Optional[Dict[str, Any]]:
        """解析單一 .event-item 元件"""
        h2 = item_el.find("h2")
        if not h2:
            return None

        title_en = h2.get_text(strip=True)
        if not title_en:
            return None

        tag_badge = item_el.select_one(".event-tag-badge")
        raw_tag = tag_badge.get_text(strip=True) if tag_badge else "Event"
        tag_zh, theme_color = self._normalize_tag(raw_tag)

        title_zh, featured_pokemon = self._translate_event_title(title_en)

        p = item_el.find("p")
        raw_time = p.get_text(strip=True) if p else ""
        time_zh = self._translate_time_str(raw_time)

        img_el = item_el.find("img")
        image_url = img_el.get("src", "") if img_el else ""
        if not image_url:
            # 若無圖片，若有主打寶可夢則自動使用寶可夢立繪
            if featured_pokemon:
                image_url = get_pokemon_image_url(featured_pokemon[0])
            else:
                image_url = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/25.png"

        countdown_el = item_el.select_one(".event-countdown")
        countdown_iso = countdown_el.get("data-countdown", "") if countdown_el else ""
        countdown_to = countdown_el.get("data-countdown-to", "") if countdown_el else ""

        is_raid_event = any(k in raw_tag.lower() for k in ["raid day", "raid hour", "raid battles"]) or "raid" in title_en.lower()

        return {
            "status_type": status_type,
            "title_en": title_en,
            "title_zh": title_zh,
            "raw_tag": raw_tag,
            "tag_zh": tag_zh,
            "theme_color": theme_color,
            "raw_time": raw_time,
            "time_zh": time_zh,
            "countdown_iso": countdown_iso,
            "countdown_to": countdown_to,
            "image_url": image_url,
            "is_raid_event": is_raid_event,
            "featured_pokemon": featured_pokemon
        }

    def _parse_leekduck_events_html(self, html: str) -> Dict[str, Any]:
        """解析 LeekDuck Events 頁面內容"""
        soup = BeautifulSoup(html, "html.parser")
        current_events = []
        upcoming_events = []

        curr_container = soup.select_one(".events-list.current-events")
        if curr_container:
            for it in curr_container.select(".event-item"):
                parsed = self._parse_event_item(it, status_type="current")
                if parsed:
                    current_events.append(parsed)

        up_container = soup.select_one(".events-list.upcoming-events")
        if up_container:
            for it in up_container.select(".event-item"):
                parsed = self._parse_event_item(it, status_type="upcoming")
                if parsed:
                    upcoming_events.append(parsed)

        return {
            "current_events": current_events,
            "upcoming_events": upcoming_events,
            "total_count": len(current_events) + len(upcoming_events)
        }

    def _get_fallback_events(self) -> Dict[str, Any]:
        """離線內建備援活動名單"""
        now = datetime.now()
        return {
            "current_events": [
                {
                    "status_type": "current",
                    "title_en": "Staraptor Super Mega Raid Day",
                    "title_zh": "超級姆克鷹 極致超級團體戰日",
                    "raw_tag": "Raid Day",
                    "tag_zh": "⚔️ 團體戰日",
                    "theme_color": "#DC2626",
                    "raw_time": "14:00 - 17:00",
                    "time_zh": "14:00 - 17:00 (當地時間)",
                    "countdown_iso": "",
                    "countdown_to": "end",
                    "image_url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/398.png",
                    "is_raid_event": True,
                    "featured_pokemon": ["姆克鷹"]
                }
            ],
            "upcoming_events": [
                {
                    "status_type": "upcoming",
                    "title_en": "Max Mondays",
                    "title_zh": "急凍鳥、閃電鳥、火焰鳥 極巨星期一",
                    "raw_tag": "Max Mondays",
                    "tag_zh": "💥 極巨星期一",
                    "theme_color": "#7C3AED",
                    "raw_time": "Mon, 18:00 - 19:00",
                    "time_zh": "週一 18:00 - 19:00 (當地時間)",
                    "countdown_iso": "",
                    "countdown_to": "start",
                    "image_url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/144.png",
                    "is_raid_event": True,
                    "featured_pokemon": ["急凍鳥", "閃電鳥", "火焰鳥"]
                }
            ],
            "total_count": 2
        }

    def get_events(self, force_refresh: bool = False) -> Dict[str, Any]:
        """[同步方法] 取得當前與即將到來的活動名單"""
        now = datetime.now()
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
        now = datetime.now()
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
