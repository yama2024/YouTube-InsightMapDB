import os
import json
import logging
from typing import Dict, List
import google.generativeai as genai
import re
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TextProcessor:
    def __init__(self):
        self._cache = {}
        # Initialize Gemini
        genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
        self.model = genai.GenerativeModel('gemini-pro')

    def get_transcript(self, video_url: str) -> str:
        """動画の文字起こしを取得"""
        try:
            video_id = self._extract_video_id(video_url)
            
            # Check cache first
            cache_key = f"transcript_{video_id}"
            if cache_key in self._cache:
                return self._cache[cache_key]
            
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            transcript = transcript_list.find_transcript(['ja', 'en'])
            transcript_data = transcript.fetch()
            
            formatter = TextFormatter()
            formatted_transcript = formatter.format_transcript(transcript_data)
            
            # Cache the result
            self._cache[cache_key] = formatted_transcript
            return formatted_transcript
            
        except Exception as e:
            logger.error(f"文字起こしの取得中にエラーが発生しました: {str(e)}")
            raise Exception(f"文字起こしの取得に失敗しました: {str(e)}")

    def _extract_video_id(self, url: str) -> str:
        """YouTube URLからビデオIDを抽出"""
        patterns = [
            r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
            r'(?:embed\/)([0-9A-Za-z_-]{11})',
            r'(?:watch\?v=)([0-9A-Za-z_-]{11})'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        raise ValueError("無効なYouTube URLです")

    def _split_into_contextual_chunks(self, text: str, chunk_size: int = 1000) -> List[str]:
        """テキストをコンテキストを考慮したチャンクに分割"""
        # 文単位で分割
        sentences = re.split('([。!?！？]+)', text)
        sentences = [''.join(i) for i in zip(sentences[0::2], sentences[1::2])]
        
        chunks = []
        current_chunk = []
        current_length = 0
        
        for sentence in sentences:
            if current_length + len(sentence) > chunk_size and current_chunk:
                chunks.append(''.join(current_chunk))
                current_chunk = []
                current_length = 0
            current_chunk.append(sentence)
            current_length += len(sentence)
            
        if current_chunk:
            chunks.append(''.join(current_chunk))
            
        return chunks

    def generate_summary(self, text: str) -> str:
        """コンテキストを考慮したAI要約を生成"""
        try:
            cache_key = hash(text)
            if cache_key in self._cache:
                return self._cache[cache_key]

            chunks = self._split_into_contextual_chunks(text)
            summaries = []
            
            for chunk in chunks:
                prompt = f'''
以下のテキストを分析し、重要度に応じて要約してください。
JSONフォーマットで出力してください。

テキストの分析ポイント:
1. 主要なトピックと重要度（1-5、5が最も重要）を抽出
2. トピック間の関連性を考慮
3. キーとなる概念や用語を特定

出力形式:
{{
    "主要ポイント": [
        {{
            "タイトル": "トピックタイトル",
            "説明": "トピックの詳細説明（30文字以内）",
            "重要度": 重要度スコア(1-5)
        }}
    ],
    "関連性": [
        {{
            "トピックA": "トピックタイトル",
            "トピックB": "関連するトピックタイトル",
            "関連度": 関連度スコア(1-5)
        }}
    ],
    "キーワード": [
        {{
            "用語": "キーワード",
            "説明": "用語の説明（20文字以内）"
        }}
    ]
}}

分析対象テキスト:
{chunk}
'''
                try:
                    response = self.model.generate_content(prompt)
                    json_str = response.text.strip()
                    
                    # Clean JSON string if needed
                    if json_str.startswith('```json'):
                        json_str = json_str[7:]
                    if json_str.endswith('```'):
                        json_str = json_str[:-3]
                    
                    chunk_data = json.loads(json_str)
                    summaries.append(chunk_data)
                except Exception as e:
                    logger.warning(f"チャンク解析エラー: {str(e)}")
                    continue

            if not summaries:
                raise ValueError("有効な要約が生成されませんでした")

            # マージして最終的な要約を生成
            merged_summary = self._merge_summaries(summaries)
            formatted_summary = self._format_summary(merged_summary)
            
            self._cache[cache_key] = formatted_summary
            return formatted_summary

        except Exception as e:
            logger.error(f"要約の生成中にエラーが発生しました: {str(e)}")
            raise Exception(f"要約の生成に失敗しました: {str(e)}")

    def _merge_summaries(self, summaries: List[Dict]) -> Dict:
        """複数のチャンク要約をマージ"""
        merged = {
            "主要ポイント": [],
            "関連性": [],
            "キーワード": []
        }
        
        # 重要度でソート
        all_points = []
        for summary in summaries:
            if "主要ポイント" in summary:
                all_points.extend(summary["主要ポイント"])
        
        sorted_points = sorted(
            all_points,
            key=lambda x: x.get("重要度", 0),
            reverse=True
        )
        
        # 重複を除去して上位を選択
        seen_titles = set()
        for point in sorted_points:
            title = point["タイトル"]
            if title not in seen_titles:
                seen_titles.add(title)
                merged["主要ポイント"].append(point)
        
        # キーワードをマージ
        seen_keywords = set()
        for summary in summaries:
            if "キーワード" in summary:
                for keyword in summary["キーワード"]:
                    if keyword["用語"] not in seen_keywords:
                        seen_keywords.add(keyword["用語"])
                        merged["キーワード"].append(keyword)
        
        return merged

    def _format_summary(self, merged_summary: Dict) -> str:
        """要約を読みやすい形式にフォーマット"""
        formatted_lines = ["# コンテンツ要約\n"]
        
        # 主要ポイント
        formatted_lines.append("## 主要ポイント")
        for point in merged_summary["主要ポイント"]:
            importance = "🔥" * point.get("重要度", 1)
            formatted_lines.append(
                f"\n### {point['タイトル']} {importance}\n"
                f"{point['説明']}"
            )
        
        # キーワード
        if merged_summary["キーワード"]:
            formatted_lines.append("\n## 重要キーワード")
            for keyword in merged_summary["キーワード"]:
                formatted_lines.append(
                    f"\n- **{keyword['用語']}**: {keyword['説明']}"
                )
        
        return "\n".join(formatted_lines)
