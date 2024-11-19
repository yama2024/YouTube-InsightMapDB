import logging
from youtube_transcript_api import YouTubeTranscriptApi
import google.generativeai as genai
import re
import os
import time
import random
from typing import List, Optional, Dict, Any, Tuple, Callable
from cachetools import TTLCache
import json
from datetime import datetime
from threading import Lock
import math
import hashlib

# Enhanced logging setup with more detailed formatting
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
)
logger = logging.getLogger(__name__)

# Enhanced error messages in Japanese
ERROR_MESSAGES = {
    'rate_limit': "APIトークンを使い切りました。{retry_after}秒後に再試行してください。",
    'retry_failed': "複数回再試行しましたが失敗しました。後ほど再度お試しください。",
    'processing': "要約を生成中です。しばらくお待ちください。",
    'token_exhausted': "APIトークンを使い切りました。{retry_after}秒後に再試行してください。",
    'api_error': "APIエラーが発生しました: {error_message}",
    'general_error': "予期せぬエラーが発生しました: {error_message}"
}

class RateLimitError(Exception):
    """Custom exception for rate limit errors"""
    def __init__(self, message: str, retry_after: Optional[int] = None):
        super().__init__(message)
        self.retry_after = retry_after

class YouTubeURLError(Exception):
    """Custom exception for YouTube URL related errors"""
    pass

class TokenBucket:
    """Token bucket rate limiter implementation"""
    def __init__(self, tokens_per_second: float, max_tokens: int):
        self.tokens_per_second = tokens_per_second
        self.max_tokens = max_tokens
        self.tokens = max_tokens
        self.last_update = time.time()
        self.lock = Lock()

    def _add_new_tokens(self):
        """Add new tokens based on time elapsed"""
        now = time.time()
        time_passed = now - self.last_update
        new_tokens = time_passed * self.tokens_per_second
        self.tokens = min(self.tokens + new_tokens, self.max_tokens)
        self.last_update = now

    def try_consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens from the bucket"""
        with self.lock:
            self._add_new_tokens()
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    def get_wait_time(self, tokens: int = 1) -> float:
        """Calculate wait time until enough tokens are available"""
        with self.lock:
            self._add_new_tokens()
            additional_tokens_needed = tokens - self.tokens
            if additional_tokens_needed <= 0:
                return 0
            return additional_tokens_needed / self.tokens_per_second

class TextProcessor:
    def __init__(self):
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("Gemini API key is not set in environment variables")
        
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-1.5-pro')
        
        # Enhanced caching with longer TTL for frequently accessed data
        self.subtitle_cache = TTLCache(maxsize=300, ttl=14400)  # 4 hours TTL
        self.processed_text_cache = TTLCache(maxsize=300, ttl=7200)  # 2 hours TTL
        self.summary_cache = TTLCache(maxsize=300, ttl=14400)  # 4 hours TTL for summaries
        
        # Rate limiting configuration with adjusted settings
        self.max_retries = 5
        self.base_delay = 64  # Base delay in seconds (increased from 2)
        self.max_delay = 300  # Maximum delay in seconds (increased from 64)
        self.jitter_factor = 0.1  # Maximum jitter as a fraction of delay
        
        # Updated token bucket configuration
        self.rate_limiter = TokenBucket(
            tokens_per_second=0.016,  # One request per 64 seconds
            max_tokens=3  # Limit concurrent requests
        )
        
        # Reduced chunk size for text processing
        self.max_chunk_size = 4000  # Reduced from 8000
        
        # URL patterns for video ID extraction
        self.url_patterns = [
            r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})',
            r'(?:https?://)?youtu\.be/([a-zA-Z0-9_-]{11})',
            r'(?:https?://)?(?:www\.)?youtube\.com/v/([a-zA-Z0-9_-]{11})',
            r'(?:https?://)?(?:www\.)?youtube\.com/embed/([a-zA-Z0-9_-]{11})'
        ]
        
        # Enhanced noise patterns for Japanese text
        self.noise_patterns = {
            'timestamps': r'\[?\(?\d{1,2}:\d{2}(?::\d{2})?\]?\)?',
            'speaker_tags': r'\[[^\]]*\]|\([^)]*\)',
            'filler_words': r'\b(えーと|えっと|えー|あの|あのー|まぁ|んー|そのー|なんか|こう|ね|ねぇ|さぁ|うーん|あー|そうですね|ちょっと)\b',
            'repeated_chars': r'([^\W\d_])\1{3,}',
            'multiple_spaces': r'[\s　]{2,}',
            'empty_lines': r'\n\s*\n',
            'punctuation': r'([。．！？])\1+',
            'noise_symbols': r'[♪♫♬♩†‡◊◆◇■□▲△▼▽○●◎]',
            'parentheses': r'（[^）]*）|\([^)]*\)',
            'unnecessary_symbols': r'[＊∗※#＃★☆►▷◁◀→←↑↓]',
            'commercial_markers': r'(?:CM|広告|スポンサー)(?:\s*\d*)?',
            'system_messages': r'(?:システム|エラー|通知)(?:：|:).*?(?:\n|$)',
            'automated_tags': r'\[(?:音楽|拍手|笑|BGM|SE|効果音)\]'
        }

    def _get_cache_key(self, text: str, operation: str) -> str:
        """Generate a unique cache key for the given text and operation"""
        # Create a more unique hash using SHA-256
        text_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]
        timestamp = datetime.now().strftime('%Y%m%d')
        return f"{operation}:{timestamp}:{text_hash}"

    def _chunk_text(self, text: str) -> List[str]:
        """Split text into chunks with improved handling of Japanese text"""
        if not text:
            return []

        # Split text at sentence boundaries
        sentences = re.split(r'([。！？])', text)
        chunks = []
        current_chunk = ""

        for i in range(0, len(sentences), 2):
            sentence = sentences[i] + (sentences[i + 1] if i + 1 < len(sentences) else "")
            
            if len(current_chunk) + len(sentence) <= self.max_chunk_size:
                current_chunk += sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = sentence

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    def _retry_with_backoff(self, func: Callable, *args, **kwargs) -> Any:
        """Execute a function with exponential backoff retry logic and jitter"""
        last_error = None
        for attempt in range(self.max_retries):
            try:
                # Check rate limiter
                wait_time = self.rate_limiter.get_wait_time()
                if wait_time > 0:
                    logger.warning(f"Rate limit cooldown. Waiting {wait_time:.2f}s")
                    time.sleep(wait_time)
                    
                if not self.rate_limiter.try_consume():
                    retry_after = math.ceil(wait_time)
                    raise RateLimitError(
                        ERROR_MESSAGES['rate_limit'].format(retry_after=retry_after),
                        retry_after=retry_after
                    )
                
                return func(*args, **kwargs)
                
            except Exception as e:
                last_error = e
                if isinstance(e, RateLimitError) or "429" in str(e) or "Resource has been exhausted" in str(e):
                    delay = min(self.max_delay, self.base_delay * (2 ** attempt))
                    jitter = random.uniform(0, delay * self.jitter_factor)
                    total_delay = delay + jitter
                    logger.warning(
                        f"Rate limit hit. Attempt {attempt + 1}/{self.max_retries}. "
                        f"Waiting {total_delay:.2f}s"
                    )
                    time.sleep(total_delay)
                    continue
                raise e
        
        raise RateLimitError(
            ERROR_MESSAGES['retry_failed'],
            retry_after=self.max_delay
        )

    def _extract_video_id(self, url: str) -> str:
        """Extract video ID from various YouTube URL formats"""
        if not url:
            raise YouTubeURLError("URLが空です")
            
        # Remove any leading/trailing whitespace and normalize
        url = url.strip()
        
        # Try each pattern
        for pattern in self.url_patterns:
            match = re.match(pattern, url)
            if match:
                video_id = match.group(1)
                if self._validate_video_id(video_id):
                    return video_id
                    
        # If no pattern matched or video ID was invalid
        raise YouTubeURLError(
            "無効なYouTube URLです。以下の形式がサポートされています:\n"
            "- https://www.youtube.com/watch?v=VIDEO_ID\n"
            "- https://youtu.be/VIDEO_ID\n"
            "- youtube.com/watch?v=VIDEO_ID"
        )

    def _validate_video_id(self, video_id: str) -> bool:
        """Validate YouTube video ID format"""
        if not video_id:
            return False
            
        # YouTube video IDs are 11 characters long and contain only alphanumeric chars, underscores, and hyphens
        video_id_pattern = r'^[a-zA-Z0-9_-]{11}$'
        return bool(re.match(video_id_pattern, video_id))

    def get_transcript(self, url: str) -> str:
        """Get transcript with improved URL handling, caching, and error handling"""
        try:
            # Check cache first
            cache_key = self._get_cache_key(url, "transcript")
            cached_transcript = self.subtitle_cache.get(cache_key)
            if cached_transcript:
                logger.info("Using cached transcript")
                return cached_transcript

            # Extract and validate video ID
            try:
                video_id = self._extract_video_id(url)
                logger.info(f"Successfully extracted video ID: {video_id}")
            except YouTubeURLError as e:
                logger.error(f"Invalid YouTube URL: {str(e)}")
                raise

            # Fetch transcript with language fallback
            try:
                transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['ja'])
            except Exception as e:
                logger.warning(f"Japanese transcript not found, trying English: {str(e)}")
                try:
                    transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['en'])
                except Exception as e:
                    logger.error(f"Failed to fetch transcript: {str(e)}")
                    raise ValueError("字幕を取得できませんでした。動画に字幕が設定されていないか、アクセスできない可能性があります。")

            # Process and combine transcript entries
            transcript = " ".join([entry['text'] for entry in transcript_list])
            
            # Cache the result
            self.subtitle_cache[cache_key] = transcript
            return transcript

        except YouTubeURLError as e:
            raise YouTubeURLError(str(e))
        except Exception as e:
            logger.error(f"Error fetching transcript: {str(e)}")
            raise ValueError(f"字幕の取得に失敗しました: {str(e)}")

    def generate_summary(self, text: str, progress_callback: Optional[Callable] = None) -> str:
        """Generate a summary with enhanced error handling and caching"""
        logger.info("Starting summary generation process")
        
        try:
            # Input validation
            is_valid, error_msg = self._validate_text(text)
            if not is_valid:
                raise ValueError(f"無効な入力テキスト: {error_msg}")
            
            # Check cache first
            cache_key = self._get_cache_key(text, "summary")
            cached_summary = self.summary_cache.get(cache_key)
            if cached_summary:
                logger.info("Using cached summary")
                return cached_summary

            # Clean and chunk the text
            cleaned_text = self._clean_text(text)
            text_chunks = self._chunk_text(cleaned_text)
            logger.info(f"Text split into {len(text_chunks)} chunks")

            # Process chunks with progress tracking
            chunk_summaries = []
            for i, chunk in enumerate(text_chunks):
                if progress_callback:
                    progress = (i + 1) / len(text_chunks)
                    progress_callback(progress, ERROR_MESSAGES['processing'])
                
                try:
                    summary = self._retry_with_backoff(
                        self._generate_chunk_summary,
                        chunk,
                        i,
                        len(text_chunks)
                    )
                    chunk_summaries.append(summary)
                except RateLimitError as e:
                    logger.error(f"Rate limit error during chunk processing: {str(e)}")
                    raise
                except Exception as e:
                    logger.error(f"Error processing chunk {i + 1}: {str(e)}")
                    raise

            # Combine summaries
            if chunk_summaries:
                combined_summary = self._retry_with_backoff(
                    self._combine_summaries,
                    chunk_summaries
                )
                
                # Cache the successful result
                self.summary_cache[cache_key] = combined_summary
                logger.info("Summary generation completed successfully")
                return combined_summary
            else:
                raise ValueError(ERROR_MESSAGES['general_error'].format(
                    error_message="チャンクから要約を生成できませんでした"
                ))

        except RateLimitError as e:
            logger.error(f"Rate limit error: {str(e)}")
            raise RateLimitError(
                ERROR_MESSAGES['token_exhausted'].format(
                    retry_after=e.retry_after or self.max_delay
                ),
                retry_after=e.retry_after
            )
        except Exception as e:
            logger.error(f"Error in summary generation: {str(e)}")
            raise ValueError(ERROR_MESSAGES['general_error'].format(error_message=str(e)))

    def _generate_chunk_summary(self, chunk: str, chunk_index: int, total_chunks: int) -> str:
        """Generate summary for a single chunk with enhanced error handling"""
        logger.info(f"Processing chunk {chunk_index + 1}/{total_chunks}")
        
        prompt = f"""
        このテキストはYouTube動画の文字起こしの一部です ({chunk_index + 1}/{total_chunks})。
        視聴者が内容を効率的に理解できるよう、包括的な要約を生成します。

        # 要約のガイドライン
        1. このチャンクの重要なポイントを簡潔に要約
        2. 専門用語や技術的な概念は以下のように扱う：
           - 初出時に簡潔な説明を付記
           - 可能な場合は平易な言葉で言い換え
           - 重要な専門用語は文脈を保持

        # 入力テキスト：
        {chunk}
        """

        try:
            response = self.model.generate_content(prompt)
            if not response or not response.text:
                raise ValueError(ERROR_MESSAGES['api_error'].format(
                    error_message="APIからの応答が空でした"
                ))
            
            return response.text.strip()
            
        except Exception as e:
            logger.error(f"Error in chunk summary generation: {str(e)}")
            raise ValueError(ERROR_MESSAGES['api_error'].format(error_message=str(e)))

    def _clean_text(self, text: str) -> str:
        """Clean text with enhanced noise removal"""
        cleaned = text
        for pattern_name, pattern in self.noise_patterns.items():
            cleaned = re.sub(pattern, ' ', cleaned)
        return re.sub(r'\s+', ' ', cleaned).strip()

    def _validate_text(self, text: str) -> Tuple[bool, str]:
        """Validate input text with enhanced checks"""
        try:
            if not text:
                return False, "テキストが空です"
            
            if len(text) < 100:
                return False, "テキストが短すぎます（最低100文字必要です）"
            
            try:
                text.encode('utf-8').decode('utf-8')
            except UnicodeError:
                return False, "テキストのエンコーディングが無効です"
            
            noise_ratio = len(re.findall(r'[^\w\s。、！？」』）「『（]', text)) / len(text)
            if noise_ratio > 0.3:
                return False, "テキストにノイズが多すぎます（特殊文字が30%以上）"
            
            return True, ""
            
        except Exception as e:
            logger.error(f"Text validation error: {str(e)}")
            return False, f"テキスト検証エラー: {str(e)}"

    def _chunk_text(self, text: str, max_chunk_size: int = 8000) -> List[str]:
        """Split text into manageable chunks with improved sentence boundary detection"""
        try:
            sentences = re.split(r'([。！？])', text)
            chunks = []
            current_chunk = ""
            
            for i in range(0, len(sentences), 2):
                sentence = sentences[i] + (sentences[i+1] if i+1 < len(sentences) else "")
                if len(current_chunk) + len(sentence) < max_chunk_size:
                    current_chunk += sentence
                else:
                    if current_chunk:
                        chunks.append(current_chunk)
                    current_chunk = sentence
                    
            if current_chunk:
                chunks.append(current_chunk)
                
            return chunks
            
        except Exception as e:
            logger.error(f"Error in chunking text: {str(e)}")
            raise ValueError(ERROR_MESSAGES['general_error'].format(error_message=str(e)))

    def _combine_summaries(self, summaries: List[str]) -> str:
        """Combine chunk summaries into a cohesive final summary"""
        try:
            combined_text = "\n\n".join(summaries)
            
            prompt = f"""
            以下の要約をより簡潔で一貫性のある一つの要約にまとめてください：

            {combined_text}
            
            # 要件：
            1. 重複する情報を統合
            2. 一貫した文体を維持
            3. 論理的な流れを保持
            4. 重要なポイントを強調
            """
            
            response = self._retry_with_backoff(
                self.model.generate_content,
                prompt
            )
            
            if not response or not response.text:
                raise ValueError(ERROR_MESSAGES['api_error'].format(
                    error_message="APIからの応答が空でした"
                ))
            
            return response.text.strip()
            
        except Exception as e:
            logger.error(f"Error combining summaries: {str(e)}")
            raise ValueError(ERROR_MESSAGES['general_error'].format(error_message=str(e)))

    def enhance_text(self, text: str, progress_callback: Optional[Callable] = None) -> str:
        """Enhance text with proper formatting and structure"""
        try:
            if not text:
                return ""

            cache_key = self._get_cache_key(text, "enhance")
            cached_result = self.processed_text_cache.get(cache_key)
            if cached_result:
                return cached_result

            # Clean and chunk text
            cleaned_text = self._clean_text(text)
            chunks = self._chunk_text(cleaned_text)
            
            enhanced_chunks = []
            for i, chunk in enumerate(chunks):
                if progress_callback:
                    progress = (i + 1) / len(chunks)
                    progress_callback(progress, "テキストを整形中...")
                
                prompt = f"""
                以下のテキストを整形・改善してください：

                {chunk}

                要件：
                1. 文章を段落に分割
                2. 読点、句点を適切に配置
                3. 冗長な表現を簡潔に
                4. 専門用語には説明を追加
                5. 文体を統一
                """

                try:
                    response = self._retry_with_backoff(
                        self.model.generate_content,
                        prompt
                    )
                    
                    if response and response.text:
                        enhanced_chunks.append(response.text.strip())
                    else:
                        raise ValueError("空の応答を受け取りました")
                        
                except Exception as e:
                    logger.error(f"Error enhancing chunk {i + 1}: {str(e)}")
                    raise

            # Combine enhanced chunks
            result = "\n\n".join(enhanced_chunks)
            self.processed_text_cache[cache_key] = result
            return result

        except Exception as e:
            logger.error(f"Error in text enhancement: {str(e)}")
            raise ValueError(ERROR_MESSAGES['general_error'].format(error_message=str(e)))

    def proofread_text(self, text: str, progress_callback: Optional[Callable] = None) -> str:
        """Proofread and enhance text with proper formatting and structure"""
        try:
            if not text:
                return ""

            cache_key = self._get_cache_key(text, "proofread")
            cached_result = self.processed_text_cache.get(cache_key)
            if cached_result:
                return cached_result

            prompt = f"""
            以下のテキストを校正・整形してください：

            {text}

            要件：
            1. 文章を段落に分割
            2. 読点、句点を適切に配置
            3. 冗長な表現を簡潔に
            4. 専門用語には説明を追加
            5. 文体を統一
            """

            response = self._retry_with_backoff(
                self.model.generate_content,
                prompt
            )

            if not response or not response.text:
                raise ValueError(ERROR_MESSAGES['api_error'].format(
                    error_message="校正処理の応答が空でした"
                ))

            result = response.text.strip()
            self.processed_text_cache[cache_key] = result
            return result

        except RateLimitError as e:
            logger.error(f"Rate limit error during proofreading: {str(e)}")
            raise RateLimitError(
                ERROR_MESSAGES['token_exhausted'].format(
                    retry_after=e.retry_after or self.max_delay
                ),
                retry_after=e.retry_after
            )
        except Exception as e:
            logger.error(f"Error in text proofreading: {str(e)}")
            raise ValueError(ERROR_MESSAGES['general_error'].format(error_message=str(e)))