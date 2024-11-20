import os
import google.generativeai as genai
import logging
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled
import json
import re

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TextProcessor:
    def __init__(self):
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("Gemini API key is not set in environment variables")
        
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-1.0-pro')
        self._cache = {}

    def _create_summary_prompt(self, text):
        prompt = f"""
以下のテキストを分析し、文脈を考慮した要約を生成してください。以下のJSON形式で出力してください：

{{
    "主要ポイント": [
        {{
            "タイトル": "簡潔なトピック",
            "説明": "30文字以内の説明",
            "重要度": 1-5の数値
        }}
    ],
    "詳細分析": [
        {{
            "セクション": "セクション名",
            "キーポイント": ["重要ポイント（各15文字以内）"]
        }}
    ],
    "キーワード": [
        {{
            "用語": "キーワード",
            "説明": "20文字以内の説明"
        }}
    ],
    "文脈連携": {{
        "継続するトピック": ["トピック名"],
        "新規トピック": ["新トピック名"]
    }}
}}

分析対象テキスト:
{text}
"""
        return prompt

    def get_transcript(self, video_url):
        """Get transcript from YouTube video"""
        try:
            video_id = self._extract_video_id(video_url)
            
            # Check cache first
            cache_key = f"transcript_{video_id}"
            if cache_key in self._cache:
                return self._cache[cache_key]
            
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            transcript = transcript_list.find_transcript(['ja', 'en'])
            transcript_pieces = transcript.fetch()
            
            full_transcript = ' '.join([piece['text'] for piece in transcript_pieces])
            
            # Cache the result
            self._cache[cache_key] = full_transcript
            return full_transcript
            
        except (NoTranscriptFound, TranscriptsDisabled) as e:
            logger.error(f"字幕の取得に失敗しました: {str(e)}")
            raise Exception("この動画では字幕を利用できません")
        except Exception as e:
            logger.error(f"字幕の取得中にエラーが発生しました: {str(e)}")
            raise Exception(f"字幕の取得に失敗しました: {str(e)}")

    def _extract_video_id(self, url):
        """Extract video ID from YouTube URL"""
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

    def generate_summary(self, text):
        """Generate context-aware summary using Gemini"""
        try:
            # Check cache first
            cache_key = hash(text)
            if cache_key in self._cache:
                return self._cache[cache_key]

            prompt = self._create_summary_prompt(text)
            response = self.model.generate_content(prompt)
            
            if not response.text:
                raise Exception("要約の生成に失敗しました")

            # Extract JSON from response
            json_str = response.text
            if json_str.startswith('```json'):
                json_str = json_str[7:]
            if json_str.endswith('```'):
                json_str = json_str[:-3]

            # Parse JSON and validate structure
            summary_data = json.loads(json_str)
            
            # Format the summary in a readable way
            formatted_summary = self._format_summary(summary_data)
            
            # Cache the result
            self._cache[cache_key] = formatted_summary
            return formatted_summary
            
        except Exception as e:
            logger.error(f"要約の生成中にエラーが発生しました: {str(e)}")
            raise Exception(f"要約の生成に失敗しました: {str(e)}")

    def _format_summary(self, data):
        """Format the summary data into a readable markdown string"""
        try:
            sections = []
            
            # Main points section
            if "主要ポイント" in data:
                sections.append("## 📌 主要ポイント\n")
                for point in data["主要ポイント"]:
                    importance = "🔥" * point.get("重要度", 1)
                    sections.append(f"### {point['タイトル']} {importance}\n")
                    sections.append(f"{point['説明']}\n")

            # Detailed analysis section
            if "詳細分析" in data:
                sections.append("\n## 📊 詳細分析\n")
                for analysis in data["詳細分析"]:
                    sections.append(f"### {analysis['セクション']}\n")
                    for point in analysis['キーポイント']:
                        sections.append(f"- {point}\n")

            # Keywords section
            if "キーワード" in data:
                sections.append("\n## 🔍 重要キーワード\n")
                for keyword in data["キーワード"]:
                    sections.append(f"**{keyword['用語']}**: {keyword['説明']}\n")

            # Context connection section
            if "文脈連携" in data:
                sections.append("\n## 🔄 文脈の連携\n")
                
                if data["文脈連携"]["継続するトピック"]:
                    sections.append("### 継続するトピック\n")
                    for topic in data["文脈連携"]["継続するトピック"]:
                        sections.append(f"- {topic}\n")
                
                if data["文脈連携"]["新規トピック"]:
                    sections.append("\n### 新規トピック\n")
                    for topic in data["文脈連携"]["新規トピック"]:
                        sections.append(f"- {topic}\n")

            return "\n".join(sections)
            
        except Exception as e:
            logger.error(f"要約のフォーマット中にエラーが発生しました: {str(e)}")
            return "要約のフォーマットに失敗しました"
