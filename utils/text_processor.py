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
from typing import Optional, Callable, List, Dict
import json
import google.generativeai as genai

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DynamicRateLimiter:
    def __init__(self):
        self.last_request = 0
        self.base_interval = 1.0  # 基本待機時間（秒）
        self.response_times = []
        self.max_samples = 10
        self.backoff_factor = 1.5

    def update_interval(self, response_time: float):
        """応答時間に基づいて待機時間を動的に調整"""
        self.response_times.append(response_time)
        if len(self.response_times) > self.max_samples:
            self.response_times.pop(0)
        
        # 直近の応答時間の平均に基づいて基本待機時間を調整
        if self.response_times:
            avg_response_time = sum(self.response_times) / len(self.response_times)
            self.base_interval = max(1.0, min(5.0, avg_response_time * self.backoff_factor))

    def wait(self):
        """動的な待機時間を適用"""
        now = time.time()
        elapsed = now - self.last_request
        if elapsed < self.base_interval:
            sleep_time = self.base_interval - elapsed + uniform(0.1, 0.5)
            sleep(sleep_time)
        self.last_request = time.time()

class TextProcessor:
    def __init__(self):
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("Gemini API key is not set in environment variables")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-1.5-pro')
        self.rate_limiter = DynamicRateLimiter()
        
        # Initialize cache with 1-hour TTL
        self.cache = TTLCache(maxsize=100, ttl=3600)
        self.chunk_size = 6000  # Gemini Pro's context window size

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

    def _split_text_into_chunks(self, text: str) -> List[str]:
        """テキストを適切なサイズのチャンクに分割"""
        words = text.split()
        chunks = []
        current_chunk = []
        current_length = 0

        for word in words:
            word_length = len(word)
            if current_length + word_length + 1 <= self.chunk_size:
                current_chunk.append(word)
                current_length += word_length + 1
            else:
                chunks.append(' '.join(current_chunk))
                current_chunk = [word]
                current_length = word_length

        if current_chunk:
            chunks.append(' '.join(current_chunk))

        return chunks

    def _retry_with_backoff(self, func, max_retries=5):
        """改善された再試行ロジック with Gemini特有のエラーハンドリング"""
        last_error = None
        for attempt in range(max_retries):
            try:
                start_time = time.time()
                self.rate_limiter.wait()
                result = func()
                # 成功した場合は応答時間を更新
                self.rate_limiter.update_interval(time.time() - start_time)
                return result
            except Exception as e:
                error_msg = str(e)
                wait_time = (2 ** attempt) + uniform(0, 1)
                
                if "quota" in error_msg.lower():
                    raise Exception("API利用クォータを超過しました。後でもう一度お試しください。")
                elif "rate" in error_msg.lower():
                    logger.warning(f"Rate limit hit, waiting {wait_time:.2f} seconds...")
                    sleep(wait_time)
                else:
                    wait_time = uniform(1, 3)
                    sleep(wait_time)
                
                last_error = e
                if attempt == max_retries - 1:
                    if "quota" in error_msg.lower():
                        raise Exception("API利用クォータを超過しました。")
                    elif "rate" in error_msg.lower():
                        raise Exception("API制限に達しました。再試行回数を超過しました。")
                    else:
                        raise Exception(f"予期せぬエラーが発生しました: {str(e)}")

        raise last_error

    def _create_summary_prompt(self, text: str, context: Optional[Dict] = None) -> str:
        """Gemini APIに適したプロンプト生成"""
        context_info = ""
        if context:
            context_info = f"\nコンテキスト情報:\n{json.dumps(context, ensure_ascii=False, indent=2)}"

        prompt = f"""以下のテキストを分析し、構造化された要約を生成してください。

入力テキスト:
{text}
{context_info}

出力要件:
1. 概要（150文字以内）：主要なテーマと重要なポイントを簡潔に説明
2. 主要なポイント（3-5項目）：重要度順に具体的な説明を付けて記載
3. 詳細分析：各主要ポイントの詳細な展開と具体例
4. キーワードと重要概念：重要用語の定義と関連性の説明

以下のJSON形式で出力してください：
{{
    "概要": "string",
    "主要ポイント": [
        {{"タイトル": "string", "説明": "string"}}
    ],
    "詳細分析": [
        {{"ポイント": "string", "分析": "string"}}
    ],
    "キーワード": [
        {{"用語": "string", "説明": "string"}}
    ]
}}"""

        return prompt

    def generate_summary(self, text: str, progress_callback: Optional[Callable] = None) -> str:
        """Gemini APIを使用した改善された要約生成プロセス"""
        try:
            if not text:
                raise ValueError("入力テキストが空です")

            if progress_callback:
                progress_callback(0.1, "テキストを解析中...")

            # キャッシュチェック
            cache_key = hashlib.md5(text.encode()).hexdigest()
            if cache_key in self.cache:
                if progress_callback:
                    progress_callback(1.0, "✨ キャッシュから要約を取得しました")
                return self.cache[cache_key]

            # テキストを適切なサイズのチャンクに分割
            chunks = self._split_text_into_chunks(text)
            chunk_summaries = []
            context = {"total_chunks": len(chunks)}

            for i, chunk in enumerate(chunks, 1):
                if progress_callback:
                    progress = 0.1 + (0.7 * (i / len(chunks)))
                    progress_callback(progress, f"チャンク {i}/{len(chunks)} を処理中...")

                context.update({
                    "current_chunk": i,
                    "chunk_position": "開始" if i == 1 else "終了" if i == len(chunks) else "中間"
                })

                def process_chunk():
                    prompt = self._create_summary_prompt(chunk, context)
                    response = self.model.generate_content(
                        prompt,
                        generation_config=genai.types.GenerationConfig(
                            temperature=0.3,
                            top_p=0.8,
                            top_k=40,
                            max_output_tokens=8192,
                        )
                    )
                    return response.text

                chunk_summary = self._retry_with_backoff(process_chunk)
                try:
                    chunk_summaries.append(json.loads(chunk_summary))
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse JSON from chunk {i}, skipping...")
                    continue

            if progress_callback:
                progress_callback(0.9, "要約を統合中...")

            # 最終的な要約を生成
            def generate_final_summary():
                combined_context = {
                    "final_summary": True,
                    "chunk_summaries": chunk_summaries
                }
                prompt = self._create_summary_prompt(text, combined_context)
                response = self.model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.3,
                        top_p=0.8,
                        top_k=40,
                        max_output_tokens=8192,
                    )
                )
                return response.text

            final_summary_json = self._retry_with_backoff(generate_final_summary)
            try:
                final_summary_data = json.loads(final_summary_json)
            except json.JSONDecodeError:
                raise ValueError("API returned invalid JSON format")

            # JSONを整形されたテキストに変換
            final_summary = f"# 概要\n{final_summary_data['概要']}\n\n"
            final_summary += "# 主要ポイント\n"
            for point in final_summary_data['主要ポイント']:
                final_summary += f"- {point['タイトル']}: {point['説明']}\n"
            
            final_summary += "\n# 詳細分析\n"
            for analysis in final_summary_data['詳細分析']:
                final_summary += f"## {analysis['ポイント']}\n{analysis['分析']}\n\n"
            
            final_summary += "# キーワードと重要概念\n"
            for keyword in final_summary_data['キーワード']:
                final_summary += f"- {keyword['用語']}: {keyword['説明']}\n"

            # キャッシュに保存
            self.cache[cache_key] = final_summary

            if progress_callback:
                progress_callback(1.0, "✨ 要約が完了しました")

            return final_summary

        except Exception as e:
            error_msg = str(e)
            if "quota" in error_msg.lower():
                error_msg = "API利用クォータを超過しました。後でもう一度お試しください。"
            elif "rate" in error_msg.lower():
                error_msg = "API制限に達しました。しばらく待ってから再試行してください。"
            
            logger.error(f"Error generating summary: {error_msg}")
            if progress_callback:
                progress_callback(1.0, f"❌ エラーが発生しました: {error_msg}")
            raise Exception(f"要約の生成に失敗しました: {error_msg}")

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

    def proofread_text(self, text: str, progress_callback: Optional[Callable] = None) -> str:
        """Proofread and enhance text using Gemini API."""
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
                prompt = """以下のテキストを校正・整形してください。

要件:
1. 文章の明確性と読みやすさの向上
2. 文法・表現の改善
3. 文脈の一貫性確保
4. 専門用語の適切な使用
5. 段落構造の最適化

入力テキスト:
""" + text

                response = self.model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.3,
                        top_p=0.8,
                        top_k=40,
                        max_output_tokens=8192,
                    )
                )
                return response.text

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
            if "quota" in error_msg.lower():
                error_msg = "API利用クォータを超過しました。後でもう一度お試しください。"
            elif "rate" in error_msg.lower():
                error_msg = "API制限に達しました。しばらく待ってから再試行してください。"
            logger.error(f"Error proofreading text: {error_msg}")
            if progress_callback:
                progress_callback(1.0, f"❌ エラーが発生しました: {error_msg}")
            raise Exception(f"Failed to proofread text: {error_msg}")
