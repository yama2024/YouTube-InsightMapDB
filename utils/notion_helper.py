from notion_client import Client
import os
import json
import logging
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NotionHelper:
    def __init__(self):
        self.notion = Client(auth=os.environ["NOTION_API_KEY"])
        self.database_id = os.environ["NOTION_DATABASE_ID"]

    def _convert_view_count(self, view_count_str):
        """
        視聴回数の文字列を数値に変換する
        例: "3万回視聴" → 30000
        """
        try:
            # "回視聴"を削除
            count = view_count_str.replace('回視聴', '')
            
            # 単位変換マップ
            unit_map = {
                '万': 10000,
                '千': 1000
            }
            
            # 単位があれば変換
            for unit, multiplier in unit_map.items():
                if unit in count:
                    number = float(count.replace(unit, ''))
                    return int(number * multiplier)
            
            # 単位がなければそのまま数値に変換
            return int(count.replace(',', ''))
        except (ValueError, TypeError):
            # 変換できない場合は0を返す
            logger.warning(f"視聴回数の変換に失敗しました: {view_count_str}")
            return 0

    def save_video_analysis(self, video_info, summary, mindmap=None):
        """
        動画分析結果をNotionデータベースに保存する
        
        Parameters:
        - video_info (dict): 動画の基本情報
        - summary (str): 動画の要約テキスト
        - mindmap (str, optional): マインドマップのMermaid形式テキスト
        """
        try:
            # 現在の日時を取得
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 視聴回数を数値に変換
            view_count = self._convert_view_count(video_info["view_count"])
            
            # ページプロパティの設定
            properties = {
                "タイトル": {
                    "title": [
                        {
                            "text": {
                                "content": video_info["title"]
                            }
                        }
                    ]
                },
                "チャンネル": {
                    "rich_text": [
                        {
                            "text": {
                                "content": video_info["channel_title"]
                            }
                        }
                    ]
                },
                "URL": {
                    "url": video_info["video_url"]
                },
                "視聴回数": {
                    "number": view_count
                },
                "動画時間": {
                    "rich_text": [
                        {
                            "text": {
                                "content": video_info["duration"]
                            }
                        }
                    ]
                },
                "分析日時": {
                    "date": {
                        "start": datetime.now().isoformat()
                    }
                },
                "ステータス": {
                    "status": {
                        "name": "完了"
                    }
                }
            }

            try:
                # サマリーJSONの解析
                summary_data = json.loads(summary)
            except json.JSONDecodeError as e:
                logger.error(f"サマリーJSONの解析に失敗しました: {str(e)}")
                return False, "サマリーデータの形式が正しくありません"
            
            # ページ本文の設定
            children = [
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": "動画の概要"}}]
                    }
                },
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": summary_data.get("動画の概要", "")}}]
                    }
                },
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": "主要ポイント"}}]
                    }
                }
            ]

            # マインドマップが存在する場合、追加
            if mindmap:
                children.extend([
                    {
                        "object": "block",
                        "type": "heading_2",
                        "heading_2": {
                            "rich_text": [{"type": "text", "text": {"content": "マインドマップ"}}]
                        }
                    },
                    {
                        "object": "block",
                        "type": "code",
                        "code": {
                            "language": "mermaid",
                            "rich_text": [{"type": "text", "text": {"content": mindmap}}]
                        }
                    }
                ])

            # Notionページの作成
            response = self.notion.pages.create(
                parent={"database_id": self.database_id},
                properties=properties,
                children=children
            )

            logger.info(f"Notionに分析結果を保存しました: {video_info['title']}")
            return True, "保存が完了しました"

        except Exception as e:
            logger.error(f"Notionへの保存中にエラーが発生しました: {str(e)}")
            return False, f"保存に失敗しました: {str(e)}"
