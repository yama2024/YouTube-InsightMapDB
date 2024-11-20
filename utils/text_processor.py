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

    def _create_summary_prompt(self, text: str, style: str = "balanced") -> str:
        """Create a summary prompt based on the selected style"""
        base_prompt = f"""
テキストを分析し、以下の形式で要約してください。
重要なポイントを明確に示し、"""

        if style == "detailed":
            base_prompt += "詳細な説明を含めて要約してください。\n\n"
            json_template = {
                "動画の概要": "【400文字程度の詳細な概要】",
                "ポイント": [
                    {
                        "番号": 1,
                        "タイトル": "【20文字以内の明確なタイトル】",
                        "内容": "【80文字程度の詳細な説明】",
                        "重要度": 5,
                        "補足情報": "【40文字程度の追加コンテキスト】"
                    }
                ] * 5,
                "結論": "【200文字程度の詳細な結論】",
                "キーワード": [
                    {
                        "用語": "【キーワード】",
                        "説明": "【40文字程度の詳細な説明】",
                        "関連用語": ["関連キーワード1", "関連キーワード2"]
                    }
                ] * 5
            }
        elif style == "overview":
            base_prompt += "簡潔にポイントを絞って要約してください。\n\n"
            json_template = {
                "動画の概要": "【100文字以内の簡潔な概要】",
                "ポイント": [
                    {
                        "番号": 1,
                        "タイトル": "【15文字以内の明確なタイトル】",
                        "内容": "【30文字以内の簡潔な説明】",
                        "重要度": 5
                    }
                ] * 3,
                "結論": "【50文字以内の明確な結論】",
                "キーワード": [
                    {
                        "用語": "【キーワード】",
                        "説明": "【20文字以内の簡潔な説明】"
                    }
                ] * 3
            }
        else:  # balanced (default)
            base_prompt += "バランスの取れた形で要約してください。\n\n"
            json_template = {
                "動画の概要": "【200文字以内の簡潔な概要】",
                "ポイント": [
                    {
                        "番号": 1,
                        "タイトル": "【15文字以内の明確なタイトル】",
                        "内容": "【40文字以内の具体的な説明】",
                        "重要度": 5
                    }
                ] * 3,
                "結論": "【100文字以内の明確な結論】",
                "キーワード": [
                    {
                        "用語": "【キーワード】",
                        "説明": "【20文字以内の簡潔な説明】"
                    }
                ]
            }

        return base_prompt + json.dumps(json_template, ensure_ascii=False, indent=2) + f"\n\n分析対象テキスト:\n{text}"

    def _evaluate_summary_quality(self, summary: str, style: str = "balanced") -> dict:
        """Evaluate the quality of the generated summary based on the style"""
        try:
            summary_data = json.loads(summary)
            scores = {
                "構造の完全性": 0.0,
                "情報量": 0.0,
                "簡潔性": 0.0,
                "総合スコア": 0.0
            }

            # Style-specific evaluation criteria
            if style == "detailed":
                # Detailed style expects more comprehensive content
                overview_length_range = (300, 400)
                content_length_range = (60, 80)
                conclusion_length_range = (150, 200)
                min_keywords = 8
            elif style == "overview":
                # Overview style expects concise content
                overview_length_range = (50, 100)
                content_length_range = (20, 30)
                conclusion_length_range = (30, 50)
                min_keywords = 3
            else:  # balanced
                # Balanced style has moderate expectations
                overview_length_range = (150, 200)
                content_length_range = (30, 40)
                conclusion_length_range = (70, 100)
                min_keywords = 5

            # Evaluate structure completeness (10 points)
            structure_score = 0
            required_keys = ["動画の概要", "ポイント", "結論", "キーワード"]
            for key in required_keys:
                if key in summary_data:
                    structure_score += 2.5

            points = summary_data.get("ポイント", [])
            if points:
                point_structure_score = 0
                required_point_keys = ["番号", "タイトル", "内容", "重要度"]
                if style == "detailed":
                    required_point_keys.append("補足情報")
                
                for point in points:
                    if all(key in point for key in required_point_keys):
                        point_structure_score += 1
                structure_score += min(point_structure_score / len(points), 2.5)

            scores["構造の完全性"] = min(structure_score, 10.0)

            # Evaluate information content (10 points)
            info_score = 0
            overview_length = len(summary_data.get("動画の概要", ""))
            if overview_length_range[0] <= overview_length <= overview_length_range[1]:
                info_score += 3
            elif overview_length >= overview_length_range[0] * 0.7:
                info_score += 2

            # Points evaluation
            for point in points:
                content_len = len(point.get("内容", ""))
                if content_length_range[0] <= content_len <= content_length_range[1]:
                    info_score += 0.5

            # Keywords evaluation
            keywords = summary_data.get("キーワード", [])
            if len(keywords) >= min_keywords:
                info_score += 2
            elif len(keywords) >= min_keywords * 0.7:
                info_score += 1

            # Conclusion evaluation
            conclusion_length = len(summary_data.get("結論", ""))
            if conclusion_length_range[0] <= conclusion_length <= conclusion_length_range[1]:
                info_score += 2
            elif conclusion_length >= conclusion_length_range[0] * 0.7:
                info_score += 1

            scores["情報量"] = min(info_score, 10.0)

            # Evaluate conciseness (10 points)
            concise_score = 10.0
            
            # Penalize based on style-specific criteria
            if overview_length > overview_length_range[1]:
                concise_score -= (overview_length - overview_length_range[1]) / 100

            for point in points:
                content_len = len(point.get("内容", ""))
                if content_len > content_length_range[1]:
                    concise_score -= 0.5

            if conclusion_length > conclusion_length_range[1]:
                concise_score -= (conclusion_length - conclusion_length_range[1]) / 50

            scores["簡潔性"] = max(concise_score, 0.0)

            # Calculate overall score with style-specific weights
            if style == "detailed":
                weights = {"構造の完全性": 0.3, "情報量": 0.5, "簡潔性": 0.2}
            elif style == "overview":
                weights = {"構造の完全性": 0.3, "情報量": 0.2, "簡潔性": 0.5}
            else:  # balanced
                weights = {"構造の完全性": 0.4, "情報量": 0.3, "簡潔性": 0.3}

            scores["総合スコア"] = round(
                sum(scores[key] * weights[key] for key in weights), 1
            )

            # Round all scores to one decimal place
            return {key: round(value, 1) for key, value in scores.items()}

        except json.JSONDecodeError:
            logger.error("Summary is not in valid JSON format")
            return {key: 0.0 for key in ["構造の完全性", "情報量", "簡潔性", "総合スコア"]}
        except Exception as e:
            logger.error(f"Error evaluating summary quality: {str(e)}")
            return {key: 0.0 for key in ["構造の完全性", "情報量", "簡潔性", "総合スコア"]}

    def generate_summary(self, text: str, style: str = "balanced") -> tuple:
        """Generate a summary of the given text and evaluate its quality"""
        try:
            # Create cache key including style
            cache_key = hash(f"{text}_{style}")
            if cache_key in self._cache:
                return self._cache[cache_key]

            prompt = self._create_summary_prompt(text, style)
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
            quality_scores = self._evaluate_summary_quality(summary, style)

            # Cache the result
            result = (summary, quality_scores)
            self._cache[cache_key] = result
            return result

        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            raise
