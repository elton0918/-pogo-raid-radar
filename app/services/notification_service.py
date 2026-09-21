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

    def send_daily_digest(self, user_ids: Any = None) -> Dict[str, Any]:
        """
        發送每日 08:00 晨報給所有訂閱者 (LINE Push Message)
        """
        from app.services.today_raids_service import today_raids_service
        from app.services.events_service import events_service
        from app.services.flex_builder import (
            create_daily_digest_flex,
            format_daily_digest_text
        )
        from linebot.v3.messaging import FlexContainer, FlexMessage

        subscribers = user_ids if user_ids is not None else subscription_service.get_digest_subscribers()
        if not subscribers:
            logger.info("目前無任何晨報訂閱者，略過發送")
            return {
                "status": "skipped",
                "message": "無訂閱者",
                "sent_count": 0,
                "failed_count": 0
            }

        today_raids = today_raids_service.get_today_raids()
        events = events_service.get_events()

        flex_dict = create_daily_digest_flex(today_raids, events)
        fallback_text = format_daily_digest_text(today_raids, events)

        success_users = []
        failed_users = []

        with ApiClient(self.line_config) as api_client:
            line_bot_api = MessagingApi(api_client)

            try:
                msg = FlexMessage(
                    alt_text="🌅 【Pokémon GO 每日晨報】今日頭目與活動速報",
                    contents=FlexContainer.from_dict(flex_dict)
                )
            except Exception as e:
                logger.warning(f"晨報 Flex 結構解析異常，使用純文字備援: {e}")
                msg = TextMessage(text=fallback_text)

            for uid in subscribers:
                try:
                    line_bot_api.push_message(
                        PushMessageRequest(
                            to=uid,
                            messages=[msg]
                        )
                    )
                    success_users.append(uid)
                    logger.info(f"✅ 成功推播每日晨報給 {uid}")
                except Exception as e:
                    logger.error(f"❌ 推播每日晨報給 {uid} 失敗: {e}")
                    failed_users.append({"user_id": uid, "error": str(e)})

        return {
            "status": "completed",
            "sent_count": len(success_users),
            "failed_count": len(failed_users),
            "successful_subscribers": success_users,
            "failed_subscribers": failed_users
        }

notification_service = NotificationService()
