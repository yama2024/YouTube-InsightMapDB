import os
import json
import logging
import requests
from datetime import datetime
from notion_client import Client
from typing import Optional, List, Dict, Any, Tuple

# Set up logging
logger = logging.getLogger(__name__)

class NotionHelper:
    # ステータス定義
    SYNC_STATUS = {
        'SYNCED': '同期済み',
        'SYNCING': '同期中',
        'ERROR': 'エラー'
    }

    # ステータスアイコン定義
    STATUS_ICONS = {
        'SYNCED': '🟢',
        'SYNCING': '🔄',
        'ERROR': '⚠️'
    }

    def __init__(self):
        self.notion = Client(auth=os.environ["NOTION_API_KEY"])
        self.database_id = os.environ["NOTION_DATABASE_ID"]

    def _split_text(self, text, max_length=1900):
        """テキストを指定された最大長で分割する（文章の区切りを考慮）"""
        if not text:
            return []
        
        chunks = []
        current_chunk = ""
        current_length = 0
        
        # 段落で分割（改行で区切る）
        paragraphs = text.split("\n")
        
        for paragraph in paragraphs:
            # 段落内の文を分割
            sentences = paragraph.split("。")
            
            for sentence in sentences:
                # 文末の句点を追加
                sentence = sentence + "。" if sentence else ""
                sentence_length = len(sentence)
                
                # 1つの文が最大長を超える場合は、強制的に分割
                if sentence_length > max_length:
                    if current_chunk:
                        chunks.append(current_chunk)
                        current_chunk = ""
                        current_length = 0
                    
                    # 長い文を適切な長さで分割
                    for i in range(0, len(sentence), max_length):
                        chunk = sentence[i:i + max_length]
                        chunks.append(chunk)
                    continue
                
                # 現在のチャンクに文を追加できるかチェック
                if current_length + sentence_length <= max_length:
                    current_chunk += sentence
                    current_length += sentence_length
                else:
                    # 現在のチャンクを保存し、新しいチャンクを開始
                    chunks.append(current_chunk)
                    current_chunk = sentence
                    current_length = sentence_length
            
            # 段落の終わりに改行を追加（最後の段落以外）
            if current_chunk and paragraph != paragraphs[-1]:
                current_chunk += "\n"
                current_length += 1
        
        # 最後のチャンクを追加
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks

    def _convert_view_count(self, view_count_str):
        """
        視聴回数の文字列を数値に変換する
        例: "3万回視聴" → 30000
        """
        if not view_count_str:
            logger.warning("視聴回数が空です")
            return 0

        try:
            # "回視聴"を削除
            count = view_count_str.replace('回視聴', '').strip()
            
            # 単位変換マップ
            unit_map = {
                '万': 10000,
                '千': 1000
            }
            
            # カンマを削除
            count = count.replace(',', '')
            
            # 単位があれば変換
            for unit, multiplier in unit_map.items():
                if unit in count:
                    try:
                        number = float(count.replace(unit, ''))
                        return int(number * multiplier)
                    except ValueError as e:
                        logger.error(f"数値変換エラー ({count}): {str(e)}")
                        return 0
            
            # 単位がなければそのまま数値に変換
            try:
                return int(count)
            except ValueError as e:
                logger.error(f"数値変換エラー ({count}): {str(e)}")
                return 0
                
        except Exception as e:
            logger.error(f"視聴回数の変換に失敗しました ({view_count_str}): {str(e)}")
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

    def _download_thumbnail(self, thumbnail_url: str) -> Optional[bytes]:
        """
        サムネイル画像をダウンロードする

        Args:
            thumbnail_url (str): サムネイル画像のURL

        Returns:
            Optional[bytes]: ダウンロードした画像データ。失敗した場合はNone
        """
        if not thumbnail_url:
            logger.warning("サムネイルURLが指定されていません")
            return None

        try:
            # タイムアウトを設定してリクエスト
            response = requests.get(thumbnail_url, timeout=10, 
                                 headers={'User-Agent': 'Mozilla/5.0'})
            
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '')
                if not content_type.startswith('image/'):
                    logger.error(f"不正なコンテンツタイプです: {content_type}")
                    return None
                    
                if len(response.content) > 5 * 1024 * 1024:  # 5MB制限
                    logger.error("画像サイズが大きすぎます")
                    return None
                    
                logger.info("サムネイル画像のダウンロードに成功しました")
                return response.content
            else:
                logger.error(f"サムネイル画像のダウンロードに失敗しました: HTTP {response.status_code}")
                return None
                
        except requests.Timeout:
            logger.error("サムネイル画像のダウンロードがタイムアウトしました")
            return None
        except requests.RequestException as e:
            logger.error(f"サムネイル画像のダウンロード中にネットワークエラーが発生しました: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"サムネイル画像のダウンロード中に予期せぬエラーが発生しました: {str(e)}")
            return None

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
                    "url": video_info["video_url"]
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
            
            # サムネイル画像セクション
            if "thumbnail_url" in video_info and video_info["thumbnail_url"]:
                thumbnail_data = self._download_thumbnail(video_info["thumbnail_url"])
                if thumbnail_data:
                    children.extend([
                        {
                            "object": "block",
                            "type": "image",
                            "image": {
                                "type": "external",
                                "external": {
                                    "url": video_info["thumbnail_url"]
                                }
                            }
                        },
                        {
                            "object": "block",
                            "type": "divider",
                            "divider": {}
                        }
                    ])
                    logger.info("サムネイル画像をNotionページに追加しました")
            
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

    def get_video_pages(self, search_query=None, sort_by="analysis_date", ascending=False):
        """
        保存された動画ページの一覧を取得する

        Parameters:
        - search_query (str, optional): 検索クエリ
        - sort_by (str): ソートするプロパティ名
        - ascending (bool): 昇順にするかどうか

        Returns:
        - list: ページ情報のリスト
        """
        try:
            # フィルター設定
            filter_params = {
                "database_id": self.database_id,
                "sorts": [{
                    "property": sort_by,
                    "direction": "ascending" if ascending else "descending"
                }]
            }

            # 検索クエリがある場合
            if search_query:
                filter_params["filter"] = {
                    "or": [
                        {
                            "property": "name",
                            "title": {
                                "contains": search_query
                            }
                        },
                        {
                            "property": "channel",
                            "rich_text": {
                                "contains": search_query
                            }
                        }
                    ]
                }

            # データの取得
            response = self.notion.databases.query(**filter_params)
            
            # 結果の整形
            pages = []
            for page in response.get("results", []):
                properties = page.get("properties", {})
                
                # 基本情報の取得
                title = properties.get("name", {}).get("title", [{}])[0].get("text", {}).get("content", "No Title")
                channel = properties.get("channel", {}).get("rich_text", [{}])[0].get("text", {}).get("content", "No Channel")
                url = properties.get("url", {}).get("url", "")
                view_count = properties.get("view_count", {}).get("number", 0)
                duration = properties.get("duration", {}).get("rich_text", [{}])[0].get("text", {}).get("content", "")
                analysis_date = properties.get("analysis_date", {}).get("date", {}).get("start", "")
                status = properties.get("status", {}).get("status", {}).get("name", "Unknown")
                
                # 同期ステータスの判定
                sync_status = 'SYNCED'
                if status.lower() == 'error':
                    sync_status = 'ERROR'
                elif status.lower() == 'syncing':
                    sync_status = 'SYNCING'
                
                pages.append({
                    "id": page.get("id"),
                    "title": title,
                    "channel": channel,
                    "url": url,
                    "view_count": view_count,
                    "duration": duration,
                    "analysis_date": analysis_date,
                    "status": self.SYNC_STATUS[sync_status],
                    "sync_status": sync_status,
                    "status_icon": self.STATUS_ICONS[sync_status]
                })
            
            return True, pages

        except Exception as e:
            logger.error(f"動画ページの取得中にエラーが発生しました: {str(e)}")
            return False, f"データの取得に失敗しました: {str(e)}"

    def update_video_page(self, page_id, video_info=None, summary=None, transcript=None, mindmap=None, proofread_text=None):
        """
        既存の動画ページを更新する

        Parameters:
        - page_id (str): 更新するページのID
        - video_info (dict): 動画情報
        - summary (str): 要約テキスト
        - transcript (str): 文字起こし
        - mindmap (str): マインドマップ
        - proofread_text (str): 校正済みテキスト

        Returns:
        - tuple: (成功したかどうか, メッセージ)
        """
        try:
            # 更新するプロパティの準備
            properties = {}
            
            if video_info:
                properties.update({
                    "name": {"title": [{"text": {"content": video_info['title']}}]},
                    "channel": {"rich_text": [{"text": {"content": video_info['channel_title']}}]},
                    "url": {"url": video_info['url']},
                    "view_count": {"number": video_info['view_count']},
                    "duration": {"rich_text": [{"text": {"content": video_info['duration']}}]},
                    "status": {"status": {"name": "Updated"}},
                    "last_updated": {"date": {"start": datetime.now().isoformat()}}
                })

            # ページの更新
            response = self.notion.pages.update(
                page_id=page_id,
                properties=properties
            )

            # コンテンツブロックの更新
            if any([summary, transcript, mindmap, proofread_text]):
                blocks = []
                
                if summary:
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"type": "text", "text": {"content": "要約:\n" + summary}}]
                        }
                    })
                
                if transcript:
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"type": "text", "text": {"content": "文字起こし:\n" + transcript}}]
                        }
                    })
                
                if mindmap:
                    blocks.append({
                        "object": "block",
                        "type": "code",
                        "code": {
                            "language": "mermaid",
                            "rich_text": [{"type": "text", "text": {"content": mindmap}}]
                        }
                    })
                
                if proofread_text:
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"type": "text", "text": {"content": "校正済みテキスト:\n" + proofread_text}}]
                        }
                    })

                # 既存のブロックを削除
                existing_blocks = self.notion.blocks.children.list(block_id=page_id)
                for block in existing_blocks.get("results", []):
                    self.notion.blocks.delete(block_id=block["id"])

                # 新しいブロックを追加
                self.notion.blocks.children.append(
                    block_id=page_id,
                    children=blocks
                )

            return True, "ページを更新しました"

        except Exception as e:
            logger.error(f"ページの更新中にエラーが発生しました: {str(e)}")
            return False, f"更新に失敗しました: {str(e)}"

    def sync_pages(self, local_data=None):
        """
        NotionデータベースとローカルデータとのSync処理を行う

        Parameters:
        - local_data (dict): ローカルのデータ（オプション）

        Returns:
        - tuple: (成功したかどうか, 同期結果のメッセージ)
        """
        try:
            # Notionからデータを取得
            success, pages = self.get_video_pages()
            if not success:
                return False, "Notionからのデータ取得に失敗しました"

            sync_results = {
                "updated": 0,
                "failed": 0,
                "skipped": 0
            }

            # ローカルデータがある場合は同期処理を実行
            if local_data:
                for page in pages:
                    page_id = page["id"]
                    local_video = local_data.get(page_id)
                    
                    if not local_video:
                        sync_results["skipped"] += 1
                        continue

                    # 更新が必要かチェック
                    needs_update = (
                        local_video.get("status") != page.get("status") or
                        local_video.get("view_count") != page.get("view_count")
                    )

                    if needs_update:
                        success, _ = self.update_video_page(
                            page_id=page_id,
                            video_info=local_video
                        )
                        if success:
                            sync_results["updated"] += 1
                        else:
                            sync_results["failed"] += 1
                    else:
                        sync_results["skipped"] += 1

            return True, f"""同期完了:
            - 更新: {sync_results['updated']}件
            - 失敗: {sync_results['failed']}件
            - スキップ: {sync_results['skipped']}件"""

        except Exception as e:
            logger.error(f"同期処理中にエラーが発生しました: {str(e)}")
            return False, f"同期に失敗しました: {str(e)}"
