import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import httpx
from bs4 import BeautifulSoup

from app.data.pokemon_data import (
    translate_pokemon_name,
    clean_pokemon_name,
    translate_type,
    translate_weather,
    get_pokemon_image_url
)

logger = logging.getLogger(__name__)

class TodayRaidsService:
    """
    今日/現行團體戰頭目查詢服務
    
    具備：
    1. 即時爬取 LeekDuck 最新團體戰頭目資訊（5星傳說、超級、暗影、3星、1星）
    2. 自動雙重備援：LeekDuck 連線異常時，自動切換至 ScrapedDuck GitHub JSON 或本機精選名單
    3. 1小時記憶體 TTL 快取，兼顧資料新鮮度與查詢效能
    4. 全中文化翻譯：自動轉換寶可夢中英文名稱、形態（百戰勇者/化身形態等）、屬性與加成天氣
    5. 一鍵連動：提取核心名稱便於直接發起 5km 雷達搜尋或 IV 打手查詢
    """

    def __init__(self):
        self.cache_ttl_seconds = 3600  # 1 小時快取
        self._cached_data: Optional[Dict[str, Any]] = None
        self._cache_expires_at: Optional[datetime] = None

    def get_today_raids(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        [同步核心方法] 取得今日團體戰頭目分組清單
        """
        now = datetime.now()
        if not force_refresh and self._cached_data and self._cache_expires_at and self._cache_expires_at > now:
            logger.info("⚡ [Today Raids Cache Hit] 命中今日團體戰快取")
            return self._cached_data

        # 1. 嘗試由 LeekDuck 網頁即時抓取最新資料
        raids_data = self._fetch_from_leekduck()
        source = "leekduck_live"

        # 2. 若失敗，嘗試 GitHub 備援資料源
        if not raids_data:
            logger.warning("LeekDuck 網頁爬取失敗，嘗試 GitHub 備援資料庫...")
            raids_data = self._fetch_from_github_backup()
            source = "github_backup"

        # 3. 若仍失敗，使用內建安全離線備援
        if not raids_data:
            logger.warning("GitHub 備援亦不可用，採用本機內建離線備援...")
            raids_data = self._get_fallback_raids()
            source = "offline_database"

        # 4. 智慧整併：若當天有進行中的團體戰日 (Raid Day) 或晚餐會 (Raid Hour)，將其頭目置頂插入
        if raids_data:
            raids_data = self._merge_active_event_raids(raids_data)

        result = {
            "source": source,
            "updated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "categories": raids_data,
            "total_bosses": sum(len(cat.get("bosses", [])) for cat in raids_data)
        }

        # 更新快取
        self._cached_data = result
        self._cache_expires_at = now + timedelta(seconds=self.cache_ttl_seconds)
        return result

    async def get_today_raids_async(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        [非同步方法] 供 FastAPI 端點呼叫
        """
        now = datetime.now()
        if not force_refresh and self._cached_data and self._cache_expires_at and self._cache_expires_at > now:
            return self._cached_data

        raids_data = await self._fetch_from_leekduck_async()
        source = "leekduck_live"

        if not raids_data:
            raids_data = await self._fetch_from_github_backup_async()
            source = "github_backup"

        if not raids_data:
            raids_data = self._get_fallback_raids()
            source = "offline_database"

        if raids_data:
            raids_data = self._merge_active_event_raids(raids_data)

        result = {
            "source": source,
            "updated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "categories": raids_data,
            "total_bosses": sum(len(cat.get("bosses", [])) for cat in raids_data)
        }

        self._cached_data = result
        self._cache_expires_at = now + timedelta(seconds=self.cache_ttl_seconds)
        return result

    def _merge_active_event_raids(self, categories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """檢查是否有進行中的團體戰日 (Raid Day) 或晚餐會 (Raid Hour)，將其頭目置頂插入"""
        try:
            from app.services.events_service import events_service
            active_raids = events_service.get_active_raid_events()
            if not active_raids:
                return categories

            existing_boss_names = set()
            for cat in categories:
                for b in cat.get("bosses", []):
                    existing_boss_names.add(b.get("name_zh", "").lower())
                    existing_boss_names.add(b.get("search_name", "").lower())

            event_categories = []
            for ev in active_raids:
                tag_raw = ev.get("raw_tag", "").lower()
                # 針對限時快閃活動（團體戰日 Raid Day、晚餐會 Raid Hour 等）
                if not any(k in tag_raw for k in ["raid day", "raid hour"]):
                    continue

                boss_items = []
                for p_name in ev.get("featured_pokemon", []):
                    if p_name.lower() in existing_boss_names:
                        continue

                    is_mega = "mega" in ev.get("title_en", "").lower() or "超級" in ev.get("title_zh", "")
                    name_prefix = "超級" if is_mega and not p_name.startswith("超級") else ""
                    full_name_zh = f"{name_prefix}{p_name}"

                    img = ev.get("image_url") or get_pokemon_image_url(p_name)
                    boss_items.append({
                        "name_en": ev.get("title_en", p_name),
                        "name_zh": full_name_zh,
                        "search_name": p_name,
                        "shiny_available": True,
                        "types": ["活動特選"],
                        "types_en": ["Event"],
                        "cp_range": "限時開蛋",
                        "boosted_cp": "",
                        "weather_boost": [],
                        "image_url": img,
                        "is_shadow": False,
                        "is_mega": is_mega
                    })
                    existing_boss_names.add(p_name.lower())

                if boss_items:
                    event_categories.append({
                        "tier_title": f"🔥 今日限時活動：{ev.get('tag_zh', '團體戰日')} ({ev.get('title_zh', '')})",
                        "tier_raw": ev.get("raw_tag", "Event"),
                        "badge": "EVENT",
                        "color": "#DC2626",
                        "is_shadow": False,
                        "bosses": boss_items
                    })

            return event_categories + categories
        except Exception as e:
            logger.warning(f"整併活動頭目時發生異常: {e}")
            return categories

    def _normalize_tier_title(self, raw_title: str, is_shadow: bool) -> tuple[str, str, str]:
        """
        格式化 Tier 標題、星級標籤與代表色
        返回: (標題中文, 標籤徽章, 主題色碼)
        """
        raw = raw_title.lower()
        if "mega" in raw:
            return ("🧬 超級團體戰 (Mega Raids)", "MEGA", "#059669")
        elif "5-star" in raw or "5 star" in raw or "tier 5" in raw:
            if is_shadow:
                return ("🌑 5星暗影傳奇團體戰 (Shadow T5)", "SHADOW 5★", "#6B21A8")
            return ("⭐️ 5星傳說團體戰 (Tier 5)", "TIER 5★", "#1E3A8A")
        elif "3-star" in raw or "3 star" in raw or "tier 3" in raw:
            if is_shadow:
                return ("🌑 3星暗影團體戰 (Shadow T3)", "SHADOW 3★", "#7C3AED")
            return ("⚔️ 3星團體戰 (Tier 3)", "TIER 3★", "#2563EB")
        elif "1-star" in raw or "1 star" in raw or "tier 1" in raw:
            if is_shadow:
                return ("🌑 1星暗影團體戰 (Shadow T1)", "SHADOW 1★", "#8B5CF6")
            return ("🐣 1星團體戰 (Tier 1)", "TIER 1★", "#3B82F6")
        elif "elite" in raw:
            return ("👑 菁英團體戰 (Elite Raids)", "ELITE", "#DC2626")
        elif "ultra beast" in raw:
            return ("🌌 究極異獸 (Ultra Beast)", "UB", "#4F46E5")
        else:
            prefix = "🌑 暗影 " if is_shadow else ""
            return (f"{prefix}{raw_title}", "RAID", "#4B5563")

    def _build_boss_item(
        self,
        name_en: str,
        image_url: str,
        shiny: bool,
        types_en: List[str],
        cp_val: str,
        boosted_cp_val: str,
        weather_en: List[str],
        is_shadow: bool
    ) -> Dict[str, Any]:
        """封裝單一頭目物件並完整在地化繁體中文"""
        name_zh = translate_pokemon_name(name_en)
        search_name = clean_pokemon_name(name_zh)
        types_zh = [translate_type(t) for t in types_en if t]
        weather_zh = [translate_weather(w) for w in weather_en if w]
        
        # 確保有圖片 (若 LeekDuck 圖片為相對路徑或空，自動推導 PokeAPI 官方立繪)
        if not image_url or not image_url.startswith("http"):
            image_url = get_pokemon_image_url(search_name)

        return {
            "name_en": name_en,
            "name_zh": name_zh,
            "search_name": search_name,
            "shiny_available": shiny,
            "types": types_zh,
            "types_en": types_en,
            "cp_range": cp_val,
            "boosted_cp": boosted_cp_val,
            "weather_boost": weather_zh,
            "image_url": image_url,
            "is_shadow": is_shadow,
            "is_mega": "mega" in name_en.lower()
        }

    def _parse_leekduck_html(self, html_content: str) -> Optional[List[Dict[str, Any]]]:
        """解析 LeekDuck 團體戰 HTML 結構"""
        try:
            soup = BeautifulSoup(html_content, "html.parser")
            all_tiers = soup.select(".tier")
            if not all_tiers:
                return None

            categories = []
            for t in all_tiers:
                parent_classes = t.parent.get("class", []) if t.parent else []
                is_shadow = "shadow-raid-bosses" in parent_classes
                tier_h2 = t.find("h2")
                raw_tier_label = tier_h2.get_text(strip=True) if tier_h2 else "團體戰"
                
                tier_title_zh, badge, color = self._normalize_tier_title(raw_tier_label, is_shadow)
                
                tier_bosses = []
                for card in t.select(".card"):
                    name_el = card.select_one(".identity .name")
                    if not name_el:
                        continue
                    name_en = name_el.get_text(strip=True)
                    
                    img_el = card.select_one(".boss-img img")
                    img_url = img_el.get("src", "") if img_el else ""
                    shiny = bool(card.select_one(".shiny-icon"))
                    
                    types = [t_el.get_text(strip=True) for t_el in card.select(".boss-type .type-label")]
                    if not types:
                        types = [t_el.get_text(strip=True) for t_el in card.select(".boss-type .type")]
                    
                    cp_el = card.select_one(".cp-range")
                    cp_val = cp_el.get_text(strip=True).replace("CP", "").strip() if cp_el else ""
                    
                    boosted_cp_el = card.select_one(".boosted-cp-row")
                    boosted_cp_val = boosted_cp_el.get_text(strip=True).replace("CP", "").strip() if boosted_cp_el else ""
                    
                    weather = [w.get_text(strip=True) for w in card.select(".weather-pill .label")]

                    tier_bosses.append(self._build_boss_item(
                        name_en=name_en,
                        image_url=img_url,
                        shiny=shiny,
                        types_en=types,
                        cp_val=cp_val,
                        boosted_cp_val=boosted_cp_val,
                        weather_en=weather,
                        is_shadow=is_shadow
                    ))

                if tier_bosses:
                    categories.append({
                        "tier_title": tier_title_zh,
                        "tier_raw": raw_tier_label,
                        "badge": badge,
                        "color": color,
                        "is_shadow": is_shadow,
                        "bosses": tier_bosses
                    })

            return categories if categories else None
        except Exception as e:
            logger.error(f"解析 LeekDuck HTML 失敗: {e}")
            return None

    def _fetch_from_leekduck(self) -> Optional[List[Dict[str, Any]]]:
        """從 LeekDuck 官方網頁抓取 (同步)"""
        url = "https://leekduck.com/raid-bosses/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
        try:
            with httpx.Client(verify=False, timeout=8.0, follow_redirects=True) as client:
                resp = client.get(url, headers=headers)
                if resp.status_code == 200:
                    return self._parse_leekduck_html(resp.text)
        except Exception as e:
            logger.debug(f"連線 LeekDuck 失敗: {e}")
        return None

    async def _fetch_from_leekduck_async(self) -> Optional[List[Dict[str, Any]]]:
        """從 LeekDuck 官方網頁抓取 (非同步)"""
        url = "https://leekduck.com/raid-bosses/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        try:
            async with httpx.AsyncClient(verify=False, timeout=8.0, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    return self._parse_leekduck_html(resp.text)
        except Exception as e:
            logger.debug(f"非同步連線 LeekDuck 失敗: {e}")
        return None

    def _parse_github_json(self, raw_json: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """解析 GitHub 備援 JSON (如 zhenga8533/leak-duck)"""
        try:
            categories = []
            for tier_name, bosses_raw in raw_json.items():
                if not isinstance(bosses_raw, list) or not bosses_raw:
                    continue
                is_shadow = "shadow" in tier_name.lower() or any("shadow" in b.get("name", "").lower() for b in bosses_raw)
                tier_title_zh, badge, color = self._normalize_tier_title(tier_name, is_shadow)
                
                bosses = []
                for b in bosses_raw:
                    name_en = b.get("name", "")
                    shiny = b.get("shiny_available", True)
                    image_url = b.get("asset_url", "")
                    types = b.get("types", [])
                    cp_range = b.get("cp_range", {})
                    cp_val = f"{cp_range.get('min', '')} - {cp_range.get('max', '')}" if cp_range else ""
                    boosted_range = b.get("boosted_cp_range", {})
                    boosted_val = f"{boosted_range.get('min', '')} - {boosted_range.get('max', '')}" if boosted_range else ""
                    
                    bosses.append(self._build_boss_item(
                        name_en=name_en,
                        image_url=image_url,
                        shiny=shiny,
                        types_en=types,
                        cp_val=cp_val,
                        boosted_cp_val=boosted_val,
                        weather_en=[],
                        is_shadow=is_shadow
                    ))
                    
                if bosses:
                    categories.append({
                        "tier_title": tier_title_zh,
                        "tier_raw": tier_name,
                        "badge": badge,
                        "color": color,
                        "is_shadow": is_shadow,
                        "bosses": bosses
                    })
            return categories if categories else None
        except Exception as e:
            logger.error(f"解析 GitHub 備援 JSON 失敗: {e}")
            return None

    def _fetch_from_github_backup(self) -> Optional[List[Dict[str, Any]]]:
        """從 GitHub 備援 API 抓取 (同步)"""
        url = "https://raw.githubusercontent.com/zhenga8533/leak-duck/data/raid_bosses.json"
        try:
            with httpx.Client(verify=False, timeout=6.0) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    return self._parse_github_json(resp.json())
        except Exception as e:
            logger.debug(f"連線 GitHub 備援失敗: {e}")
        return None

    async def _fetch_from_github_backup_async(self) -> Optional[List[Dict[str, Any]]]:
        """從 GitHub 備援 API 抓取 (非同步)"""
        url = "https://raw.githubusercontent.com/zhenga8533/leak-duck/data/raid_bosses.json"
        try:
            async with httpx.AsyncClient(verify=False, timeout=6.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    return self._parse_github_json(resp.json())
        except Exception as e:
            logger.debug(f"非同步連線 GitHub 備援失敗: {e}")
        return None

    def _get_fallback_raids(self) -> List[Dict[str, Any]]:
        """離線內建高品質備援名單 (防斷線機制)"""
        return [
            {
                "tier_title": "⭐️ 5星傳說團體戰 (Tier 5)",
                "tier_raw": "5-Star Raids",
                "badge": "TIER 5★",
                "color": "#1E3A8A",
                "is_shadow": False,
                "bosses": [
                    self._build_boss_item(
                        name_en="Zamazenta (Hero)",
                        image_url="https://cdn.leekduck.com/assets/img/pokemon_icons/pm889.fHERO.icon.png",
                        shiny=True,
                        types_en=["Fighting"],
                        cp_val="2100 - 2188",
                        boosted_cp_val="2625 - 2735",
                        weather_en=["Cloudy"],
                        is_shadow=False
                    )
                ]
            },
            {
                "tier_title": "🧬 超級團體戰 (Mega Raids)",
                "tier_raw": "Mega Raids",
                "badge": "MEGA",
                "color": "#059669",
                "is_shadow": False,
                "bosses": [
                    self._build_boss_item(
                        name_en="Mega Venusaur",
                        image_url="https://cdn.leekduck.com/assets/img/pokemon_icons/pm3.fMEGA.icon.png",
                        shiny=True,
                        types_en=["Grass", "Poison"],
                        cp_val="1480 - 1554",
                        boosted_cp_val="1851 - 1943",
                        weather_en=["Sunny", "Cloudy"],
                        is_shadow=False
                    )
                ]
            },
            {
                "tier_title": "🌑 5星暗影傳奇團體戰 (Shadow T5)",
                "tier_raw": "Shadow 5-Star Raids",
                "badge": "SHADOW 5★",
                "color": "#6B21A8",
                "is_shadow": True,
                "bosses": [
                    self._build_boss_item(
                        name_en="Shadow Thundurus (Incarnate)",
                        image_url="https://cdn.leekduck.com/assets/img/pokemon_icons/pm642.fINCARNATE.icon.png",
                        shiny=True,
                        types_en=["Electric", "Flying"],
                        cp_val="1762 - 1911",
                        boosted_cp_val="2203 - 2389",
                        weather_en=["Rainy", "Windy"],
                        is_shadow=True
                    )
                ]
            },
            {
                "tier_title": "🌑 3星暗影團體戰 (Shadow T3)",
                "tier_raw": "Shadow 3-Star Raids",
                "badge": "SHADOW 3★",
                "color": "#7C3AED",
                "is_shadow": True,
                "bosses": [
                    self._build_boss_item("Shadow Alolan Sandslash", "https://cdn.leekduck.com/assets/img/pokemon_icons/pm28.fALOLA.icon.png", True, ["Ice", "Steel"], "1266 - 1390", "1582 - 1737", ["Snow"], True),
                    self._build_boss_item("Shadow Quagsire", "https://cdn.leekduck.com/assets/img/pokemon_icons/pm195.icon.png", True, ["Water", "Ground"], "1025 - 1138", "1282 - 1423", ["Rainy", "Sunny"], True),
                    self._build_boss_item("Shadow Lampent", "https://cdn.leekduck.com/assets/img/pokemon_icons/pm608.icon.png", True, ["Ghost", "Fire"], "871 - 976", "1089 - 1220", ["Fog", "Sunny"], True)
                ]
            },
            {
                "tier_title": "🌑 1星暗影團體戰 (Shadow T1)",
                "tier_raw": "Shadow 1-Star Raids",
                "badge": "SHADOW 1★",
                "color": "#8B5CF6",
                "is_shadow": True,
                "bosses": [
                    self._build_boss_item("Shadow Machop", "https://cdn.leekduck.com/assets/img/pokemon_icons/pm66.icon.png", True, ["Fighting"], "638 - 730", "798 - 913", ["Cloudy"], True),
                    self._build_boss_item("Shadow Bellsprout", "https://cdn.leekduck.com/assets/img/pokemon_icons/pm69.icon.png", True, ["Grass", "Poison"], "506 - 590", "633 - 738", ["Sunny", "Cloudy"], True),
                    self._build_boss_item("Shadow Torchic", "https://cdn.leekduck.com/assets/img/pokemon_icons/pm255.icon.png", True, ["Fire"], "541 - 624", "677 - 781", ["Sunny"], True),
                    self._build_boss_item("Shadow Bagon", "https://cdn.leekduck.com/assets/img/pokemon_icons/pm371.icon.png", True, ["Dragon"], "575 - 660", "719 - 826", ["Windy"], True)
                ]
            }
        ]

today_raids_service = TodayRaidsService()
