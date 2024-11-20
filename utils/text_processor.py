import google.generativeai as genai
import os
import logging
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter
import re
from cachetools import TTLCache
from typing import Optional, Callable

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TextProcessor:
    def __init__(self):
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("Gemini API key is not set in environment variables")
        
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-1.5-pro')
        
        # Initialize cache with 1-hour TTL
        self.cache = TTLCache(maxsize=100, ttl=3600)

    def _extract_video_id(self, url: str) -> str:
        """Extract YouTube video ID from URL."""
        try:
            patterns = [
                r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
                r'(?:youtu\.be\/)([0-9A-Za-z_-]{11})',
                r'(?:embed\/)([0-9A-Za-z_-]{11})'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, url)
                if match:
                    return match.group(1)
            raise ValueError("Invalid YouTube URL format")
        except Exception as e:
            logger.error(f"Error extracting video ID: {str(e)}")
            raise ValueError(f"Could not extract video ID from URL: {str(e)}")

    def get_transcript(self, url: str) -> str:
        """Get transcript from YouTube video with error handling and caching."""
        try:
            video_id = self._extract_video_id(url)
            
            # Check cache first
            if video_id in self.cache:
                return self.cache[video_id]
            
            # Get transcript
            transcript = YouTubeTranscriptApi.get_transcript(
                video_id,
                languages=['ja', 'en']
            )
            
            # Format transcript
            formatter = TextFormatter()
            formatted_transcript = formatter.format_transcript(transcript)
            
            # Cache the result
            self.cache[video_id] = formatted_transcript
            
            return formatted_transcript
            
        except Exception as e:
            logger.error(f"Error getting transcript: {str(e)}")
            raise Exception(f"Failed to get transcript: {str(e)}")

    def generate_summary(self, text: str, progress_callback: Optional[Callable] = None) -> str:
        """Generate an enhanced summary using Gemini with improved prompting and error handling."""
        try:
            if not text:
                raise ValueError("Input text is empty")

            if progress_callback:
                progress_callback(0.2, "テキストを解析中...")

            prompt = f"""
以下のテキストを詳細に分析し、構造化された要約を生成してください。

入力テキスト:
{text}

要約の要件:
1. 概要（100文字以内）
2. 主要なポイント（箇条書き）
3. 詳細な分析（各主要ポイントの展開）
4. キーワードと重要な概念の説明

出力形式:
# 概要
[簡潔な概要]

# 主要ポイント
- [ポイント1]
- [ポイント2]
...

# 詳細分析
## [ポイント1]
[詳細な説明]

## [ポイント2]
[詳細な説明]
...

# キーワードと概念
- [キーワード1]: [説明]
- [キーワード2]: [説明]
...
"""

            if progress_callback:
                progress_callback(0.4, "AI要約を生成中...")

            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.3,
                    top_p=0.8,
                    top_k=40,
                    max_output_tokens=8192,
                )
            )

            if progress_callback:
                progress_callback(0.8, "要約を整形中...")

            if not response or not response.text:
                raise ValueError("Empty response from Gemini API")

            summary = response.text.strip()

            if progress_callback:
                progress_callback(1.0, "✨ 要約が完了しました")

            return summary

        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            if progress_callback:
                progress_callback(1.0, f"❌ エラーが発生しました: {str(e)}")
            raise Exception(f"Failed to generate summary: {str(e)}")

    def proofread_text(self, text: str, progress_callback: Optional[Callable] = None) -> str:
        """Proofread and enhance text with improved error handling and progress tracking."""
        try:
            if not text:
                raise ValueError("Input text is empty")

            if progress_callback:
                progress_callback(0.2, "テキストを解析中...")

            prompt = f"""
以下のテキストを校正・整形してください：

{text}

要件：
1. 文章の明確性と読みやすさの向上
2. 文法・表現の改善
3. 文脈の一貫性確保
4. 専門用語の適切な使用
5. 段落構造の最適化

出力は整形されたテキストのみとし、説明等は不要です。
"""

            if progress_callback:
                progress_callback(0.4, "文章を校正中...")

            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.2,
                    top_p=0.8,
                    top_k=40,
                    max_output_tokens=8192,
                )
            )

            if progress_callback:
                progress_callback(0.8, "最終調整中...")

            if not response or not response.text:
                raise ValueError("Empty response from Gemini API")

            enhanced_text = response.text.strip()

            if progress_callback:
                progress_callback(1.0, "✨ 校正が完了しました")

            return enhanced_text

        except Exception as e:
            logger.error(f"Error proofreading text: {str(e)}")
            if progress_callback:
                progress_callback(1.0, f"❌ エラーが発生しました: {str(e)}")
            raise Exception(f"Failed to proofread text: {str(e)}")
