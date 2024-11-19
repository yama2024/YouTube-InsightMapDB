import logging
from youtube_transcript_api import YouTubeTranscriptApi
import google.generativeai as genai
import re
import os
import time
from typing import List, Optional, Dict, Any, Tuple
from retrying import retry
from cachetools import TTLCache, cached
import json
from datetime import datetime, timedelta
from queue import Queue
from threading import Lock

# Enhanced logging setup
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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
        self.summary_cache = TTLCache(maxsize=100, ttl=3600)  # 1 hour TTL for summaries
        
        # Rate limiting and request tracking
        self.request_counter = 0
        self.last_request_time = datetime.now()
        self.failed_attempts = 0
        self.last_reset_time = datetime.now()
        self.reset_interval = timedelta(minutes=5)  # Reset counters every 5 minutes
        
        # Request queue management
        self.request_queue = Queue()
        self.max_concurrent_requests = 3
        self.request_lock = Lock()
        self.active_requests = 0
        
        # Maximum chunk size for text processing (in characters)
        self.max_chunk_size = 8000
        
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

    def _manage_request_limits(self):
        """Manage API request limits and implement adaptive backoff"""
        current_time = datetime.now()
        
        # Reset counters if reset interval has passed
        if current_time - self.last_reset_time > self.reset_interval:
            logger.info("Resetting rate limit counters")
            self.request_counter = 0
            self.failed_attempts = 0
            self.last_reset_time = current_time
        
        # Increase base delay and add progressive backoff
        base_delay = 2.0  # Increased from 1.0
        if self.request_counter > 0:
            delay = base_delay * (1 + (self.request_counter * 0.5))
            time.sleep(delay)
        
        # Update request tracking
        self.request_counter += 1
        self.last_request_time = current_time
        
        # Log request statistics
        logger.debug(f"Request counter: {self.request_counter}, Failed attempts: {self.failed_attempts}")

    def _calculate_backoff_time(self, attempt: int) -> float:
        """Calculate adaptive backoff time based on failure history"""
        base_backoff = min(120, (2 ** attempt) * 15)  # Increased values
        
        # Increase backoff if there have been multiple failures
        if self.failed_attempts > 2:
            base_backoff *= (1 + (self.failed_attempts * 0.75))  # Increased multiplier
        
        return min(300, base_backoff)  # Cap at 5 minutes

    def _process_request_queue(self):
        """Process requests in the queue with rate limiting"""
        with self.request_lock:
            if self.active_requests >= self.max_concurrent_requests:
                return False
            self.active_requests += 1
        
        try:
            while not self.request_queue.empty():
                request_data = self.request_queue.get()
                chunk = request_data['chunk']
                chunk_index = request_data['index']
                total_chunks = request_data['total']
                
                # Manage request limits
                self._manage_request_limits()
                
                # Generate summary for this chunk
                response = self.model.generate_content(
                    self._create_summary_prompt(chunk, chunk_index, total_chunks)
                )
                
                if not response or not response.text:
                    raise ValueError("AIモデルからの応答が空でした")
                
                self.request_queue.task_done()
                return response.text.strip()
                
        finally:
            with self.request_lock:
                self.active_requests -= 1

    def generate_summary(self, text: str) -> str:
        """Generate a summary with enhanced rate limit handling and error reporting"""
        logger.info("要約生成を開始します")
        
        try:
            # Input validation
            is_valid, error_msg = self._validate_text(text)
            if not is_valid:
                raise ValueError(f"入力テキストが無効です: {error_msg}")
            
            # Check cache first
            cache_key = hash(text)
            cached_summary = self.summary_cache.get(cache_key)
            if cached_summary:
                logger.info("キャッシュされた要約を使用します")
                return cached_summary
            
            # Clean and chunk the text
            cleaned_text = self._clean_text(text)
            text_chunks = self._chunk_text(cleaned_text)
            logger.info(f"テキストを{len(text_chunks)}チャンクに分割しました")
            
            chunk_summaries = []
            max_retries = 5  # Increased from 3 to 5
            
            # Add all chunks to request queue
            for i, chunk in enumerate(text_chunks):
                self.request_queue.put({
                    'chunk': chunk,
                    'index': i,
                    'total': len(text_chunks)
                })
            
            # Process chunks with queuing and rate limiting
            for i in range(len(text_chunks)):
                logger.info(f"チャンク {i+1}/{len(text_chunks)} の処理を開始")
                
                for attempt in range(max_retries):
                    try:
                        summary = self._process_request_queue()
                        if summary:
                            chunk_summaries.append(summary)
                            # Reset failed attempts counter on success
                            self.failed_attempts = 0
                            # Add delay between chunk processing
                            time.sleep(2.0)  # Base delay between chunks
                            break
                        
                    except Exception as e:
                        self.failed_attempts += 1
                        wait_time = self._calculate_backoff_time(attempt)
                        
                        if "429" in str(e) or "Resource has been exhausted" in str(e):
                            error_msg = f"API制限に達しました。待機時間: {wait_time}秒"
                            logger.error(f"{error_msg}: {str(e)}")
                            if attempt < max_retries - 1:
                                logger.info(f"待機中... {wait_time}秒後に再試行 ({attempt + 1}/{max_retries})")
                                time.sleep(wait_time)
                            else:
                                raise ValueError(f"{error_msg}。しばらく待ってから再試行してください。")
                        else:
                            logger.warning(f"生成エラー (試行 {attempt + 1}/{max_retries}): {str(e)}")
                            if attempt == max_retries - 1:
                                raise ValueError(f"要約の生成に失敗しました: {str(e)}")
                            logger.info(f"待機中... {wait_time}秒後に再試行")
                            time.sleep(wait_time)
            
            # Combine chunk summaries
            if chunk_summaries:
                combined_summary = self._combine_summaries(chunk_summaries)
                self.summary_cache[cache_key] = combined_summary
                logger.info("要約の生成が正常に完了しました")
                return combined_summary
            else:
                raise ValueError("チャンクの要約生成に失敗しました")
                
        except Exception as e:
            error_msg = f"要約生成中にエラーが発生しました: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)

    def _create_summary_prompt(self, chunk: str, chunk_index: int, total_chunks: int) -> str:
        """Create a prompt for summary generation"""
        return f"""
        # 目的と背景
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

    def _combine_summaries(self, chunk_summaries: List[str]) -> str:
        """Combine multiple chunk summaries into a coherent final summary"""
        if not chunk_summaries:
            return ""

        try:
            combine_prompt = f"""
            # 目的
            複数のテキストチャンクの要約を1つの包括的な要約にまとめます。

            # 出力フォーマット
            以下の構造で最終的な要約を作成してください：

            # 概要
            [全体の要点を2-3文で簡潔に説明]

            ## 主なポイント
            • [重要なポイント1 - 具体的な例や数値を含める]
            • [重要なポイント2 - 技術用語がある場合は説明を付記]
            • [重要なポイント3 - 実践的な示唆や応用点を含める]

            ## 詳細な解説
            [本文の詳細な解説]

            ## まとめ
            [主要な発見や示唆を1-2文で結論付け]

            # 入力テキスト（チャンク要約）：
            {' '.join(chunk_summaries)}
            """

            for attempt in range(3):
                try:
                    response = self.model.generate_content(combine_prompt)
                    if not response or not response.text:
                        raise ValueError("AIモデルからの応答が空でした")
                    
                    final_summary = response.text.strip()
                    is_valid, error_msg = self._validate_summary_response(final_summary)
                    if not is_valid:
                        raise ValueError(f"生成された要約が無効です: {error_msg}")
                    
                    return final_summary

                except Exception as e:
                    if "429" in str(e) or "Resource has been exhausted" in str(e):
                        logger.error(f"API制限に達しました: {str(e)}")
                        wait_time = self._calculate_backoff_time(attempt)
                        time.sleep(wait_time)
                        if attempt == 2:
                            raise ValueError("API制限に達しました。しばらく待ってから再試行してください。")
                    else:
                        logger.warning(f"要約の結合中にエラーが発生 (試行 {attempt + 1}/3): {str(e)}")
                        if attempt == 2:
                            raise
                        wait_time = self._calculate_backoff_time(attempt)
                        time.sleep(wait_time)

        except Exception as e:
            logger.error(f"要約の結合中にエラーが発生しました: {str(e)}")
            raise ValueError(f"要約の結合に失敗しました: {str(e)}")

    def _validate_text(self, text: str) -> Tuple[bool, str]:
        """Validate input text and return validation status and error message"""
        try:
            if not text:
                return False, "入力テキストが空です"
            
            # Check minimum length (100 characters)
            if len(text) < 100:
                return False, "テキストが短すぎます（最小100文字必要）"
            
            # Validate text encoding
            try:
                text.encode('utf-8').decode('utf-8')
            except UnicodeError:
                return False, "テキストのエンコーディングが無効です"
            
            # Check for excessive noise or invalid patterns
            noise_ratio = len(re.findall(r'[^\w\s。、！？」』）「『（]', text)) / len(text)
            if noise_ratio > 0.3:  # More than 30% noise characters
                return False, "テキストにノイズが多すぎます"
            
            return True, ""
            
        except Exception as e:
            logger.error(f"テキスト検証中にエラーが発生: {str(e)}")
            return False, f"テキスト検証エラー: {str(e)}"

    def _validate_summary_response(self, response: str) -> Tuple[bool, str]:
        """Validate the generated summary response"""
        try:
            if not response:
                return False, "生成された要約が空です"
            
            # Check for required sections
            required_sections = ['概要', '主なポイント', '詳細な解説', 'まとめ']
            for section in required_sections:
                if section not in response:
                    return False, f"必要なセクション '{section}' が見つかりません"
            
            # Check for minimum content length in each section
            sections_content = re.split(r'#{1,2}\s+(?:概要|主なポイント|詳細な解説|まとめ)', response)
            if any(len(section.strip()) < 50 for section in sections_content[1:]):
                return False, "一部のセクションの内容が不十分です"
            
            # Verify bullet points in main points section
            main_points_match = re.search(r'##\s*主なポイント\n(.*?)(?=##|$)', response, re.DOTALL)
            if main_points_match:
                main_points = main_points_match.group(1)
                if len(re.findall(r'•|\*|\-', main_points)) < 2:
                    return False, "主なポイントの箇条書きが不十分です"
            
            return True, ""
            
        except Exception as e:
            logger.error(f"要約の検証中にエラーが発生: {str(e)}")
            return False, f"要約の検証エラー: {str(e)}"

    def _chunk_text(self, text: str) -> List[str]:
        """Split text into manageable chunks"""
        sentences = re.split(r'([。！？])', text)
        chunks = []
        current_chunk = ""
        
        for i in range(0, len(sentences), 2):
            sentence = sentences[i] + (sentences[i+1] if i+1 < len(sentences) else '')
            if len(current_chunk) + len(sentence) <= self.max_chunk_size:
                current_chunk += sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = sentence
        
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks

    def _clean_text(self, text: str) -> str:
        """Clean and normalize text"""
        if not text:
            return text
            
        cleaned_text = text
        
        # Apply noise pattern removal
        for pattern_name, pattern in self.noise_patterns.items():
            cleaned_text = re.sub(pattern, ' ', cleaned_text)
        
        # Apply Japanese text normalization
        for category, replacements in self.jp_normalization.items():
            for old, new in replacements.items():
                cleaned_text = cleaned_text.replace(old, new)
        
        # Remove extra whitespace
        cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
        
        return cleaned_text

    def get_transcript(self, url: str) -> str:
        """Get transcript from YouTube video"""
        try:
            video_id = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', url)
            if not video_id:
                raise ValueError("無効なYouTube URLです")
            
            video_id = video_id.group(1)
            
            # Check cache
            if video_id in self.subtitle_cache:
                return self.subtitle_cache[video_id]
            
            # Get transcript
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['ja', 'en'])
            
            # Combine transcript texts
            transcript_text = ' '.join([entry['text'] for entry in transcript_list])
            
            # Clean transcript
            cleaned_transcript = self._clean_text(transcript_text)
            
            # Cache result
            self.subtitle_cache[video_id] = cleaned_transcript
            
            return cleaned_transcript
            
        except Exception as e:
            logger.error(f"文字起こしの取得に失敗しました: {str(e)}")
            raise Exception(f"文字起こしの取得に失敗しました: {str(e)}")
