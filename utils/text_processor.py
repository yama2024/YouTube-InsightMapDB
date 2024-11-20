import google.generativeai as genai
import os
import logging
import time
from time import sleep
from random import uniform
import hashlib
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter
import re
from cachetools import TTLCache
from typing import Optional, Callable

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RateLimiter:
    def __init__(self):
        self.last_request = 0
        self.min_interval = 1.0  # 最小待機時間（秒）

    def wait(self):
        now = time.time()
        elapsed = now - self.last_request
        if elapsed < self.min_interval:
            sleep_time = self.min_interval - elapsed + uniform(0.1, 0.5)
            sleep(sleep_time)
        self.last_request = time.time()

class TextProcessor:
    def __init__(self):
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("Gemini API key is not set in environment variables")
        
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-1.5-pro')
        self.rate_limiter = RateLimiter()
        
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

    def _retry_with_backoff(self, func, max_retries=3):
        """Retry function with exponential backoff."""
        for attempt in range(max_retries):
            try:
                self.rate_limiter.wait()  # レート制限を適用
                return func()
            except Exception as e:
                if "429" in str(e):
                    wait_time = (2 ** attempt) + uniform(0, 1)
                    sleep(wait_time)
                    if attempt == max_retries - 1:
                        raise Exception("API制限に達しました。しばらく待ってから再試行してください。")
                else:
                    raise e

    def _get_generation_config(self):
        """Get generation config for Gemini API."""
        return genai.types.GenerationConfig(
            temperature=0.3,
            top_p=0.8,
            top_k=40,
            max_output_tokens=8192,
        )

    def _create_summary_prompt(self, text: str) -> str:
        """Create prompt for summary generation."""
        return f"""
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

    def get_transcript(self, url: str) -> str:
        """Get transcript from YouTube video with error handling and caching."""
        try:
            video_id = self._extract_video_id(url)
            
            # Check cache first
            if video_id in self.cache:
                return self.cache[video_id]
            
            def fetch_transcript():
                transcript = YouTubeTranscriptApi.get_transcript(
                    video_id,
                    languages=['ja', 'en']
                )
                formatter = TextFormatter()
                return formatter.format_transcript(transcript)
            
            # Use retry logic for transcript fetching
            formatted_transcript = self._retry_with_backoff(fetch_transcript)
            
            # Cache the result
            self.cache[video_id] = formatted_transcript
            
            return formatted_transcript
            
        except Exception as e:
            logger.error(f"Error getting transcript: {str(e)}")
            raise Exception(f"Failed to get transcript: {str(e)}")

    def generate_summary(self, text: str, progress_callback: Optional[Callable] = None) -> str:
        """Generate an enhanced summary using Gemini with improved error handling and caching."""
        try:
            if not text:
                raise ValueError("入力テキストが空です")

            if progress_callback:
                progress_callback(0.2, "テキストを解析中...")

            # キャッシュをチェック
            cache_key = hashlib.md5(text.encode()).hexdigest()
            if cache_key in self.cache:
                if progress_callback:
                    progress_callback(1.0, "✨ キャッシュから要約を取得しました")
                return self.cache[cache_key]

            if progress_callback:
                progress_callback(0.4, "AI要約を生成中...")

            def generate():
                response = self.model.generate_content(
                    self._create_summary_prompt(text),
                    generation_config=self._get_generation_config()
                )
                return response.text.strip()

            # 再試行ロジックを使用
            summary = self._retry_with_backoff(generate)
            
            if progress_callback:
                progress_callback(0.8, "要約を整形中...")

            if not summary:
                raise ValueError("Empty response from Gemini API")

            # 成功した場合はキャッシュに保存
            self.cache[cache_key] = summary

            if progress_callback:
                progress_callback(1.0, "✨ 要約が完了しました")

            return summary

        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg:
                error_msg = "API制限に達しました。しばらく待ってから再試行してください。"
            logger.error(f"Error generating summary: {error_msg}")
            if progress_callback:
                progress_callback(1.0, f"❌ エラーが発生しました: {error_msg}")
            raise Exception(f"要約の生成に失敗しました: {error_msg}")

    def proofread_text(self, text: str, progress_callback: Optional[Callable] = None) -> str:
        """Proofread and enhance text with improved error handling and caching."""
        try:
            if not text:
                raise ValueError("Input text is empty")

            if progress_callback:
                progress_callback(0.2, "テキストを解析中...")

            # キャッシュをチェック
            cache_key = hashlib.md5(f"proofread_{text}".encode()).hexdigest()
            if cache_key in self.cache:
                if progress_callback:
                    progress_callback(1.0, "✨ キャッシュから校正済みテキストを取得しました")
                return self.cache[cache_key]

            if progress_callback:
                progress_callback(0.4, "文章を校正中...")

            def proofread():
                response = self.model.generate_content(
                    f"""
以下のテキストを校正・整形してください：

{text}

要件：
1. 文章の明確性と読みやすさの向上
2. 文法・表現の改善
3. 文脈の一貫性確保
4. 専門用語の適切な使用
5. 段落構造の最適化

出力は整形されたテキストのみとし、説明等は不要です。
""",
                    generation_config=self._get_generation_config()
                )
                return response.text.strip()

            # 再試行ロジックを使用
            enhanced_text = self._retry_with_backoff(proofread)

            if progress_callback:
                progress_callback(0.8, "最終調整中...")

            if not enhanced_text:
                raise ValueError("Empty response from Gemini API")

            # 成功した場合はキャッシュに保存
            self.cache[cache_key] = enhanced_text

            if progress_callback:
                progress_callback(1.0, "✨ 校正が完了しました")

            return enhanced_text

        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg:
                error_msg = "API制限に達しました。しばらく待ってから再試行してください。"
            logger.error(f"Error proofreading text: {error_msg}")
            if progress_callback:
                progress_callback(1.0, f"❌ エラーが発生しました: {error_msg}")
            raise Exception(f"Failed to proofread text: {error_msg}")
