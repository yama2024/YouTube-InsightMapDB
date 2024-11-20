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
テキストを分析し、以下の形式で要約してください。
重要なポイントを明確に示し、簡潔にまとめてください。

{{
    "動画の概要": "【200文字以内の簡潔な概要】",
    "ポイント": [
        {{
            "番号": 1,
            "タイトル": "【15文字以内の明確なタイトル】",
            "内容": "【40文字以内の具体的な説明】",
            "重要度": 5
        }},
        {{
            "番号": 2,
            "タイトル": "【15文字以内の明確なタイトル】",
            "内容": "【40文字以内の具体的な説明】",
            "重要度": 4
        }},
        {{
            "番号": 3,
            "タイトル": "【15文字以内の明確なタイトル】",
            "内容": "【40文字以内の具体的な説明】",
            "重要度": 3
        }}
    ],
    "結論": "【100文字以内の明確な結論】",
    "キーワード": [
        {{
            "用語": "【キーワード】",
            "説明": "【20文字以内の簡潔な説明】"
        }}
    ]
}}

注意事項:
1. 概要は要点を押さえて簡潔に
2. ポイントは重要度順に配置
3. キーワードは最大10個まで
4. 説明は具体的かつ簡潔に

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

            # 構造の完全性の評価（配点: 10点満点）
            structure_score = 0
            required_keys = ["動画の概要", "ポイント", "結論", "キーワード"]
            for key in required_keys:
                if key in summary_data:
                    structure_score += 2

            points = summary_data.get("ポイント", [])
            if len(points) == 3:  # 正確に3つのポイントがある
                structure_score += 1

            # ポイントの構造チェック
            point_structure_score = 0
            for point in points:
                if all(key in point for key in ["番号", "タイトル", "内容", "重要度"]):
                    point_structure_score += 1
            structure_score += point_structure_score / len(points) if points else 0

            scores["構造の完全性"] = min(structure_score, 10.0)

            # 情報量の評価（配点: 10点満点）
            info_score = 0
            # 概要の情報量
            overview_length = len(summary_data.get("動画の概要", ""))
            if 100 <= overview_length <= 200:
                info_score += 3
            elif 50 <= overview_length < 100:
                info_score += 2

            # ポイントの情報量チェック
            for point in points:
                title_len = len(point.get("タイトル", ""))
                content_len = len(point.get("内容", ""))
                if 5 <= title_len <= 15:
                    info_score += 0.5
                if 20 <= content_len <= 40:
                    info_score += 0.5

            # キーワードの評価
            keywords = summary_data.get("キーワード", [])
            if 3 <= len(keywords) <= 10:
                info_score += 2
            elif 1 <= len(keywords) < 3:
                info_score += 1

            # 結論の情報量
            conclusion_length = len(summary_data.get("結論", ""))
            if 50 <= conclusion_length <= 100:
                info_score += 2
            elif 20 <= conclusion_length < 50:
                info_score += 1

            scores["情報量"] = min(info_score, 10.0)

            # 簡潔性の評価（配点: 10点満点）
            concise_score = 10.0
            
            # 文字数制限オーバーのチェック
            if overview_length > 200:
                concise_score -= 2
            if conclusion_length > 100:
                concise_score -= 2

            # ポイントの簡潔性チェック
            for point in points:
                if len(point.get("タイトル", "")) > 15:
                    concise_score -= 1
                if len(point.get("内容", "")) > 40:
                    concise_score -= 1

            # キーワードの簡潔性
            for keyword in keywords:
                if len(keyword.get("説明", "")) > 20:
                    concise_score -= 0.5

            scores["簡潔性"] = max(concise_score, 0.0)

            # 総合スコアの計算（重み付け平均）
            scores["総合スコア"] = (
                scores["構造の完全性"] * 0.4 +
                scores["情報量"] * 0.3 +
                scores["簡潔性"] * 0.3
            )

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
