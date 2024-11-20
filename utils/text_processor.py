import logging
from youtube_transcript_api import YouTubeTranscriptApi
import google.generativeai as genai
import re
import os
import time
import random
from typing import List, Optional, Dict, Any, Tuple
from retrying import retry
from cachetools import TTLCache, cached

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

    def _handle_rate_limit(self, attempt: int, max_attempts: int = 5) -> float:
        if attempt >= max_attempts:
            raise Exception("最大リトライ回数を超えました")
        
        # Calculate delay with jitter
        base_delay = min(32, (2 ** attempt))  # Exponential backoff capped at 32 seconds
        jitter = random.uniform(0, 0.1 * base_delay)  # 10% jitter
        return base_delay + jitter

    def generate_summary(self, text: str) -> str:
        try:
            # Smaller chunks for first processing
            first_chunk_size = 200  # Reduced size for first chunk
            regular_chunk_size = 400  # Size for subsequent chunks
            chunks = []
            
            # Special handling for first chunk
            if len(text) > first_chunk_size:
                chunks.append(text[:first_chunk_size])
                remaining_text = text[first_chunk_size:]
                chunks.extend(self._chunk_text(remaining_text, chunk_size=regular_chunk_size, overlap=30))
            else:
                chunks = [text]
            
            summaries = []
            last_request_time = 0
            min_request_interval = 3.0  # Increased minimum interval
            
            # Special handling for first chunk
            for i, chunk in enumerate(chunks):
                current_time = time.time()
                if current_time - last_request_time < min_request_interval:
                    time.sleep(min_request_interval - (current_time - last_request_time))
                
                # Extended retries for first chunk
                max_retries = 7 if i == 0 else 5
                success = False
                
                for attempt in range(max_retries):
                    try:
                        if attempt > 0:
                            delay = self._handle_rate_limit(attempt)
                            logger.info(f"チャンク {i+1} のリトライ {attempt+1}/{max_retries}, {delay}秒待機")
                            time.sleep(delay)
                        
                        prompt = f'''
                        以下のテキストを要約してください。
                        重要なポイントを漏らさず、簡潔にまとめてください。

                        テキスト:
                        {chunk}
                        '''
                        
                        response = self.model.generate_content(
                            prompt,
                            safety_settings=self.safety_settings,
                            generation_config=genai.types.GenerationConfig(
                                temperature=0.3,
                                top_p=0.8,
                                top_k=40,
                                max_output_tokens=400,  # Reduced token limit
                            )
                        )
                        
                        if response and response.text:
                            summaries.append(response.text.strip())
                            success = True
                            last_request_time = time.time()
                            # Additional delay after successful first chunk
                            if i == 0:
                                time.sleep(5.0)
                            break
                            
                    except Exception as e:
                        if 'Resource has been exhausted' in str(e):
                            logger.warning(f"レート制限エラー (チャンク {i+1}): {str(e)}")
                            if i == 0 and attempt < max_retries - 1:
                                time.sleep(10.0)  # Extended delay for first chunk
                            continue
                        raise
                
                if not success:
                    raise Exception(f"チャンク {i+1} の処理に失敗しました")
                
                # Progressive delay between chunks
                time.sleep(min(5.0, 2.0 + (i * 0.5)))
                
                if not summaries:
                    raise ValueError("要約を生成できませんでした")
                
                # Final summary with improved error handling
                final_text = "\n".join(summaries)
                for attempt in range(5):
                    try:
                        delay = self._handle_rate_limit(attempt)
                        time.sleep(delay)
                        
                        final_response = self.model.generate_content(
                            f"以下の要約をさらに整理して、簡潔にまとめてください:\n\n{final_text}",
                            safety_settings=self.safety_settings,
                            generation_config=genai.types.GenerationConfig(
                                temperature=0.3,
                                top_p=0.8,
                                top_k=40,
                                max_output_tokens=800,
                            )
                        )
                        
                        if final_response and final_response.text:
                            return final_response.text.strip()
                            
                    except Exception as e:
                        if 'Resource has been exhausted' in str(e) and attempt < 4:
                            logger.warning(f"最終要約でレート制限エラー: {str(e)}")
                            continue
                        raise
                
                raise Exception("最終要約の生成に失敗しました")
                
        except Exception as e:
            logger.error(f"要約生成エラー: {str(e)}")
            raise Exception(f"要約の生成に失敗しました: {str(e)}")

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

    def _chunk_text(self, text: str, chunk_size: int = 1500, overlap: int = 200) -> List[str]:
        if not text:
            return []
            
        # Split into sentences first
        sentences = re.split('([。!?！？]+)', text)
        sentences = [''.join(i) for i in zip(sentences[0::2], sentences[1::2])]
        
        chunks = []
        current_chunk = []
        current_length = 0
        
        for sentence in sentences:
            sentence_length = len(sentence)
            
            if current_length + sentence_length > chunk_size:
                if current_chunk:
                    chunks.append(''.join(current_chunk))
                    # Keep last sentence for overlap
                    current_chunk = current_chunk[-1:] if overlap > 0 else []
                    current_length = sum(len(s) for s in current_chunk)
                
            current_chunk.append(sentence)
            current_length += sentence_length
            
        if current_chunk:
            chunks.append(''.join(current_chunk))
            
        return chunks

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
            
            cleaned_transcript = self._clean_text(transcript)
            self.subtitle_cache[video_id] = cleaned_transcript
            return cleaned_transcript
            
        except Exception as e:
            error_msg = f"字幕取得エラー: {str(e)}"
            logger.error(error_msg)
            raise ValueError(error_msg)

    def _extract_video_id(self, url: str) -> Optional[str]:
        """Extract YouTube video ID from URL"""
        if not url:
            return None
            
        patterns = [
            r'(?:v=|/v/|^)([a-zA-Z0-9_-]{11})',
            r'(?:youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
            r'(?:youtube\.com/shorts/)([a-zA-Z0-9_-]{11})'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None