import logging
from youtube_transcript_api import YouTubeTranscriptApi
import google.generativeai as genai
import re
import os
import time
import random
from typing import List, Optional, Dict, Any, Tuple, Callable
from retrying import retry
from cachetools import TTLCache, cached
from concurrent.futures import ThreadPoolExecutor, as_completed

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
        self.safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
        
        # Enhanced caching with separate caches for different operations
        self.subtitle_cache = TTLCache(maxsize=100, ttl=3600)  # 1 hour TTL
        self.summary_cache = TTLCache(maxsize=50, ttl=1800)    # 30 minutes TTL
        self.chunk_cache = TTLCache(maxsize=200, ttl=900)      # 15 minutes TTL
        
        # Rate limiting settings
        self.request_timestamps = []
        self.max_requests_per_minute = 50
        self.min_request_interval = 1.2  # seconds

        # Japanese text normalization patterns
        self.jp_normalization = {
            'brackets': {
                '「': '', '」': '', '『': '', '』': '',
                '（': '', '）': '', '【': '', '】': ''
            },
            'punctuation': {
                '、': ' ', '，': ' ',
                '。': '. ', '．': '. '
            }
        }
        
        # Initialize noise patterns
        self._init_noise_patterns()

    def _preprocess_text(self, text: str) -> str:
        """Preprocess text with enhanced normalization"""
        # Remove noise patterns
        for pattern in self.noise_patterns.values():
            text = re.sub(pattern, ' ', text)
            
        # Apply Japanese text normalization
        for brackets in self.jp_normalization['brackets'].items():
            text = text.replace(brackets[0], brackets[1])
        for punct in self.jp_normalization['punctuation'].items():
            text = text.replace(punct[0], punct[1])
            
        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _chunk_text(self, text: str, chunk_size: int = 800, overlap: int = 100) -> List[str]:
        # 入力検証の強化
        if not text or len(text.strip()) < 200:
            raise ValueError("入力テキストが短すぎます（最小200文字必要）")
        
        # 文章の前処理
        text = self._preprocess_text(text)
        
        # 文単位での分割
        sentences = re.split('([。!?！？]+)', text)
        sentences = [''.join(i) for i in zip(sentences[0::2], sentences[1::2])]
        
        chunks = []
        current_chunk = []
        current_length = 0
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
                
            # チャンクサイズの動的調整
            if current_length + len(sentence) > chunk_size and current_chunk:
                chunk_text = ' '.join(current_chunk)
                if len(chunk_text) >= 200:
                    chunks.append(chunk_text)
                # オーバーラップの処理
                overlap_text = ' '.join(current_chunk[-2:])  # 最後の2文を保持
                current_chunk = [overlap_text] if overlap_text else []
                current_length = len(overlap_text) if overlap_text else 0
            
            current_chunk.append(sentence)
            current_length += len(sentence)
        
        # 残りのテキストの処理
        if current_chunk:
            final_chunk = ' '.join(current_chunk)
            if len(final_chunk) >= 200:
                chunks.append(final_chunk)
        
        # チャンクの検証
        if not chunks:
            raise ValueError("有効なチャンクを生成できませんでした")
        
        return chunks

    def _generate_chunk_summary(self, chunk: str) -> str:
        prompt = f'''
        以下のテキストチャンクを要約してください：
        
        要件：
        1. 重要な情報を保持
        2. 文脈を維持
        3. 簡潔で分かりやすい表現
        4. 前後のチャンクとの一貫性を考慮
        
        テキスト：
        {chunk}
        '''
        
        response = self.model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.3,
                top_p=0.8,
                top_k=40,
                max_output_tokens=400
            )
        )
        
        if not response or not response.text:
            raise ValueError("要約の生成に失敗しました")
        
        return response.text.strip()

    def _init_noise_patterns(self):
        """Initialize enhanced noise patterns for better text cleaning"""
        self.noise_patterns = {
            'timestamps': r'\[?\(?\d{1,2}:\d{2}(?::\d{2})?\]?\)?',
            'speaker_tags': r'\[[^\]]*\]|\([^)]*\)',
            'filler_words': r'\b(えーと|えっと|えー|あの|あのー|まぁ|んー|そのー|なんか|こう|ね|ねぇ|さぁ|うーん|あー|そうですね|ちょっと)\b',
            'repeated_chars': r'([^\W\d_])\1{3,}',
            'multiple_spaces': r'[\s　]{2,}',
            'empty_lines': r'\n\s*\n',
            'punctuation': r'([。．！？])\1+',
            'noise_symbols': r'[♪♫♬♩†‡◊◆◇■□▲△▼▽○●◎]',
            'unnecessary_symbols': r'[＊∗※#＃★☆►▷◁◀→←↑↓]'
        }

    def _enforce_rate_limit(self):
        """Enhanced rate limiting with dynamic adjustment"""
        current_time = time.time()
        self.request_timestamps = [ts for ts in self.request_timestamps 
                                 if current_time - ts < 60]
        
        if len(self.request_timestamps) >= self.max_requests_per_minute:
            sleep_time = 60 - (current_time - self.request_timestamps[0]) + 1
            logger.warning(f"Rate limit reached, waiting {sleep_time:.2f} seconds")
            time.sleep(sleep_time)
        
        time_since_last_request = (current_time - self.request_timestamps[-1] 
                                 if self.request_timestamps else float('inf'))
        if time_since_last_request < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last_request)
        
        self.request_timestamps.append(time.time())

    def generate_summary(self, text: str, chunk_size: int = 800) -> str:
        """Generate a summary with improved quality and performance"""
        try:
            # Input validation
            if not text or len(text.strip()) < 200:
                raise ValueError("入力テキストが短すぎます（最小200文字必要）")

            # Cache check
            cache_key = hash(text)
            cached_summary = self.summary_cache.get(cache_key)
            if cached_summary:
                logger.info("キャッシュされた要約を使用します")
                return cached_summary

            # Process text in chunks
            chunks = self._chunk_text(text, chunk_size=chunk_size)
            summaries = []

            # Process chunks with parallel execution
            with ThreadPoolExecutor(max_workers=3) as executor:
                future_to_chunk = {executor.submit(self._generate_chunk_summary, chunk): i 
                                 for i, chunk in enumerate(chunks)}
                
                for future in as_completed(future_to_chunk):
                    try:
                        chunk_summary = future.result()
                        if chunk_summary:
                            summaries.append((future_to_chunk[future], chunk_summary))
                    except Exception as e:
                        logger.error(f"チャンク処理エラー: {str(e)}")

            if not summaries:
                raise ValueError("要約の生成に失敗しました")

            # Sort summaries by original chunk order
            summaries.sort(key=lambda x: x[0])
            final_text = "\n".join([summary for _, summary in summaries])

            # Generate final summary
            final_summary = self._generate_chunk_summary(final_text)
            if not final_summary:
                raise ValueError("最終要約の生成に失敗しました")

            # Cache the result
            self.summary_cache[cache_key] = final_summary
            return final_summary

        except Exception as e:
            error_msg = f"要約生成エラー: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)

    @retry(stop_max_attempt_number=3, wait_fixed=2000)
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
            
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['ja', 'ja-JP', 'en'])
            transcript = ' '.join([entry['text'] for entry in transcript_list])
            
            cleaned_transcript = self._preprocess_text(transcript)
            self.subtitle_cache[video_id] = cleaned_transcript
            return cleaned_transcript
            
        except Exception as e:
            error_msg = f"字幕取得エラー: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)

    def _extract_video_id(self, url: str) -> Optional[str]:
        """Extract YouTube video ID from URL"""
        patterns = [
            r'(?:v=|\/videos\/|embed\/|youtu.be\/|\/v\/|\/e\/|watch\?v%3D|watch\?feature=player_embedded&v=|%2Fvideos%2F|embed%\u200C\u200B2F|youtu.be%2F|%2Fv%2F)([^#\&\?\n]*)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def _validate_input_text(self, text: str) -> bool:
        """Validate input text length and content"""
        if not text:
            raise ValueError("入力テキストが空です")
        
        text = text.strip()
        if len(text) < 100:
            raise ValueError("入力テキストが短すぎます（最小100文字必要）")
            
        # Check for meaningful content
        normalized_text = ''.join(text.split())
        if len(normalized_text) < 50:
            raise ValueError("有効なテキストコンテンツが不足しています（実質的な内容が50文字未満）")
            
        return True

    def _clean_text(self, text: str, progress_callback=None) -> str:
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
            
            return text.strip()
            
        except Exception as e:
            logger.error(f"文章構造の改善中にエラーが発生しました: {str(e)}")
            return text

    def proofread_text(self, text: str, progress_callback=None) -> str:
        """Proofread and enhance text readability with progress tracking"""
        if not text:
            return ""
            
        try:
            if progress_callback:
                progress_callback(0.1, "🔍 テキスト解析を開始")
            
            # Initial text cleaning with detailed progress
            cleaning_steps = {
                0.15: "📝 フィラーワードを除去中...",
                0.20: "🔤 文字の正規化を実行中...",
                0.25: "📊 タイムスタンプを処理中...",
                0.30: "✨ 不要な記号を削除中..."
            }
            
            for progress, message in cleaning_steps.items():
                if progress_callback:
                    progress_callback(progress, message)
                time.sleep(0.3)  # Visual feedback
            
            text = self._clean_text(text, lambda p, m: progress_callback(0.3 + p * 0.2, m) if progress_callback else None)
            
            if progress_callback:
                progress_callback(0.5, "🤖 AIモデルによる文章校正を準備中...")
            
            # AI Processing with safety settings
            prompt = f"""
            以下のテキストを校閲し、文章を整形してください：
            
            {text}
            """
            
            response = self.model.generate_content(
                prompt,
                safety_settings=self.safety_settings,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.3,
                    top_p=0.8,
                    top_k=40,
                    max_output_tokens=1024,
                )
            )
            
            if not response or not response.text:
                logger.error("AIモデルからの応答が空でした")
                if progress_callback:
                    progress_callback(1.0, "❌ エラー: AIモデルからの応答が空です")
                return text
            
            enhanced_text = response.text.strip()
            enhanced_text = self._clean_text(enhanced_text)
            enhanced_text = self._improve_sentence_structure(enhanced_text)
            
            if progress_callback:
                progress_callback(1.0, "✨ 校正処理が完了しました!")
            
            return enhanced_text
            
        except Exception as e:
            logger.error(f"テキストの校正中にエラーが発生しました: {str(e)}")
            if progress_callback:
                progress_callback(1.0, f"❌ エラー: {str(e)}")
            return text