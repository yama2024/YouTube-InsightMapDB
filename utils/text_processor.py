import logging
from youtube_transcript_api import YouTubeTranscriptApi
import google.generativeai as genai
import re
import os
import time
import random
from typing import List, Optional, Dict, Any, Tuple, Callable
from cachetools import TTLCache, cached
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential_jitter,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
    RetryError,
    after_log
)

# Enhanced logging setup with more detailed format
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
)
logger = logging.getLogger(__name__)

class APIError(Exception):
    """Base class for API related errors"""
    pass

class ConnectionError(APIError):
    """Error when connection to API fails"""
    pass

class TimeoutError(APIError):
    """Error when API request times out"""
    pass

class QuotaExceededError(APIError):
    """Error when API quota is exceeded"""
    pass

class InvalidInputError(APIError):
    """Error when input is invalid"""
    pass

class PartialResultError(APIError):
    """Error when only partial results are available"""
    def __init__(self, partial_result: str, message: str):
        self.partial_result = partial_result
        self.message = message
        super().__init__(message)

class TextProcessor:
    def __init__(self):
        self.api_calls = 0
        self.api_errors = 0
        self.performance_metrics = {
            'total_processing_time': 0.0,
            'successful_calls': 0.0,
            'failed_calls': 0.0,
            'retry_count': 0.0
        }
        
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("Gemini API キーが環境変数に設定されていません")
        
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-1.5-pro')
        
        # Initialize caches with monitoring
        self.subtitle_cache = TTLCache(maxsize=100, ttl=3600)
        self.processed_text_cache = TTLCache(maxsize=100, ttl=1800)
        
        # Japanese error messages
        self.error_messages = {
            'timeout': "応答待ちがタイムアウトしました。処理に時間がかかっているため、後でもう一度お試しください。",
            'quota': "API利用制限に達しました。しばらく待ってから再度お試しください。",
            'connection': "ネットワーク接続エラーが発生しました。インターネット接続を確認してください。",
            'invalid_input': "入力データが無効です。テキストを確認して再試行してください。",
            'partial_result': "一部の結果のみ生成できました。完全な結果を得るには再試行が必要です。",
            'unknown': "予期せぬエラーが発生しました。システム管理者に連絡してください。"
        }

        # Initialize performance monitoring
        self.start_monitoring()

    def start_monitoring(self):
        """Initialize performance monitoring"""
        self.performance_metrics = {
            'start_time': time.time(),
            'api_calls': 0.0,
            'successful_calls': 0.0,
            'failed_calls': 0.0,
            'retry_attempts': 0.0,
            'total_processing_time': 0.0,
            'average_response_time': 0.0
        }

    def update_metrics(self, success: bool, processing_time: float, retries: int = 0):
        """Update performance metrics"""
        self.performance_metrics['api_calls'] += 1.0
        if success:
            self.performance_metrics['successful_calls'] += 1.0
        else:
            self.performance_metrics['failed_calls'] += 1.0
        
        self.performance_metrics['retry_attempts'] += retries
        self.performance_metrics['total_processing_time'] += processing_time
        self.performance_metrics['average_response_time'] = (
            self.performance_metrics['total_processing_time'] / 
            max(self.performance_metrics['api_calls'], 1.0)
        )

    def log_performance_metrics(self):
        """Log current performance metrics"""
        metrics = self.performance_metrics
        logger.info(f"""Performance Metrics:
        Total API Calls: {metrics['api_calls']}
        Success Rate: {(metrics['successful_calls'] / max(metrics['api_calls'], 1.0)) * 100:.2f}%
        Average Response Time: {metrics['average_response_time']:.2f}s
        Retry Attempts: {metrics['retry_attempts']}
        """)

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1.5, min=4, max=60),
        retry=(
            retry_if_exception_type(ConnectionError) |
            retry_if_exception_type(TimeoutError) |
            retry_if_exception_type(APIError)
        ),
        before_sleep=before_sleep_log(logger, logging.INFO),
        after=after_log(logger, logging.INFO)
    )
    def generate_summary(self, text: str, progress_callback: Optional[Callable] = None) -> str:
        """Generate AI summary with enhanced error handling and monitoring"""
        if not text:
            raise InvalidInputError("入力テキストが空です")
        
        start_time = time.time()
        retry_count = 0
        
        try:
            if progress_callback:
                progress_callback(0.1, "🔍 テキスト解析の準備中...")
            
            # Log input statistics
            logger.info(f"入力テキスト文字数: {len(text)}")
            
            prompt = f"""
# 目的:
入力テキストの包括的な要約を生成します。

# 要約の構造:
1. 概要（全体の要点）
2. 主要なポイント（箇条書き）
3. 詳細な分析（重要なトピックごと）
4. 結論

# フォーマット規則:
- Markdown形式で出力
- 適切な見出しレベル
- 重要ポイントの強調
- 効果的な箇条書き

入力テキスト:
{text}
"""
            
            if progress_callback:
                progress_callback(0.2, "🤖 AI分析を開始...")
            
            try:
                # Set timeout and validate response
                generation_start = time.time()
                response = self.model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.3,
                        top_p=0.8,
                        top_k=40,
                        max_output_tokens=8192,
                    ),
                )
                
                generation_time = time.time() - generation_start
                logger.info(f"AI生成完了 (生成時間: {generation_time:.2f}秒)")
                
                if not response.text:
                    raise APIError("AIモデルからの応答が空です")
                
                if progress_callback:
                    progress_callback(0.6, "📝 要約を最適化中...")
                
                # Process and validate the response
                summary = response.text
                if len(summary) < len(text) * 0.1:
                    logger.warning("生成された要約が短すぎます")
                    raise PartialResultError(
                        summary,
                        "要約が不完全です。より詳細な要約を生成するには再試行が必要です。"
                    )
                
                # Post-processing with detailed progress
                if progress_callback:
                    progress_callback(0.7, "✨ テキストを整形中...")
                
                try:
                    summary = self._clean_text(summary)
                    if progress_callback:
                        progress_callback(0.8, "📊 文章構造を最適化中...")
                    
                    summary = self._improve_sentence_structure(summary)
                    if progress_callback:
                        progress_callback(0.9, "🔍 最終チェック中...")
                    
                except Exception as e:
                    logger.warning(f"後処理中の警告: {str(e)}")
                    if len(summary) > 0:
                        logger.info("部分的な結果を使用して続行します")
                    else:
                        raise APIError("テキスト処理中にエラーが発生しました")
                
                # Update performance metrics
                processing_time = time.time() - start_time
                self.update_metrics(True, processing_time, retry_count)
                self.log_performance_metrics()
                
                if progress_callback:
                    progress_callback(1.0, "✅ 要約が完了しました")
                
                return summary
                
            except Exception as e:
                self.api_errors += 1
                error_msg = str(e).lower()
                retry_count += 1
                
                if "timeout" in error_msg:
                    raise TimeoutError(self.error_messages['timeout'])
                elif "quota" in error_msg:
                    raise QuotaExceededError(self.error_messages['quota'])
                elif "connection" in error_msg:
                    raise ConnectionError(self.error_messages['connection'])
                else:
                    raise APIError(f"AI生成エラー: {self._get_user_friendly_error_message(str(e))}")
                
        except RetryError as e:
            logger.error(f"リトライ後も要約生成に失敗: {str(e)}")
            if progress_callback:
                progress_callback(1.0, "❌ 要約生成に失敗しました")
            
            # Update failure metrics
            processing_time = time.time() - start_time
            self.update_metrics(False, processing_time, retry_count)
            self.log_performance_metrics()
            
            raise APIError("""
要約の生成に失敗しました。以下をお試しください：
1. しばらく待ってから再度実行
2. テキストを短く区切って処理
3. インターネット接続を確認
4. 別のテキストで試行
""")
            
        except Exception as e:
            logger.error(f"致命的なエラー: {str(e)}")
            if progress_callback:
                progress_callback(1.0, "❌ システムエラーが発生しました")
            
            # Update failure metrics
            processing_time = time.time() - start_time
            self.update_metrics(False, processing_time, retry_count)
            self.log_performance_metrics()
            
            raise APIError(f"システムエラー: {self._get_user_friendly_error_message(str(e))}")

    def _clean_text(self, text: str) -> str:
        """Clean and normalize text with enhanced error handling"""
        if not text:
            return ""
        
        try:
            # Remove noise and normalize text
            text = re.sub(r'\s+', ' ', text)
            text = text.strip()
            
            # Improve formatting
            text = re.sub(r'([。！？])\s*(?=[^」』）])', r'\1\n', text)
            text = re.sub(r'([。！？])\s*\n\s*([^「『（])', r'\1\n\n\2', text)
            
            return text
        except Exception as e:
            logger.error(f"テキストクリーニングエラー: {str(e)}")
            return text

    def _get_user_friendly_error_message(self, error_msg: str) -> str:
        """Convert technical errors to user-friendly Japanese messages"""
        error_msg = error_msg.lower()
        
        # Additional context-specific error patterns
        if "memory" in error_msg:
            return "処理メモリが不足しています。テキストを短く区切って再試行してください。"
        elif "rate limit" in error_msg:
            return "API制限に達しました。しばらく待ってから再試行してください。"
        elif "invalid request" in error_msg:
            return "リクエストが無効です。入力テキストを確認して再試行してください。"
        
        # Default error categories
        for key, message in self.error_messages.items():
            if key in error_msg:
                return message
        
        return self.error_messages['unknown']

    def _improve_sentence_structure(self, text: str) -> str:
        """Improve Japanese text structure with error handling"""
        try:
            # Normalize line breaks
            text = re.sub(r'\r\n|\r|\n', '\n', text)
            
            # Improve readability
            text = re.sub(r'([。！？])\s*(?=[^」』）])', r'\1\n', text)
            text = re.sub(r'([。！？])\s*\n\s*([^「『（])', r'\1\n\n\2', text)
            
            # Fix Japanese punctuation spacing
            text = re.sub(r'\s+([。、！？」』）])', r'\1', text)
            text = re.sub(r'([「『（])\s+', r'\1', text)
            
            # Improve list formatting
            text = re.sub(r'^[-・]\s*', '• ', text, flags=re.MULTILINE)
            
            return text
            
        except Exception as e:
            logger.error(f"文章構造の改善中にエラー: {str(e)}")
            return text

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1.5, min=4, max=60),
        retry=(
            retry_if_exception_type(ConnectionError) |
            retry_if_exception_type(TimeoutError) |
            retry_if_exception_type(Exception)
        ),
        before_sleep=before_sleep_log(logger, logging.INFO),
        after=after_log(logger, logging.INFO)
    )
    def get_transcript(self, url: str) -> str:
        """Get transcript with improved error handling and retries"""
        video_id = self._extract_video_id(url)
        if not video_id:
            raise ValueError("無効なYouTube URLです")
        
        try:
            # Check cache first
            cached_transcript = self.subtitle_cache.get(video_id)
            if cached_transcript:
                logger.info("キャッシュされた字幕を使用します")
                return cached_transcript
            
            transcript = self._get_subtitles_with_priority(video_id)
            if not transcript:
                raise ValueError("字幕を取得できませんでした。動画に字幕が設定されていないか、アクセスできない可能性があります。")
            
            cleaned_transcript = self._clean_text(transcript)
            self.subtitle_cache[video_id] = cleaned_transcript
            return cleaned_transcript
            
        except Exception as e:
            error_msg = f"字幕取得エラー: {str(e)}"
            logger.error(error_msg)
            raise ValueError(error_msg)

    def _extract_video_id(self, url: str) -> Optional[str]:
        """Extract video ID from YouTube URL"""
        try:
            patterns = [
                r'(?:v=|/v/|youtu\.be/)([^&?/]+)',
                r'(?:embed/|v/)([^/?]+)',
                r'^([^/?]+)$'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, url)
                if match:
                    return match.group(1)
            return None
        except Exception as e:
            logger.error(f"Video ID抽出エラー: {str(e)}")
            return None

    def _get_subtitles_with_priority(self, video_id: str) -> Optional[str]:
        """Get subtitles with enhanced error handling and caching"""
        try:
            logger.debug(f"字幕取得を開始: video_id={video_id}")
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            logger.debug(f"TranscriptList オブジェクトの型: {type(transcript_list)}")
            
            transcript = None
            error_messages = []
            
            # Try Japanese subtitles first with detailed error logging
            for lang in ['ja', 'ja-JP']:
                try:
                    logger.debug(f"{lang}の手動作成字幕を検索中...")
                    transcript = transcript_list.find_manually_created_transcript([lang])
                    logger.info(f"{lang}の手動作成字幕が見つかりました")
                    break
                except Exception as e:
                    error_messages.append(f"{lang}の手動作成字幕の取得に失敗: {str(e)}")
                    try:
                        logger.debug(f"{lang}の自動生成字幕を検索中...")
                        transcript = transcript_list.find_generated_transcript([lang])
                        logger.info(f"{lang}の自動生成字幕が見つかりました")
                        break
                    except Exception as e:
                        error_messages.append(f"{lang}の自動生成字幕の取得に失敗: {str(e)}")

            # Fallback to English if Japanese is not available
            if not transcript:
                logger.debug("日本語字幕が見つからないため、英語字幕を検索中...")
                try:
                    transcript = transcript_list.find_manually_created_transcript(['en'])
                    logger.info("英語の手動作成字幕が見つかりました")
                except Exception as e:
                    error_messages.append(f"英語の手動作成字幕の取得に失敗: {str(e)}")
                    try:
                        transcript = transcript_list.find_generated_transcript(['en'])
                        logger.info("英語の自動生成字幕が見つかりました")
                    except Exception as e:
                        error_messages.append(f"英語の自動生成字幕の取得に失敗: {str(e)}")

            if not transcript:
                error_detail = "\n".join(error_messages)
                logger.error(f"利用可能な字幕が見つかりませんでした:\n{error_detail}")
                return None

            # Process transcript segments with improved timing and logging
            try:
                transcript_data = transcript.fetch()
                logger.debug(f"取得した字幕データの型: {type(transcript_data)}")
                
                if not isinstance(transcript_data, list):
                    raise ValueError("字幕データが予期しない形式です")
                
                # Process transcript segments with improved timing and logging
                transcript_segments = []
                current_segment = []
                current_time = 0
                
                for entry in transcript_data:
                    if not isinstance(entry, dict):
                        logger.warning(f"不正な字幕エントリ形式: {type(entry)}")
                        continue
                        
                    text = entry.get('text', '').strip()
                    start_time = entry.get('start', 0)
                    
                    # Handle time gaps and segment breaks
                    if start_time - current_time > 5:  # Gap of more than 5 seconds
                        if current_segment:
                            transcript_segments.append(' '.join(current_segment))
                            current_segment = []
                    
                    if text:
                        # Clean up text
                        text = re.sub(r'\[.*?\]', '', text)
                        text = text.strip()
                        
                        # Handle sentence endings
                        if re.search(r'[。．.！!？?]$', text):
                            current_segment.append(text)
                            transcript_segments.append(' '.join(current_segment))
                            current_segment = []
                        else:
                            current_segment.append(text)
                    
                    current_time = start_time + entry.get('duration', 0)
                
                # Add remaining segment
                if current_segment:
                    transcript_segments.append(' '.join(current_segment))

                if not transcript_segments:
                    logger.warning("有効な字幕セグメントが見つかりませんでした")
                    return None
                    
                return '\n'.join(transcript_segments)

            except Exception as e:
                logger.error(f"字幕データの処理中にエラーが発生しました: {str(e)}")
                return None

        except Exception as e:
            error_msg = f"字幕の取得に失敗しました: {str(e)}"
            logger.error(error_msg)
            return None