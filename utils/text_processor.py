import json
import re
import logging
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter
import google.generativeai as genai
import os

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TextProcessor:
    def __init__(self):
        self._cache = {}
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("Gemini API key not found in environment variables")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-pro')

    def get_transcript(self, video_url: str) -> str:
        """Get transcript from YouTube video"""
        try:
            video_id = self._extract_video_id(video_url)
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            transcript = transcript_list.find_transcript(['ja', 'en'])
            transcript_data = transcript.fetch()
            formatter = TextFormatter()
            return formatter.format_transcript(transcript_data)
        except Exception as e:
            logger.error(f"Failed to fetch transcript: {str(e)}")
            raise

    def _extract_video_id(self, url: str) -> str:
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
        raise ValueError("Invalid YouTube URL")

    def _create_summary_prompt(self, text: str) -> str:
        return f'''
テキストを分析し、以下の形式で要約してください：

{{
    "動画の概要": "【重要度の高い情報を含む、200文字以内の簡潔な概要】",
    "ポイント": [
        {{
            "タイトル": "【15文字以内の明確なタイトル】",
            "説明": "【40文字以内の具体的な説明】",
            "重要度": 【4か5】  // 最重要ポイント
        }},
        {{
            "タイトル": "【15文字以内の明確なタイトル】",
            "説明": "【40文字以内の具体的な説明】",
            "重要度": 【3】  // 重要なポイント
        }},
        {{
            "タイトル": "【15文字以内の明確なタイトル】",
            "説明": "【40文字以内の具体的な説明】",
            "重要度": 【2】  // 補足的なポイント
        }}
    ],
    "結論": "【100文字以内の明確な結論】"
}}

要約の注意点:
1. 重要度の分布を必ず分けること（5または4を1つ、3を1つ、2を1つ）
2. タイトルは具体的な名詞や要点を含めること
3. 説明は簡潔かつ具体的に
4. 概要と結論で重複を避けること

分析対象テキスト:
{text}
'''

    def _evaluate_summary_quality(self, summary: str) -> dict:
        """Evaluate the quality of the generated summary"""
        try:
            summary_data = json.loads(summary)
            scores = {
                "構造の完全性": 0.0,
                "情報量": 0.0,
                "簡潔性": 0.0,
                "総合スコア": 0.0
            }

            # 構造の完全性の評価
            structure_score = 0
            required_keys = ["動画の概要", "ポイント", "結論"]
            for key in required_keys:
                if key in summary_data:
                    structure_score += 3
            
            points = summary_data.get("ポイント", [])
            if len(points) == 3:  # 正確に3つのポイントがある
                structure_score += 1
                
            # ポイントの構造チェック
            point_structure_score = 0
            for point in points:
                if all(key in point for key in ["タイトル", "説明", "重要度"]):
                    point_structure_score += 1
            structure_score += point_structure_score / len(points) if points else 0
            
            scores["構造の完全性"] = min(structure_score, 10.0)

            # 情報量の評価
            info_score = 0
            overview_length = len(summary_data.get("動画の概要", ""))
            if 100 <= overview_length <= 200:  # 適切な長さの概要
                info_score += 3
            
            # ポイントの情報量チェック
            for point in points:
                title_len = len(point.get("タイトル", ""))
                desc_len = len(point.get("説明", ""))
                if 5 <= title_len <= 15:  # タイトルの長さが適切
                    info_score += 1
                if 20 <= desc_len <= 40:  # 説明の長さが適切
                    info_score += 1
            
            conclusion_length = len(summary_data.get("結論", ""))
            if 50 <= conclusion_length <= 100:  # 適切な長さの結論
                info_score += 2
                
            scores["情報量"] = min(info_score, 10.0)

            # 簡潔性の評価
            concise_score = 10.0  # 開始点を10とし、問題があれば減点
            
            # 文字数制限オーバーのチェック
            if overview_length > 200:
                concise_score -= 2
            if conclusion_length > 100:
                concise_score -= 2
                
            # ポイントの簡潔性チェック
            for point in points:
                if len(point.get("タイトル", "")) > 15:
                    concise_score -= 1
                if len(point.get("説明", "")) > 40:
                    concise_score -= 1
                    
            scores["簡潔性"] = max(concise_score, 0.0)

            # 総合スコアの計算
            scores["総合スコア"] = (scores["構造の完全性"] * 0.4 + 
                               scores["情報量"] * 0.3 + 
                               scores["簡潔性"] * 0.3)

            return scores

        except json.JSONDecodeError:
            logger.error("Summary is not in valid JSON format")
            return {key: 0.0 for key in ["構造の完全性", "情報量", "簡潔性", "総合スコア"]}
        except Exception as e:
            logger.error(f"Error evaluating summary quality: {str(e)}")
            return {key: 0.0 for key in ["構造の完全性", "情報量", "簡潔性", "総合スコア"]}

    def generate_summary(self, text: str) -> tuple:
        """Generate a summary of the given text and evaluate its quality"""
        try:
            # Check cache first
            cache_key = hash(text)
            if cache_key in self._cache:
                return self._cache[cache_key]

            prompt = self._create_summary_prompt(text)
            response = self.model.generate_content(prompt)
            summary = response.text

            # Clean up the response to ensure valid JSON
            summary = summary.strip()
            if summary.startswith('```json'):
                summary = summary[7:]
            if summary.endswith('```'):
                summary = summary[:-3]
            summary = summary.strip()

            # Evaluate the quality of the summary
            quality_scores = self._evaluate_summary_quality(summary)

            # Cache the result
            result = (summary, quality_scores)
            self._cache[cache_key] = result
            return result

        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            raise
