import logging
from typing import Dict, Any

from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    PushMessageRequest,
    TextMessage
)

from app.config import settings
from app.services.subscription_service import subscription_service

logger = logging.getLogger(__name__)

class NotificationService:
    def __init__(self):
        self.line_config = Configuration(access_token=settings.LINE_CHANNEL_ACCESS_TOKEN)

    def notify_subscribers(self, raid: Dict[str, Any]):
        """
        當有新團體戰回報時，通知相關訂閱者
        """
        boss_name = raid.get("boss_name", "")
        gym_name = raid.get("gym_name", "")
        duration = raid.get("duration_minutes", 0)

        subscribers = subscription_service.get_subscribers_for_raid(boss_name, gym_name)
        
        if not subscribers:
            return

        message_text = (
            f"🔔 【訂閱通知】有新的團體戰符合您的關鍵字！\n\n"
            f"👾 頭目：{boss_name}\n"
            f"🏛 道館：{gym_name}\n"
            f"⏰ 倒數：約 {duration} 分鐘\n\n"
            f"請盡速前往或開啟雷達查看周遭狀況！"
        )

        with ApiClient(self.line_config) as api_client:
            line_bot_api = MessagingApi(api_client)
            for user_id in subscribers:
                try:
                    line_bot_api.push_message(
                        PushMessageRequest(
                            to=user_id,
                            messages=[TextMessage(text=message_text)]
                        )
                    )
                    logger.info(f"成功推播訂閱通知給 {user_id}")
                except Exception as e:
                    logger.error(f"推播通知失敗 {user_id}: {e}")

notification_service = NotificationService()
