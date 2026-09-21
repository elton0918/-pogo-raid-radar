import json
import os
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

SUBSCRIPTIONS_FILE = "subscriptions.json"

class SubscriptionService:
    """
    管理使用者的推播訂閱 (持久化至 JSON 檔案)
    主要功能: 管理每日 08:00 晨報推播對象（特定寶可夢關鍵字訂閱已下線）
    """
    def __init__(self):
        self.file_path = SUBSCRIPTIONS_FILE
        self._subscriptions: Dict[str, List[str]] = {}
        self.load_subscriptions()

    def load_subscriptions(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    self._subscriptions = json.load(f)
                logger.info(f"成功載入訂閱資料: 共 {len(self._subscriptions)} 位使用者")
            except Exception as e:
                logger.error(f"讀取訂閱資料失敗: {e}")
                self._subscriptions = {}
        else:
            self._subscriptions = {}
            self._save()

    def _save(self):
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self._subscriptions, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"儲存訂閱資料失敗: {e}")

    def is_digest_subscribed(self, user_id: str) -> bool:
        """檢查使用者是否訂閱每日晨報 (若有記錄且無「取消晨報」則為訂閱中)"""
        if user_id not in self._subscriptions:
            return False
        keywords = self._subscriptions.get(user_id, [])
        return "取消晨報" not in keywords and "不收晨報" not in keywords

    def set_digest_subscription(self, user_id: str, enable: bool) -> bool:
        """開啟或關閉使用者的每日晨報推播"""
        if user_id not in self._subscriptions:
            self._subscriptions[user_id] = []

        keywords = self._subscriptions[user_id]
        if enable:
            self._subscriptions[user_id] = [k for k in keywords if k not in ["取消晨報", "不收晨報"]]
            if "晨報" not in self._subscriptions[user_id]:
                self._subscriptions[user_id].append("晨報")
        else:
            self._subscriptions[user_id] = [k for k in keywords if k != "晨報"]
            if "取消晨報" not in self._subscriptions[user_id]:
                self._subscriptions[user_id].append("取消晨報")
        self._save()
        return True

    def add_subscription(self, user_id: str, keyword: str) -> bool:
        keyword = keyword.strip()
        if not keyword:
            return False
            
        if user_id not in self._subscriptions:
            self._subscriptions[user_id] = []
            
        if keyword not in self._subscriptions[user_id]:
            self._subscriptions[user_id].append(keyword)
            self._save()
            return True
        return False

    def remove_subscription(self, user_id: str, keyword: str) -> bool:
        keyword = keyword.strip()
        if user_id in self._subscriptions and keyword in self._subscriptions[user_id]:
            self._subscriptions[user_id].remove(keyword)
            self._save()
            return True
        return False

    def remove_user(self, user_id: str) -> bool:
        """移除指定使用者"""
        if user_id in self._subscriptions:
            del self._subscriptions[user_id]
            self._save()
            return True
        return False

    def get_user_subscriptions(self, user_id: str) -> List[str]:
        return self._subscriptions.get(user_id, [])

    def get_all_subscribers(self) -> List[str]:
        """取得所有已登記的使用者 user_id 清單"""
        return list(self._subscriptions.keys())

    def get_digest_subscribers(self) -> List[str]:
        """
        取得晨報推播對象：
        包含所有登記且未取消晨報的使用者
        """
        subscribers = []
        for user_id, keywords in self._subscriptions.items():
            if "取消晨報" not in keywords and "不收晨報" not in keywords:
                subscribers.append(user_id)
        return subscribers

    def get_subscribers_for_raid(self, boss_name: str, gym_name: str) -> List[str]:
        """
        比對是否有使用者的關鍵字包含在頭目名稱或道館名稱中
        （原特定寶可夢訂閱功能已下線，保留安全介面避免相依模組出錯）
        """
        subscribers = []
        for user_id, keywords in self._subscriptions.items():
            for kw in keywords:
                if kw in ["晨報", "取消晨報", "不收晨報"]:
                    continue
                if kw in boss_name or kw in gym_name:
                    subscribers.append(user_id)
                    break
        return subscribers

subscription_service = SubscriptionService()

