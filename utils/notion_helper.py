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

    def _split_text(self, text, max_length=2000):
        """テキストを指定された最大長で分割する"""
        if not text:
            return []
        chunks = []
        current_chunk = ""
        
        # 文単位で分割（。で区切る）
        sentences = text.split("。")
        
        for sentence in sentences:
            if len(current_chunk) + len(sentence) < max_length:
                current_chunk += sentence + "。"
            else:
                chunks.append(current_chunk)
                current_chunk = sentence + "。"
        
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks

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
            logger.warning(f"視聴回数の変換に失敗しました: {view_count_str}")
            return 0

    def _validate_content(self, content_dict):
        """コンテンツの存在チェックとバリデーション"""
        required_fields = {
            'video_info': ['title', 'channel_title', 'video_url', 'view_count', 'duration'],
            'contents': ['summary']
        }
        
        # 必須フィールドのチェック
        for category, fields in required_fields.items():
            if category not in content_dict:
                raise ValueError(f"必須カテゴリ {category} が見つかりません")
            
            for field in fields:
                if category == 'video_info' and field not in content_dict['video_info']:
                    raise ValueError(f"必須フィールド {field} が video_info に見つかりません")
                elif category == 'contents' and field not in content_dict['contents']:
                    raise ValueError(f"必須フィールド {field} が contents に見つかりません")

    def save_video_analysis(self, video_info, summary, transcript=None, mindmap=None, proofread_text=None):
        """
        動画分析結果をNotionデータベースに保存する
        
        Parameters:
        - video_info (dict): 動画の基本情報
        - summary (str): 動画の要約テキスト
        - transcript (str, optional): 文字起こしテキスト
        - mindmap (str, optional): マインドマップのMermaid形式テキスト
        - proofread_text (str, optional): 校正済みテキスト
        """
        try:
            # コンテンツのバリデーション
            content = {
                'video_info': video_info,
                'contents': {
                    'summary': summary,
                    'transcript': transcript,
                    'mindmap': mindmap,
                    'proofread_text': proofread_text
                }
            }
            self._validate_content(content)
            
            # 視聴回数を数値に変換
            view_count = self._convert_view_count(video_info["view_count"])
            
            # URLをmulti_select用に変換
            url_select = [{
                "name": video_info["video_url"]
            }]
            
            # ページプロパティの設定
            properties = {
                "name": {
                    "title": [
                        {
                            "text": {
                                "content": video_info["title"]
                            }
                        }
                    ]
                },
                "channel": {
                    "rich_text": [
                        {
                            "text": {
                                "content": video_info["channel_title"]
                            }
                        }
                    ]
                },
                "url": {
                    "multi_select": url_select
                },
                "view_count": {
                    "number": view_count
                },
                "duration": {
                    "rich_text": [
                        {
                            "text": {
                                "content": video_info["duration"]
                            }
                        }
                    ]
                },
                "analysis_date": {
                    "date": {
                        "start": datetime.now().isoformat()
                    }
                },
                "status": {
                    "status": {
                        "name": "Complete"
                    }
                }
            }

            # ページ本文の設定
            children = []
            
            # 文字起こしセクション
            if transcript:
                children.extend([
                    {
                        "object": "block",
                        "type": "heading_2",
                        "heading_2": {
                            "rich_text": [{"type": "text", "text": {"content": "文字起こし"}}]
                        }
                    },
                    {
                        "object": "block",
                        "type": "divider",
                        "divider": {}
                    }
                ])
                
                # 文字起こしを分割して追加
                transcript_chunks = self._split_text(transcript)
                for chunk in transcript_chunks:
                    children.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"type": "text", "text": {"content": chunk}}]
                        }
                    })

            # 要約セクション
            try:
                summary_data = json.loads(summary)
                children.extend([
                    {
                        "object": "block",
                        "type": "heading_2",
                        "heading_2": {
                            "rich_text": [{"type": "text", "text": {"content": "要約"}}]
                        }
                    },
                    {
                        "object": "block",
                        "type": "divider",
                        "divider": {}
                    }
                ])
                
                # 概要を分割して追加
                overview_chunks = self._split_text(summary_data.get("動画の概要", ""))
                for chunk in overview_chunks:
                    children.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"type": "text", "text": {"content": chunk}}]
                        }
                    })
                
            except json.JSONDecodeError as e:
                logger.error(f"サマリーJSONの解析に失敗しました: {str(e)}")
                return False, "サマリーデータの形式が正しくありません"

            # マインドマップセクション
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
                        "type": "divider",
                        "divider": {}
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

            # 校正済みテキストセクション
            if proofread_text:
                children.extend([
                    {
                        "object": "block",
                        "type": "heading_2",
                        "heading_2": {
                            "rich_text": [{"type": "text", "text": {"content": "校正済みテキスト"}}]
                        }
                    },
                    {
                        "object": "block",
                        "type": "divider",
                        "divider": {}
                    }
                ])
                
                # 校正済みテキストを分割して追加
                proofread_chunks = self._split_text(proofread_text)
                for chunk in proofread_chunks:
                    children.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"type": "text", "text": {"content": chunk}}]
                        }
                    })

            # Notionページの作成
            try:
                response = self.notion.pages.create(
                    parent={"database_id": self.database_id},
                    properties=properties,
                    children=children
                )
                logger.info(f"Notionに分析結果を保存しました: {video_info['title']}")
                return True, "保存が完了しました"
            except Exception as e:
                error_message = str(e)
                if "is not a property that exists" in error_message:
                    return False, "データベースのプロパティ設定が正しくありません。プロパティ名と型を確認してください。"
                else:
                    return False, f"Notionページの作成に失敗しました: {error_message}"

        except ValueError as ve:
            error_message = str(ve)
            logger.error(f"コンテンツバリデーションエラー: {error_message}")
            return False, f"バリデーションエラー: {error_message}"
        except Exception as e:
            logger.error(f"Notionへの保存中にエラーが発生しました: {str(e)}")
            return False, f"保存に失敗しました: {str(e)}"
