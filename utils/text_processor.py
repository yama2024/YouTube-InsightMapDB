import os
import json
import logging
from typing import Tuple, Dict, Any
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter
import google.generativeai as genai
from concurrent.futures import ThreadPoolExecutor
import re

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TextProcessor:
    def __init__(self):
        self._setup_gemini()
        self._cache = {}

    def _setup_gemini(self):
        """Initialize Gemini API with the provided key"""
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("Gemini API key is not set in environment variables")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-pro')

    def get_transcript(self, video_url: str) -> str:
        """Extract transcript from YouTube video"""
        try:
            video_id = self._extract_video_id(video_url)
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            transcript = transcript_list.find_transcript(['ja', 'en'])
            transcript_data = transcript.fetch()
            formatter = TextFormatter()
            return formatter.format_transcript(transcript_data)
        except Exception as e:
            logger.error(f"Failed to get transcript: {str(e)}")
            raise ValueError(f"文字起こしの取得に失敗しました: {str(e)}")

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

    def generate_summary(self, text: str, style: str = "overview") -> Tuple[str, Dict[str, float]]:
        """Generate a summary of the text with specified style"""
        try:
            # Validate style
            if style not in ["detailed", "overview"]:
                logger.warning(f"Invalid style '{style}', defaulting to 'overview'")
                style = "overview"

            cache_key = f"{hash(text)}_{style}"
            if cache_key in self._cache:
                return self._cache[cache_key]

            prompt = self._create_summary_prompt(text, style)
            response = self.model.generate_content(prompt)
            
            if not response.text:
                raise ValueError("空の応答が返されました")

            # Clean and parse the response
            summary = response.text.strip()
            
            # Remove markdown code block if present
            if summary.startswith('```json'):
                summary = summary[7:]
            if summary.endswith('```'):
                summary = summary[:-3]
            
            # Additional cleanup and formatting
            summary = summary.strip()
            
            # Remove any irregular whitespace and normalize newlines
            summary = re.sub(r'\s+', ' ', summary)
            summary = re.sub(r'[\n\r]+', '\n', summary)
            
            # Fix common JSON formatting issues
            summary = re.sub(r'(?<!\\)"', '\\"', summary)  # エスケープされていない引用符の処理
            summary = re.sub(r'\\+\"', '\\"', summary)     # 重複したエスケープの正規化
            summary = re.sub(r'[\x00-\x1F]', '', summary)  # 制御文字の削除
            
            # Try to detect and fix truncated JSON
            if not summary.endswith('}'):
                summary += '}'
            if summary.count('{') > summary.count('}'):
                summary += '}'
            
            try:
                # First attempt to parse with strict JSON rules
                json_data = json.loads(summary, strict=False)
                
                # Verify required fields
                required_fields = ["動画の概要", "ポイント", "結論"]
                missing_fields = [field for field in required_fields if field not in json_data]
                if missing_fields:
                    raise ValueError(f"必須フィールドが不足しています: {', '.join(missing_fields)}")
                
                # Ensure proper structure of nested objects
                if not isinstance(json_data["ポイント"], list):
                    raise ValueError("'ポイント'は配列である必要があります")
                
                # Re-serialize with proper formatting
                summary = json.dumps(json_data, ensure_ascii=False, indent=2)
                
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON response: {str(e)}")
                logger.error(f"Received text: {summary}")
                
                try:
                    # Try to fix common JSON formatting issues
                    summary = re.sub(r',\s*}', '}', summary)  # Remove trailing commas
                    summary = re.sub(r',\s*]', ']', summary)  # Remove trailing commas in arrays
                    
                    # Try parsing again with the fixed JSON
                    json_data = json.loads(summary, strict=False)
                    logger.info("JSON was successfully parsed after fixing formatting issues")
                except Exception as inner_e:
                    logger.error(f"Failed to fix JSON: {str(inner_e)}")
                    raise ValueError(f"不正なJSON形式の応答が返されました。修正を試みましたが失敗しました: {str(e)}")
            except ValueError as e:
                logger.error(f"JSON validation error: {str(e)}")
                raise ValueError(f"JSON構造の検証に失敗しました: {str(e)}")
            except Exception as e:
                logger.error(f"Unexpected error in JSON processing: {str(e)}")
                raise ValueError(f"JSON処理中に予期せぬエラーが発生しました: {str(e)}")

            # Evaluate summary quality
            quality_scores = self._evaluate_summary_quality(summary, text, style)
            
            # Cache the result
            result = (summary, quality_scores)
            self._cache[cache_key] = result
            return result

        except Exception as e:
            logger.error(f"Summary generation error: {str(e)}")
            raise ValueError(f"要約の生成に失敗しました: {str(e)}")

    def _create_summary_prompt(self, text: str, style: str) -> str:
        """Create a prompt for summary generation based on style"""
        base_prompt = f"""
以下のテキストを解析し、構造化された要約をJSON形式で生成してください。

テキスト:
{text}

要約の形式は以下のJSONスキーマに従ってください:
{{
    "動画の概要": "string",
    "ポイント": [
        {{
            "番号": number,
            "タイトル": "string",
            "内容": "string",
            "重要度": number (1-5),
            "補足情報": "string" (省略可)
        }}
    ],
    "結論": "string",
    "キーワード": [
        {{
            "用語": "string",
            "説明": "string",
            "関連用語": ["string"] (省略可)
        }}
    ]
}}
"""

        if style == "detailed":
            return base_prompt + """
詳細スタイルの要件:
- より深い分析と詳細な説明を含める
- 各ポイントに補足情報を追加
- キーワードに関連用語を含める
- 重要度は詳細に5段階で評価
"""
        else:  # overview style
            return base_prompt + """
概要スタイルの要件:
- 簡潔で要点を押さえた説明
- 重要なポイントのみを抽出
- 補足情報は特に重要な場合のみ含める
- キーワードは主要なものに限定
- 重要度は主要なポイントを中心に評価
"""

    def _evaluate_summary_quality(self, summary: str, original_text: str, style: str) -> Dict[str, float]:
        """Evaluate the quality of the generated summary"""
        try:
            summary_data = json.loads(summary)
            
            # Base scoring weights
            weights = {
                "detailed": {
                    "構造の完全性": 0.3,
                    "情報量": 0.4,
                    "簡潔性": 0.3
                },
                "overview": {
                    "構造の完全性": 0.3,
                    "情報量": 0.3,
                    "簡潔性": 0.4
                }
            }[style]

            # Evaluate structure completeness
            structure_score = self._evaluate_structure(summary_data)
            
            # Evaluate information content
            info_score = self._evaluate_information(summary_data, style)
            
            # Evaluate conciseness
            concise_score = self._evaluate_conciseness(summary_data, style)
            
            # Calculate weighted total score
            total_score = (
                structure_score * weights["構造の完全性"] +
                info_score * weights["情報量"] +
                concise_score * weights["簡潔性"]
            )

            return {
                "構造の完全性": round(structure_score, 1),
                "情報量": round(info_score, 1),
                "簡潔性": round(concise_score, 1),
                "総合スコア": round(total_score, 1)
            }

        except Exception as e:
            logger.error(f"Quality evaluation error: {str(e)}")
            return {
                "構造の完全性": 5.0,
                "情報量": 5.0,
                "簡潔性": 5.0,
                "総合スコア": 5.0
            }

    def _evaluate_structure(self, summary_data: Dict[str, Any]) -> float:
        """Evaluate the structural completeness of the summary"""
        score = 7.0  # Base score
        
        # Check for required sections
        if "動画の概要" in summary_data:
            score += 1.0
        if "ポイント" in summary_data and len(summary_data["ポイント"]) > 0:
            score += 1.0
        if "結論" in summary_data:
            score += 1.0
        
        return min(10.0, score)

    def _evaluate_information(self, summary_data: Dict[str, Any], style: str) -> float:
        """Evaluate the information content of the summary"""
        score = 5.0  # Base score
        
        points = summary_data.get("ポイント", [])
        keywords = summary_data.get("キーワード", [])
        
        if style == "detailed":
            # Check for detailed information
            if points and all("補足情報" in p for p in points):
                score += 2.0
            if keywords and all("関連用語" in k for k in keywords):
                score += 2.0
            if len(points) >= 5:
                score += 1.0
        else:  # overview
            # Check for concise information
            if points and len(points) >= 3:
                score += 2.0
            if keywords and len(keywords) >= 3:
                score += 2.0
            if all(len(p.get("内容", "")) < 100 for p in points):
                score += 1.0
        
        return min(10.0, score)

    def _evaluate_conciseness(self, summary_data: Dict[str, Any], style: str) -> float:
        """Evaluate the conciseness of the summary"""
        score = 7.0  # Base score
        
        overview = summary_data.get("動画の概要", "")
        points = summary_data.get("ポイント", [])
        
        if style == "detailed":
            # For detailed style, check for comprehensive explanations
            if len(overview) > 100:
                score += 1.0
            if points and all(len(p.get("内容", "")) > 50 for p in points):
                score += 2.0
        else:  # overview
            # For overview style, check for brevity
            if len(overview) < 100:
                score += 1.0
            if points and all(len(p.get("内容", "")) < 50 for p in points):
                score += 2.0
        
        return min(10.0, score)
