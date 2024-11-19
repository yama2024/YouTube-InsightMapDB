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
        self.max_chunk_size = 4000  # Reduced from 8000
        self.chunk_overlap = 500    # Added overlap between chunks
        
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
        """Manage API request limits with enhanced logging and exponential backoff"""
        current_time = datetime.now()
        
        # Increase base delay and add progressive backoff
        base_delay = 5.0  # Increased base delay
        if self.request_counter > 0:
            # Exponential backoff with progressive increase
            delay = base_delay * (2 ** (self.request_counter // 3))
            time.sleep(delay)
        
        # Reset counters more frequently
        if current_time - self.last_reset_time > timedelta(minutes=2):
            self.request_counter = 0
            self.failed_attempts = 0
            self.last_reset_time = current_time
        
        # Update request tracking
        self.request_counter += 1
        self.last_request_time = current_time
        
        # Enhanced logging
        logger.info(
            f"Request stats - Counter: {self.request_counter}, "
            f"Failed attempts: {self.failed_attempts}, "
            f"Time since last reset: {(current_time - self.last_reset_time).seconds}s"
        )

    def _calculate_backoff_time(self, attempt: int) -> float:
        """Calculate adaptive backoff time based on failure history"""
        base_backoff = min(120, (2 ** attempt) * 15)  # Increased values
        
        # Increase backoff if there have been multiple failures
        if self.failed_attempts > 2:
            base_backoff *= (1 + (self.failed_attempts * 0.75))  # Increased multiplier
        
        return min(300, base_backoff)  # Cap at 5 minutes

    def _process_request_queue(self):
        """Process requests in the queue with enhanced error handling and batch processing"""
        with self.request_lock:
            if self.active_requests >= self.max_concurrent_requests:
                logger.info(f"Active requests at limit ({self.active_requests}/{self.max_concurrent_requests})")
                time.sleep(2)
                return None
            self.active_requests += 1
        
        try:
            batch_size = min(3, self.request_queue.qsize())  # Process up to 3 requests at once
            if batch_size == 0:
                return None
            
            logger.info(f"Processing batch of {batch_size} requests")
            batch_results = []
            
            for _ in range(batch_size):
                if self.request_queue.empty():
                    break
                    
                request_data = self.request_queue.get()
                chunk_key = f"chunk_{request_data['index']}"
                
                # Check cache for this chunk
                if chunk_key in self.processed_text_cache:
                    logger.info(f"Using cached result for chunk {request_data['index'] + 1}")
                    batch_results.append(self.processed_text_cache[chunk_key])
                    continue
                
                try:
                    # Enhanced request handling with timeouts and retries
                    for attempt in range(3):
                        try:
                            self._manage_request_limits()
                            
                            response = self.model.generate_content(
                                self._create_summary_prompt(
                                    request_data['chunk'],
                                    request_data['index'],
                                    request_data['total']
                                )
                            )
                            
                            if not response or not response.text:
                                raise ValueError("Empty response from AI model")
                            
                            result = response.text.strip()
                            # Cache successful result
                            self.processed_text_cache[chunk_key] = result
                            batch_results.append(result)
                            break
                            
                        except Exception as e:
                            if "429" in str(e):
                                logger.error(f"Rate limit reached on attempt {attempt + 1}")
                                wait_time = self._calculate_backoff_time(attempt)
                                time.sleep(wait_time)
                            elif "timeout" in str(e).lower():
                                logger.error(f"Request timeout on attempt {attempt + 1}")
                                time.sleep(5 * (attempt + 1))
                            else:
                                logger.error(f"Error processing chunk: {str(e)}")
                                if attempt == 2:
                                    raise
                                time.sleep(3 * (attempt + 1))
                    
                except Exception as e:
                    logger.error(f"Failed to process chunk after all retries: {str(e)}")
                    self.failed_attempts += 1
                    raise
                
                finally:
                    self.request_queue.task_done()
            
            return batch_results[0] if batch_results else None
            
        finally:
            with self.request_lock:
                self.active_requests -= 1
                logger.debug(f"Active requests decreased to {self.active_requests}")

    def generate_summary(self, text: str) -> str:
        """Generate a summary with enhanced error handling and logging"""
        logger.info("Starting summary generation process")
        
        try:
            # Input validation with detailed logging
            is_valid, error_msg = self._validate_text(text)
            if not is_valid:
                logger.error(f"Input text validation failed: {error_msg}")
                raise ValueError(f"入力テキストが無効です: {error_msg}")
            
            # Check cache with logging
            cache_key = hash(text)
            cached_summary = self.summary_cache.get(cache_key)
            if cached_summary:
                logger.info("Using cached summary")
                return cached_summary
            
            # Clean and chunk the text with improved size calculation
            cleaned_text = self._clean_text(text)
            text_chunks = self._chunk_text(cleaned_text)
            logger.info(f"Text split into {len(text_chunks)} chunks (avg size: {sum(len(c) for c in text_chunks)/len(text_chunks):.0f} chars)")
            
            chunk_summaries = []
            max_retries = 5
            
            # Add all chunks to request queue with logging
            for i, chunk in enumerate(text_chunks):
                logger.info(f"Queuing chunk {i+1}/{len(text_chunks)} (size: {len(chunk)} chars)")
                self.request_queue.put({
                    'chunk': chunk,
                    'index': i,
                    'total': len(text_chunks)
                })
            
            # Process chunks with enhanced error handling
            for i in range(len(text_chunks)):
                logger.info(f"Processing chunk {i+1}/{len(text_chunks)}")
                
                for attempt in range(max_retries):
                    try:
                        summary = self._process_request_queue()
                        if summary:
                            chunk_summaries.append(summary)
                            logger.info(f"Successfully processed chunk {i+1}/{len(text_chunks)}")
                            self.failed_attempts = 0
                            time.sleep(2.0)  # Base delay between chunks
                            break
                        
                    except Exception as e:
                        self.failed_attempts += 1
                        wait_time = self._calculate_backoff_time(attempt)
                        
                        if "429" in str(e) or "Resource has been exhausted" in str(e):
                            error_msg = f"Rate limit reached. Waiting {wait_time} seconds"
                            logger.error(f"{error_msg}: {str(e)}")
                            if attempt < max_retries - 1:
                                logger.info(f"Retrying in {wait_time} seconds (attempt {attempt + 1}/{max_retries})")
                                time.sleep(wait_time)
                            else:
                                raise ValueError(f"{error_msg}. Please try again later.")
                        else:
                            logger.error(f"Error processing chunk {i+1} (attempt {attempt + 1}/{max_retries}): {str(e)}")
                            if attempt == max_retries - 1:
                                raise ValueError(f"Failed to generate summary: {str(e)}")
                            logger.info(f"Retrying in {wait_time} seconds")
                            time.sleep(wait_time)
            
            # Combine summaries with validation
            if chunk_summaries:
                logger.info("Combining chunk summaries")
                combined_summary = self._combine_summaries(chunk_summaries)
                if not combined_summary:
                    raise ValueError("Failed to combine chunk summaries")
                
                self.summary_cache[cache_key] = combined_summary
                logger.info("Successfully generated and cached summary")
                return combined_summary
            else:
                raise ValueError("No chunk summaries generated")
                
        except Exception as e:
            error_msg = f"Summary generation failed: {str(e)}"
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
                        raise ValueError("Empty response from AI model")
                    
                    final_summary = response.text.strip()
                    is_valid, error_msg = self._validate_summary_response(final_summary)
                    if not is_valid:
                        raise ValueError(f"Generated summary is invalid: {error_msg}")
                    
                    return final_summary

                except Exception as e:
                    if "429" in str(e) or "Resource has been exhausted" in str(e):
                        logger.error(f"Rate limit reached: {str(e)}")
                        wait_time = self._calculate_backoff_time(attempt)
                        time.sleep(wait_time)
                        if attempt == 2:
                            raise ValueError("Rate limit reached. Please try again later.")
                    else:
                        logger.warning(f"Error combining summaries (attempt {attempt + 1}/3): {str(e)}")
                        if attempt == 2:
                            raise
                        wait_time = self._calculate_backoff_time(attempt)
                        time.sleep(wait_time)

            return ""  # Return empty string if all attempts fail

        except Exception as e:
            logger.error(f"Error combining summaries: {str(e)}")
            raise ValueError(f"Failed to combine summaries: {str(e)}")

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
            logger.error(f"Error validating text: {str(e)}")
            return False, f"Text validation error: {str(e)}"

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
            logger.error(f"Error validating summary: {str(e)}")
            return False, f"Summary validation error: {str(e)}"

    def _chunk_text(self, text: str) -> List[str]:
        """Split text into manageable chunks with overlap and smart sentence boundaries"""
        if not text:
            return []
        
        logger.info("Starting text chunking process")
        
        # Split text into sentences using Japanese-aware sentence boundaries
        sentences = re.split(r'([。！？])', text)
        chunks = []
        current_chunk = ""
        last_sentence = ""  # Store the last sentence for overlap
        
        for i in range(0, len(sentences), 2):
            sentence = sentences[i] + (sentences[i+1] if i+1 < len(sentences) else '')
            
            # Calculate sizes including potential overlap
            current_size = len(current_chunk)
            sentence_size = len(sentence)
            
            if current_size + sentence_size <= self.max_chunk_size:
                current_chunk += sentence
            else:
                if current_chunk:
                    # Add the chunk with overlap from previous chunk if available
                    if chunks and last_sentence:
                        overlap_text = last_sentence + current_chunk
                        chunks.append(overlap_text)
                    else:
                        chunks.append(current_chunk)
                    
                    # Store last sentence for next chunk's overlap
                    sentences_in_chunk = re.split(r'([。！？])', current_chunk)
                    last_sentence = sentences_in_chunk[-2] + sentences_in_chunk[-1] if len(sentences_in_chunk) > 1 else ""
                    
                    logger.debug(f"Created chunk of size {len(current_chunk)} characters with {len(last_sentence)} overlap")
                current_chunk = sentence
        
        # Add the final chunk
        if current_chunk:
            if chunks and last_sentence:
                overlap_text = last_sentence + current_chunk
                chunks.append(overlap_text)
            else:
                chunks.append(current_chunk)
            logger.debug(f"Added final chunk of size {len(current_chunk)} characters")
        
        logger.info(f"Split text into {len(chunks)} chunks with overlap")
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