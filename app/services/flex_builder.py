from typing import List, Dict, Any

def create_raid_carousel_flex(raids: List[Dict[str, Any]], target_pokemon: str = "") -> dict:
    """
    將團體戰搜尋結果轉換為 LINE Flex Message 輪播卡片 (Carousel)
    支援顯示 Campfire 即時來源標籤與倒數資訊
    """
    bubbles = []

    for r in raids[:10]:  # LINE Carousel 上限為 10 張卡片
        source = r.get("source", "mock_database")
        if source == "campfire_live":
            source_tag = "🔥 Campfire 官方即時"
            source_color = "#059669"
        elif source == "community_report":
            source_tag = "👥 社群即時回報"
            source_color = "#2563EB"
        else:
            source_tag = "📍 雷達道館資料庫"
            source_color = "#4B5563"

        bubble = {
            "type": "bubble",
            "size": "kilo",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#1E3A8A",
                "paddingTop": "10px",
                "paddingBottom": "10px",
                "contents": [
                    {
                        "type": "text",
                        "text": f"{'⭐' * r.get('tier', 5)} TIER {r.get('tier', 5)} 傳奇團體戰",
                        "color": "#FBBF24",
                        "weight": "bold",
                        "size": "xs",
                        "align": "center"
                    }
                ]
            },
            "hero": {
                "type": "image",
                "url": r["image_url"],
                "size": "md",
                "aspectRatio": "1:1",
                "aspectMode": "fit",
                "backgroundColor": "#F3F4F6"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "text",
                        "text": r["boss_name"],
                        "weight": "bold",
                        "size": "xl",
                        "color": "#111827",
                        "align": "center"
                    },
                    {
                        "type": "text",
                        "text": f"CP {r['cp']}  •  {' / '.join(r['types'])}",
                        "size": "xs",
                        "color": "#6B7280",
                        "align": "center"
                    },
                    {
                        "type": "separator",
                        "margin": "md"
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "margin": "md",
                        "spacing": "xs",
                        "contents": [
                            {
                                "type": "box",
                                "layout": "baseline",
                                "spacing": "sm",
                                "contents": [
                                    {"type": "text", "text": "🏛 道館", "color": "#9CA3AF", "size": "xs", "flex": 2},
                                    {"type": "text", "text": r["gym_name"], "wrap": True, "color": "#1F2937", "size": "xs", "weight": "bold", "flex": 5}
                                ]
                            },
                            {
                                "type": "box",
                                "layout": "baseline",
                                "spacing": "sm",
                                "contents": [
                                    {"type": "text", "text": "📏 距離", "color": "#9CA3AF", "size": "xs", "flex": 2},
                                    {"type": "text", "text": f"{r['distance_km']} km", "color": "#059669", "size": "xs", "weight": "bold", "flex": 5}
                                ]
                            },
                            {
                                "type": "box",
                                "layout": "baseline",
                                "spacing": "sm",
                                "contents": [
                                    {"type": "text", "text": "⏰ 倒數", "color": "#9CA3AF", "size": "xs", "flex": 2},
                                    {"type": "text", "text": f"剩餘約 {r['remaining_minutes']} 分鐘 ({r['end_time_str']} 止)", "color": "#DC2626", "size": "xs", "weight": "bold", "flex": 5}
                                ]
                            },
                            {
                                "type": "box",
                                "layout": "baseline",
                                "spacing": "sm",
                                "contents": [
                                    {"type": "text", "text": "📡 來源", "color": "#9CA3AF", "size": "xs", "flex": 2},
                                    {"type": "text", "text": source_tag, "color": source_color, "size": "xs", "weight": "bold", "flex": 5}
                                ]
                            }
                        ]
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "color": "#2563EB",
                        "height": "sm",
                        "action": {
                            "type": "uri",
                            "label": "開啟 Google 地圖導航",
                            "uri": r["map_url"]
                        }
                    }
                ]
            }
        }
        bubbles.append(bubble)

    return {
        "type": "carousel",
        "contents": bubbles
    }
