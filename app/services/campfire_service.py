import logging
import math
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

class CampfireService:
    """
    Niantic Campfire 官方/社群 API 串接模組
    
    具備：
    1. 透過個人 Campfire Token 發送 GraphQL Bounding Box 地理區塊查詢
    2. 雙模支援：提供同步 (sync) 與非同步 (async) 團體戰資料拉取
    3. 空間 TTL 記憶體快取：避免短時間重複查詢 Niantic 觸發速率限制 (Rate Limit)
    4. 健壯的資料正規化：自動相容 ISO 8601 與 Unix Timestamp 倒數計算
    5. 優雅降級 (Graceful Fallback)：無 Token、過期或超時時自動切換至社群動態回報與道館快取
    6. 社群眾包即時回報功能 (Crowdsourced Raid Reporting)
    """

    def __init__(self):
        self.auth_token = settings.CAMPFIRE_AUTH_TOKEN
        self.endpoint = settings.CAMPFIRE_API_ENDPOINT
        self.timeout = settings.CAMPFIRE_TIMEOUT_SECONDS
        self.cache_ttl = settings.CAMPFIRE_CACHE_TTL_SECONDS
        self.fallback_to_mock = settings.CAMPFIRE_FALLBACK_TO_MOCK

        # 社群即時動態回報之道館團體戰清單
        self.dynamic_raids: List[Dict[str, Any]] = []

        # 空間 TTL 記憶體快取字典: Key -> {"expires_at": datetime, "data": List[dict]}
        self._spatial_cache: Dict[str, Dict[str, Any]] = {}

    def _get_cache_key(self, lat: float, lon: float, radius_km: float) -> str:
        """生成基於網格的空間快取鍵值 (約 1.1km 聚合區間)"""
        grid_lat = round(lat, 2)
        grid_lon = round(lon, 2)
        return f"{grid_lat}_{grid_lon}_{round(radius_km, 1)}"

    def _get_from_cache(self, cache_key: str) -> Optional[List[Dict[str, Any]]]:
        """檢查並取出未過期之空間快取"""
        now = datetime.now()
        entry = self._spatial_cache.get(cache_key)
        if entry and entry["expires_at"] > now:
            logger.info(f"⚡ [Campfire Cache Hit] 命中空間快取: {cache_key} (共 {len(entry['data'])} 筆)")
            return [dict(item) for item in entry["data"]]
        return None

    def _set_to_cache(self, cache_key: str, data: List[Dict[str, Any]]):
        """存入空間快取並設定過期時間"""
        now = datetime.now()
        self._spatial_cache[cache_key] = {
            "expires_at": now + timedelta(seconds=self.cache_ttl),
            "data": data
        }

    def clear_cache(self):
        """清理已過期的快取"""
        now = datetime.now()
        expired_keys = [k for k, v in self._spatial_cache.items() if v["expires_at"] <= now]
        for k in expired_keys:
            del self._spatial_cache[k]

    def add_reported_raid(
        self,
        gym_name: str,
        boss_name: str,
        tier: int = 5,
        lat: float = 25.033964,
        lon: float = 121.564468,
        duration_minutes: int = 45,
        cp: str = "52150",
        reporter: str = "社群訓練家"
    ) -> Dict[str, Any]:
        """
        供玩家在 LINE 或透過 API 動態回報即時團體戰
        """
        now = datetime.now()
        expire_time = now + timedelta(minutes=duration_minutes)

        new_raid = {
            "gym_id": f"dyn_{int(now.timestamp())}_{abs(hash(gym_name)) % 10000}",
            "gym_name": gym_name,
            "boss_name": boss_name,
            "tier": tier,
            "cp": cp,
            "types": ["傳說"],
            "latitude": lat,
            "longitude": lon,
            "duration_minutes": duration_minutes,
            "created_at": now,
            "expire_at": expire_time,
            "source": "community_report",
            "reporter": reporter
        }

        # 移除同道館先前的舊資料，加入最新回報
        self.dynamic_raids = [r for r in self.dynamic_raids if r["gym_name"] != gym_name]
        self.dynamic_raids.append(new_raid)
        logger.info(f"📢 [Campfire 社群回報] 道館: {gym_name}, 頭目: {boss_name}, 回報者: {reporter}")
        return new_raid

    def cleanup_expired(self):
        """清除已結束之社群動態回報與過期快取"""
        now = datetime.now()
        self.dynamic_raids = [r for r in self.dynamic_raids if r["expire_at"] > now]
        self.clear_cache()

    def _build_graphql_payload(self, lat: float, lon: float, radius_km: float) -> tuple[dict, dict]:
        """計算 Bounding Box 並生成 GraphQL 請求內容與標頭"""
        lat_delta = radius_km / 111.0
        # 考慮緯度對經度大圓距離之縮放
        rad = math.radians(lat)
        cos_lat = math.cos(rad)
        lon_delta = radius_km / (111.0 * max(0.1, cos_lat))

        payload = {
            "query": """
            query GetNearbyRaids($minLat: Float!, $maxLat: Float!, $minLng: Float!, $maxLng: Float!) {
                gyms(minLat: $minLat, maxLat: $maxLat, minLng: $minLng, maxLng: $maxLng) {
                    id
                    name
                    latitude
                    longitude
                    raid {
                        bossName
                        tier
                        cp
                        endTime
                        startTime
                    }
                }
            }
            """,
            "variables": {
                "minLat": lat - lat_delta,
                "maxLat": lat + lat_delta,
                "minLng": lon - lon_delta,
                "maxLng": lon + lon_delta
            }
        }

        headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json",
            "User-Agent": "Campfire/1.0 (iOS; zh-TW)",
            "Accept": "application/json"
        }

        return payload, headers

    def _parse_end_time_to_minutes(self, end_time_val: Any) -> int:
        """解析各種可能的結束時間格式 (Unix Timestamp 或 ISO 字串)"""
        now = datetime.now()
        default_duration = 45

        if not end_time_val:
            return default_duration

        try:
            # 數字或數值字串 (Timestamp)
            if isinstance(end_time_val, (int, float)) or (isinstance(end_time_val, str) and end_time_val.isdigit()):
                ts = float(end_time_val)
                # 毫秒單位換算 (大於 1e11)
                if ts > 1e11:
                    ts = ts / 1000.0
                end_dt = datetime.fromtimestamp(ts)
                diff = int((end_dt - now).total_seconds() / 60)
                return max(1, min(diff, 60))
            # ISO 格式字串
            elif isinstance(end_time_val, str):
                cleaned = end_time_val.replace("Z", "+00:00")
                end_dt = datetime.fromisoformat(cleaned).replace(tzinfo=None)
                diff = int((end_dt - now).total_seconds() / 60)
                return max(1, min(diff, 60))
        except Exception as e:
            logger.debug(f"無法解析結束時間 '{end_time_val}': {e}")

        return default_duration

    def _normalize_raids_data(self, raw_data: Any) -> List[Dict[str, Any]]:
        """將 Niantic Campfire 回應解析為標準團體戰結構"""
        results = []
        if not raw_data:
            return results

        # 支援 GraphQL 標準結構: data -> gyms
        gym_list = []
        if isinstance(raw_data, dict):
            if "data" in raw_data and isinstance(raw_data["data"], dict):
                gym_list = raw_data["data"].get("gyms", [])
            elif "gyms" in raw_data:
                gym_list = raw_data.get("gyms", [])
        elif isinstance(raw_data, list):
            gym_list = raw_data

        for item in gym_list:
            raid = item.get("raid")
            if not raid:
                continue

            boss_name = raid.get("bossName") or raid.get("pokemonName") or raid.get("boss_name", "未知頭目")
            tier = raid.get("tier", 5)
            cp = str(raid.get("cp", "未知"))
            duration_minutes = self._parse_end_time_to_minutes(raid.get("endTime") or raid.get("end_time"))

            results.append({
                "gym_id": item.get("id") or item.get("gym_id") or f"cf_{abs(hash(item.get('name', '')))}",
                "gym_name": item.get("name") or item.get("gym_name", "神秘道館"),
                "boss_name": boss_name,
                "tier": tier,
                "cp": cp,
                "types": ["傳說"],
                "latitude": float(item.get("latitude") or item.get("lat", 0.0)),
                "longitude": float(item.get("longitude") or item.get("lon") or item.get("lng", 0.0)),
                "duration_minutes": duration_minutes,
                "remaining_minutes": duration_minutes,
                "source": "campfire_live"
            })

        return results

    async def fetch_campfire_raids(
        self,
        lat: float,
        lon: float,
        radius_km: float = 5.0
    ) -> List[Dict[str, Any]]:
        """
        [異步 API] 向 Niantic Campfire 伺服器請求周遭半徑的團體戰資料
        """
        self.cleanup_expired()
        cache_key = self._get_cache_key(lat, lon, radius_km)

        # 1. 優先讀取 TTL 空間快取
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            return cached + self.dynamic_raids

        # 2. 若未配置 Token，切換至本地動態社群回報
        if not self.auth_token:
            logger.info("未設置 CAMPFIRE_AUTH_TOKEN，切換為社群回報模式")
            return self.dynamic_raids

        # 3. 發送真實 Campfire GraphQL 查詢
        payload, headers = self._build_graphql_payload(lat, lon, radius_km)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(self.endpoint, json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    parsed = self._normalize_raids_data(data)
                    self._set_to_cache(cache_key, parsed)
                    logger.info(f"🔥 [Campfire Live] 成功取得 {len(parsed)} 筆即時團體戰")
                    return parsed + self.dynamic_raids
                else:
                    logger.warning(f"Campfire 回傳 HTTP {resp.status_code}: {resp.text[:150]}")
        except Exception as e:
            logger.error(f"Campfire 異步請求異常: {e}")

        return self.dynamic_raids

    def fetch_campfire_raids_sync(
        self,
        lat: float,
        lon: float,
        radius_km: float = 5.0
    ) -> List[Dict[str, Any]]:
        """
        [同步 API] 供同步邏輯（如 LINE WebhookHandler）安全呼叫
        """
        self.cleanup_expired()
        cache_key = self._get_cache_key(lat, lon, radius_km)

        # 1. 優先讀取空間快取
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            return cached + self.dynamic_raids

        # 2. 若未配置 Token，切換為社群動態回報
        if not self.auth_token:
            return self.dynamic_raids

        # 3. 同步發送 Campfire GraphQL 查詢
        payload, headers = self._build_graphql_payload(lat, lon, radius_km)
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(self.endpoint, json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    parsed = self._normalize_raids_data(data)
                    self._set_to_cache(cache_key, parsed)
                    logger.info(f"🔥 [Campfire Live Sync] 成功取得 {len(parsed)} 筆即時團體戰")
                    return parsed + self.dynamic_raids
                else:
                    logger.warning(f"Campfire 同步回傳 HTTP {resp.status_code}: {resp.text[:150]}")
        except Exception as e:
            logger.error(f"Campfire 同步請求異常: {e}")

        return self.dynamic_raids

    def check_connection(self) -> Dict[str, Any]:
        """診斷 Campfire 連線設定與狀態"""
        has_token = bool(self.auth_token and len(self.auth_token) > 10)
        return {
            "configured": has_token,
            "endpoint": self.endpoint,
            "timeout_seconds": self.timeout,
            "cache_ttl_seconds": self.cache_ttl,
            "active_cache_entries": len(self._spatial_cache),
            "dynamic_raids_count": len(self.dynamic_raids),
            "status": "ready" if has_token else "fallback_mode"
        }

campfire_service = CampfireService()
