import logging
from youtube_transcript_api import YouTubeTranscriptApi
import google.generativeai as genai
import re
import os
import time
from typing import List, Optional, Dict, Any, Tuple, Callable
from cachetools import TTLCache, cached
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
    RetryError
)

# Enhanced logging setup
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
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

class TextProcessor:
    def __init__(self):
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("Gemini API key is not set in environment variables")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-1.5-pro')
        
        # Initialize caches
        self.subtitle_cache = TTLCache(maxsize=100, ttl=3600)  # 1 hour TTL
        self.processed_text_cache = TTLCache(maxsize=100, ttl=1800)  # 30 minutes TTL
        
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
        
        # Japanese text normalization
        self.jp_normalization = {
            'spaces': {
                '　': ' ',
                '\u3000': ' ',
                '\xa0': ' '
            },
            'punctuation': {
                '．': '。',
                '…': '。',
                '.': '。',
                '｡': '。',
                '､': '、'
            }
        }

    def _clean_text(self, text: str, progress_callback: Optional[Callable] = None) -> str:
        """Enhanced text cleaning with progress tracking"""
        if not text:
            return ""
        
        try:
            total_steps = len(self.jp_normalization) + len(self.noise_patterns) + 1
            current_step = 0
            
            # Normalize Japanese text
            for category, replacements in self.jp_normalization.items():
                for old, new in replacements.items():
                    text = text.replace(old, new)
                current_step += 1
                if progress_callback:
                    progress_callback(current_step / total_steps, f"正規化処理中: {category}")
            
            # Remove noise patterns
            for pattern_name, pattern in self.noise_patterns.items():
                text = re.sub(pattern, '', text)
                current_step += 1
                if progress_callback:
                    progress_callback(current_step / total_steps, f"ノイズ除去中: {pattern_name}")
            
            # Improve sentence structure
            text = self._improve_sentence_structure(text)
            current_step += 1
            if progress_callback:
                progress_callback(1.0, "文章構造の最適化完了")
            
            return text
            
        except Exception as e:
            logger.error(f"テキストのクリーニング中にエラーが発生しました: {str(e)}")
            return text

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1.5, min=4, max=60),
        retry=(
            retry_if_exception_type(ConnectionError) |
            retry_if_exception_type(TimeoutError) |
            retry_if_exception_type(APIError)
        ),
        before_sleep=before_sleep_log(logger, logging.INFO)
    )
    def generate_summary(self, text: str, progress_callback: Optional[Callable] = None) -> str:
        """Generate AI summary with enhanced error handling and retry mechanism"""
        if not text:
            raise InvalidInputError("入力テキストが空です")
            
        try:
            if progress_callback:
                progress_callback(0.1, "🔍 テキスト解析を開始しています")
            
            prompt = f"""
# あなたの目的:
入力されたテキストの包括的な要約を生成してください。

# ルール:
1. 要約は以下の構造で作成:
   - 概要（全体の要点）
   - 主要なポイント（箇条書き）
   - 詳細な分析（重要なトピックごと）
   - 結論

2. フォーマット:
   - Markdown形式で出力
   - 見出しは適切なレベルで
   - 重要なポイントは強調
   - 箇条書きを効果的に使用

入力テキスト:
{text}
"""
            
            if progress_callback:
                progress_callback(0.3, "🤖 AI分析を実行中...")
            
            try:
                # Set timeout and validate response
                start_time = time.time()
                response = self.model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.3,
                        top_p=0.8,
                        top_k=40,
                        max_output_tokens=8192,
                    ),
                    timeout=120  # 2 minutes timeout
                )
                
                if not response.text:
                    raise APIError("AIモデルからの応答が空です")
                
                processing_time = time.time() - start_time
                logger.info(f"AI生成完了 (処理時間: {processing_time:.2f}秒)")
                
                if progress_callback:
                    progress_callback(0.7, "📝 要約を整形中...")
                
                summary = response.text
                
                # Post-processing with error handling
                try:
                    summary = self._clean_text(summary)
                    summary = self._improve_sentence_structure(summary)
                except Exception as e:
                    logger.warning(f"要約の後処理中に警告: {str(e)}")
                
                if progress_callback:
                    progress_callback(1.0, "✨ 要約が完了しました")
                
                return summary
                
            except Exception as e:
                error_msg = str(e).lower()
                if "timeout" in error_msg:
                    raise TimeoutError("API応答がタイムアウトしました")
                elif "quota" in error_msg:
                    raise QuotaExceededError("API利用制限に達しました")
                elif "connection" in error_msg:
                    raise ConnectionError("API接続エラーが発生しました")
                else:
                    raise APIError(f"AI生成中にエラーが発生: {str(e)}")
                
        except RetryError as e:
            logger.error(f"リトライ後も要約生成に失敗: {str(e)}")
            if progress_callback:
                progress_callback(1.0, "❌ 要約生成に失敗しました")
            raise APIError("複数回の試行後も要約の生成に失敗しました。しばらく待ってから再度お試しください。")
            
        except Exception as e:
            logger.error(f"要約処理中に重大なエラーが発生: {str(e)}")
            if progress_callback:
                progress_callback(1.0, "❌ 致命的なエラーが発生しました")
            raise APIError(f"要約処理エラー: {self._get_user_friendly_error_message(str(e))}")

    def _improve_sentence_structure(self, text: str) -> str:
        """Improve Japanese sentence structure and readability"""
        try:
            # Fix sentence endings
            text = re.sub(r'([。！？])\s*(?=[^」』）])', r'\1\n', text)
            
            # Improve paragraph breaks
            text = re.sub(r'([。！？])\s*\n\s*([^「『（])', r'\1\n\n\2', text)
            
            # Fix spacing around Japanese punctuation
            text = re.sub(r'\s+([。、！？」』）])', r'\1', text)
            text = re.sub(r'([「『（])\s+', r'\1', text)
            
            # Clean up list items
            text = re.sub(r'^[-・]\s*', '• ', text, flags=re.MULTILINE)
            
            return text
        except Exception as e:
            logger.error(f"文章構造の改善中にエラーが発生しました: {str(e)}")
            return text

    def _get_user_friendly_error_message(self, error_msg: str) -> str:
        """Convert technical error messages to user-friendly messages"""
        error_map = {
            'connection': "ネットワーク接続に問題が発生しました。インターネット接続を確認してください。",
            'timeout': "応答待ちタイムアウトが発生しました。しばらく待ってから再試行してください。",
            'quota': "API利用制限に達しました。しばらく待ってから再度お試しください。",
            'invalid': "入力データが無効です。テキストを確認して再試行してください。",
            'empty': "AIモデルからの応答が空でした。別の入力テキストで試してください。"
        }
        
        error_msg = error_msg.lower()
        for key, message in error_map.items():
            if key in error_msg:
                return message
                
        return "予期せぬエラーが発生しました。システム管理者に連絡してください。"

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, Exception))
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