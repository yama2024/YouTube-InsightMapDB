import logging
from youtube_transcript_api import YouTubeTranscriptApi
import google.generativeai as genai
import re
import os
import time
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

    @cached(lambda self: self.processed_text_cache)
    def proofread_text(self, text: str) -> str:
        """Proofread and enhance text readability with AI assistance"""
        if not text:
            return ""
            
        try:
            prompt = f"""以下のテキストを校正し、読みやすく整形してください：
            
            1. 文章を自然な日本語に修正
            2. 句読点を適切に配置
            3. 段落を適切に分割
            4. 冗長な表現を簡潔に
            5. 文法的な誤りを修正
            
            入力テキスト：
            {text}
            """
            
            response = self.model.generate_content(prompt)
            enhanced_text = response.text if response.text else text
            
            # Apply additional formatting
            enhanced_text = self._clean_text(enhanced_text)
            enhanced_text = self._improve_sentence_structure(enhanced_text)
            
            return enhanced_text
            
        except Exception as e:
            logger.error(f"Text proofreading error: {str(e)}")
            return text

    @cached(lambda self: self.subtitle_cache)
    def _get_subtitles_with_priority(self, video_id: str) -> Optional[str]:
        """Get subtitles with enhanced error handling and caching"""
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            
            # Try Japanese subtitles first
            try:
                transcript = transcript_list.find_manually_created_transcript(['ja'])
            except Exception:
                try:
                    transcript = transcript_list.find_generated_transcript(['ja'])
                except Exception:
                    try:
                        transcript = transcript_list.find_manually_created_transcript(['ja-JP'])
                    except Exception:
                        transcript = None

            # Fallback to English if Japanese is not available
            if not transcript:
                try:
                    transcript = transcript_list.find_manually_created_transcript(['en'])
                except Exception:
                    try:
                        transcript = transcript_list.find_generated_transcript(['en'])
                    except Exception:
                        logger.error("No suitable subtitles found")
                        return None

            transcript_data = transcript.fetch()
            
            # Process transcript segments with improved timing
            transcript_segments = []
            current_segment = []
            current_time = 0
            
            for entry in transcript_data:
                text = entry['text'].strip()
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
                logger.warning("No valid transcript segments found")
                return None
                
            return '\n'.join(transcript_segments)

        except Exception as e:
            logger.error(f"Subtitle retrieval failed: {str(e)}")
            return None

    def _clean_text(self, text: str) -> str:
        """Enhanced text cleaning with improved Japanese handling"""
        if not text:
            return ""
        
        try:
            # Normalize Japanese text
            for category, replacements in self.jp_normalization.items():
                for old, new in replacements.items():
                    text = text.replace(old, new)
            
            # Remove noise patterns
            for pattern in self.noise_patterns.values():
                text = re.sub(pattern, '', text)
            
            # Improve sentence structure
            text = self._improve_sentence_structure(text)
            
            # Final cleanup
            text = re.sub(r'\n{3,}', '\n\n', text)  # Remove excessive newlines
            text = re.sub(r'\s+', ' ', text)  # Normalize spaces
            text = text.strip()
            
            return text
        except Exception as e:
            logger.error(f"Text cleaning error: {str(e)}")
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
            
            # Clean up list items
            text = re.sub(r'^[-・]\s*', '• ', text, flags=re.MULTILINE)
            
            return text
        except Exception as e:
            logger.error(f"Sentence structure improvement error: {str(e)}")
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
                logger.info("Using cached transcript")
                return cached_transcript
            
            transcript = self._get_subtitles_with_priority(video_id)
            if not transcript:
                raise ValueError("字幕を取得できませんでした")
            
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
            logger.error(f"Video ID extraction error: {str(e)}")
            return None

    @cached(lambda self: self.processed_text_cache)
    def generate_summary(self, text: str) -> str:
        """Generate summary with caching"""
        if not text:
            return ""
            
        try:
            prompt = f"""以下のテキストを要約してください。重要なポイントを箇条書きで示し、
            その後に簡潔な要約を作成してください：

            {text}

            出力形式：
            ■ 主なポイント：
            • ポイント1
            • ポイント2
            • ポイント3

            ■ 要約：
            [簡潔な要約文]
            """
            
            response = self.model.generate_content(prompt)
            return response.text if response.text else "要約を生成できませんでした。"
            
        except Exception as e:
            logger.error(f"Summary generation error: {str(e)}")
            return "要約の生成中にエラーが発生しました。"
