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

    def _create_summary_prompt(self, text: str) -> str:
        return f'''
以下のテキストから重要なポイントを抽出し、JSONフォーマットで出力してください。
要約は元のテキストの30%程度の長さにしてください。

必須ルール:
1. 必ず有効なJSONを出力すること
2. 各説明は簡潔に
3. 重要度は1-5の整数で表現

出力形式:
{{
    "主要ポイント": [
        {{
            "タイトル": "トピックタイトル",
            "説明": "30文字以内の説明",
            "重要度": 3
        }}
    ],
    "詳細分析": [
        {{
            "セクション": "セクション名",
            "キーポイント": ["重要ポイント"]
        }}
    ],
    "キーワード": [
        {{
            "用語": "キーワード",
            "説明": "20文字以内の説明"
        }}
    ]
}}

分析対象テキスト:
{text}
'''

    def _validate_summary_response(self, response_text: str) -> dict:
        try:
            # Clean up response
            json_str = response_text.strip()
            if json_str.startswith('```json'):
                json_str = json_str[7:]
            if json_str.endswith('```'):
                json_str = json_str[:-3]
            
            # Remove any leading/trailing whitespace or special characters
            json_str = re.sub(r'^[^{]*({.*})[^}]*$', r'\1', json_str, flags=re.DOTALL)
            
            # Parse JSON
            data = json.loads(json_str)
            
            # Validate structure
            if not isinstance(data, dict):
                return None
                
            # Validate required fields and types
            if not all(key in data for key in ["主要ポイント", "詳細分析", "キーワード"]):
                return None
                
            if not isinstance(data["主要ポイント"], list) or not data["主要ポイント"]:
                return None
                
            # Validate main points format
            for point in data["主要ポイント"]:
                if not all(key in point for key in ["タイトル", "説明", "重要度"]):
                    return None
                if not isinstance(point["重要度"], int) or not 1 <= point["重要度"] <= 5:
                    return None
                    
            return data
        except Exception as e:
            logger.error(f"Response validation failed: {str(e)}")
            return None

    def generate_summary(self, text: str) -> str:
        try:
            cache_key = hash(text)
            if cache_key in self._cache:
                return self._cache[cache_key]

            chunks = self._split_into_contextual_chunks(text)
            summaries = []
            
            for chunk in chunks:
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        response = self.model.generate_content(
                            self._create_summary_prompt(chunk),
                            generation_config=genai.types.GenerationConfig(
                                temperature=0.3,
                                top_p=0.8,
                                top_k=40,
                                max_output_tokens=8192,
                            )
                        )
                        
                        if not response.text:
                            continue
                            
                        chunk_data = self._validate_summary_response(response.text)
                        if chunk_data:
                            summaries.append(chunk_data)
                            break
                        else:
                            logger.warning(f"Invalid response format in attempt {attempt + 1}")
                    except Exception as e:
                        logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")
                        if attempt == max_retries - 1:
                            logger.error(f"All attempts failed for chunk")
            
            if not summaries:
                raise ValueError("有効な要約が生成されませんでした")
            
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
            "詳細分析": [],
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

        # 詳細分析をマージ
        seen_sections = set()
        for summary in summaries:
            if "詳細分析" in summary:
                for analysis in summary["詳細分析"]:
                    if analysis["セクション"] not in seen_sections:
                        seen_sections.add(analysis["セクション"])
                        merged["詳細分析"].append(analysis)
        
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
        
        # 詳細分析
        if merged_summary["詳細分析"]:
            formatted_lines.append("\n## 詳細分析")
            for analysis in merged_summary["詳細分析"]:
                formatted_lines.append(f"\n### {analysis['セクション']}")
                for point in analysis["キーポイント"]:
                    formatted_lines.append(f"- {point}")
        
        # キーワード
        if merged_summary["キーワード"]:
            formatted_lines.append("\n## 重要キーワード")
            for keyword in merged_summary["キーワード"]:
                formatted_lines.append(
                    f"\n- **{keyword['用語']}**: {keyword['説明']}"
                )
        
        return "\n".join(formatted_lines)
