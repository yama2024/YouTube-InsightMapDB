import logging
from youtube_transcript_api import YouTubeTranscriptApi
import google.generativeai as genai
import re
import os
import time
from typing import List, Optional, Dict, Any

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
        
        # Enhanced noise patterns for better Japanese text processing
        self.noise_patterns: Dict[str, str] = {
            'timestamps': r'\[?\(?\d{1,2}:\d{2}(?::\d{2})?\]?\)?',
            'speaker_tags': r'\[[^\]]*\]|\([^)]*\)',
            'filler_words': r'\b(えーと|えっと|えー|あの|あのー|まぁ|んー|そのー|なんか|こう|ね|ねぇ|さぁ|うーん|あー|そうですね|ちょっと|まあ|そうですね|はい|あれ|そう|うん|えっとですね|そうですねー|まぁね|あのですね|そうそう|まあまあ|あのね|えっとね)\b',
            'repeated_chars': r'([^\W\d_])\1{3,}',
            'multiple_spaces': r'[\s　]{2,}',
            'empty_lines': r'\n\s*\n',
            'punctuation': r'([。．！？])\1+',
            'noise_symbols': r'[♪♫♬♩†‡◊◆◇■□▲△▼▽○●◎⊕⊖⊗⊘⊙⊚⊛⊜⊝]',
            'parentheses': r'（[^）]*）|\([^)]*\)',
            'unnecessary_symbols': r'[＊∗※#＃★☆►▷◁◀→←↑↓]',
            'repeated_particles': r'((?:です|ます|した|ました|ません|で|に|は|が|を|な|の|と|も|や|へ|より|から|まで|による|において|について|として|という|といった|における|であって|であり|である|のような|かもしれない)\s*)+',
            'excessive_honorifics': r'(?:さん|様|氏|君|先生|殿){2,}',
            'ascii_art': r'[│┃┄┅┆┇┈┉┊┋┌┍┎┏┐┑┒┓└┕┖┗┘┙┚┛━┃┏┓┗┛┣┫┳┻╋]',
            'machine_artifacts': r'(?:\(generated\)|\[automated\]|\[machine\s*translated\])',
            'url_patterns': r'https?://\S+|www\.\S+',
            'hashtags': r'#\w+',
            'time_codes': r'\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?',
            'automated_tags': r'\[(?:音楽|拍手|笑|BGM|SE|効果音|ノイズ|雑音|間|一同|※)\]',
            'parenthetical_info': r'【[^】]*】|\([^)]*\)',
            'commercial_markers': r'(?:CM|広告|スポンサー)(?:\s*\d*)?',
            'system_messages': r'(?:システム|エラー|通知)(?:：|:).*?(?:\n|$)',
            'social_media_artifacts': r'@\w+|RT\s@\w+|#\w+',
            'formatting_markers': r'\*+|\#+|\{[^}]*\}|\[[^\]]*\]',
            'noise_words': r'\b(あー|えー|んー|まー|そのー|えっとー|あのー|まぁー|うーん|えっとぉ|んーと|そうですねぇ)\b',
            'repeated_words': r'(\b\w+\b)(\s+\1\b)+',
            'excessive_spaces': r'(?:　|\s){2,}',
            'line_noise': r'^[\s　]*(?:[=\-~]{3,}|[・×※]{2,})[\s　]*$'
        }
        
        # Enhanced Japanese text normalization patterns
        self.jp_patterns = {
            'normalize_periods': {
                '．': '。',
                '…': '。',
                '.': '。',
                '....': '。',
                '...': '。',
                '｡': '。'
            },
            'normalize_spaces': {
                '　': ' ',
                '\u3000': ' ',
                '\xa0': ' '
            },
            'normalize_quotes': {
                '「': '『',
                '」': '』',
                '"': '『',
                '"': '』',
                ''': '『',
                ''': '』'
            },
            'normalize_punctuation': {
                '、': '、',
                '､': '、',
                '？': '？',
                '?': '？',
                '!': '！',
                '！': '！'
            },
            'normalize_long_vowels': {
                'ー+': 'ー'
            },
            'remove_emphasis': r'[﹅﹆゛゜]'
        }

    def _clean_text(self, text: str) -> str:
        """Enhanced text cleaning with improved noise removal and Japanese text handling"""
        if not text:
            return ""
        
        original_length = len(text)
        logger.debug(f"Original text length: {original_length}")
        
        try:
            # Text normalization
            text = self._normalize_japanese_text(text)
            
            # Apply noise removal patterns with detailed logging
            for pattern_name, pattern in self.noise_patterns.items():
                before_length = len(text)
                if pattern_name == 'multiple_spaces':
                    text = re.sub(pattern, ' ', text)
                elif pattern_name == 'repeated_particles':
                    text = re.sub(pattern, lambda m: m.group(1).split()[0] + ' ', text)
                elif pattern_name == 'repeated_words':
                    text = re.sub(pattern, r'\1', text)
                else:
                    text = re.sub(pattern, '', text)
                after_length = len(text)
                
                if before_length - after_length > 0:
                    logger.debug(f"Pattern {pattern_name}: Removed {before_length - after_length} characters")
            
            # Post-processing improvements
            text = self._improve_sentence_structure(text)
            text = self._format_paragraphs(text)
            text = self._apply_final_cleanup(text)
            
            # Final validation and quality check
            cleaned_text = text.strip()
            if not cleaned_text:
                logger.warning("Cleaning resulted in empty text")
                return text
            
            cleaned_length = len(cleaned_text)
            if cleaned_length < (original_length * 0.3):
                logger.warning(f"Significant content loss after cleaning: {cleaned_length}/{original_length} characters")
                if cleaned_length < 100:
                    logger.error("Cleaned text is too short, might have lost important content")
                    return text
            
            return cleaned_text
            
        except Exception as e:
            logger.error(f"Error during text cleaning: {str(e)}")
            return text if text else ""

    def _apply_final_cleanup(self, text: str) -> str:
        """Apply final cleanup rules to the text"""
        try:
            # Remove excessive newlines
            text = re.sub(r'\n{3,}', '\n\n', text)
            
            # Fix spacing around punctuation
            text = re.sub(r'\s+([。、！？」』）])', r'\1', text)
            text = re.sub(r'([「『（])\s+', r'\1', text)
            
            # Normalize sentence endings
            text = re.sub(r'([。！？])\s*(?=[^」』）])', r'\1\n', text)
            
            # Clean up list markers
            text = re.sub(r'^[-・]\s*', '• ', text, flags=re.MULTILINE)
            
            # Remove trailing spaces
            text = re.sub(r'\s+$', '', text, flags=re.MULTILINE)
            
            return text
        except Exception as e:
            logger.error(f"Error in final cleanup: {str(e)}")
            return text

    def _normalize_japanese_text(self, text: str) -> str:
        """Enhanced normalization for Japanese text"""
        try:
            # Apply all normalization patterns
            for pattern_type, patterns in self.jp_patterns.items():
                if isinstance(patterns, dict):
                    for old, new in patterns.items():
                        text = text.replace(old, new)
                else:
                    text = re.sub(patterns, '', text)
            
            # Additional normalization for Japanese text
            text = re.sub(r'([。！？])\1+', r'\1', text)  # Remove repeated punctuation
            text = re.sub(r'([。！？])(?=[^」』】）\s])', r'\1\n', text)  # Add newline after sentence endings
            text = re.sub(r'\s*\n\s*', '\n', text)  # Clean up whitespace around newlines
            
            # Normalize long vowels and remove unnecessary emphasis marks
            text = re.sub(r'ー{2,}', 'ー', text)
            text = re.sub(r'[゛゜]{2,}', '', text)
            
            return text
        except Exception as e:
            logger.error(f"Error in Japanese text normalization: {str(e)}")
            return text

    def _improve_sentence_structure(self, text: str) -> str:
        """Improve sentence structure while preserving context"""
        try:
            # Add proper spacing after punctuation
            text = re.sub(r'([。．！？、]) ?([^」』】）\s])', r'\1\n\2', text)
            
            # Fix spacing around quotes
            text = re.sub(r'『\s+', '『', text)
            text = re.sub(r'\s+』', '』', text)
            
            # Normalize multiple newlines
            text = re.sub(r'\n{3,}', '\n\n', text)
            
            # Ensure proper spacing between sentences
            text = re.sub(r'([。！？](?:[」』】）])?)\s*(?=[^\s」』】）])', r'\1\n', text)
            
            # Improve readability of lists
            text = re.sub(r'(^|\n)[-・](.*?)(?=\n|$)', r'\1• \2', text)
            
            # Fix Japanese particle spacing
            text = re.sub(r'(\s+(?:は|が|を|に|へ|で|と|から|まで|より))\s+', r'\1', text)
            
            return text
        except Exception as e:
            logger.error(f"Error in sentence structure improvement: {str(e)}")
            return text

    def _format_paragraphs(self, text: str) -> str:
        """Enhanced paragraph formatting"""
        try:
            # Split into paragraphs
            paragraphs = text.split('\n\n')
            formatted_paragraphs = []
            
            for paragraph in paragraphs:
                # Skip empty paragraphs
                if not paragraph.strip():
                    continue
                    
                # Clean up whitespace
                paragraph = re.sub(r'\s+', ' ', paragraph.strip())
                
                # Remove single-character lines
                if len(paragraph.strip()) <= 1:
                    continue
                
                # Remove lines that are just punctuation
                if re.match(r'^[。、！？]+$', paragraph.strip()):
                    continue
                
                # Add paragraph to list
                formatted_paragraphs.append(paragraph)
            
            # Join paragraphs with double newlines
            return '\n\n'.join(formatted_paragraphs)
        except Exception as e:
            logger.error(f"Error in paragraph formatting: {str(e)}")
            return text

    def get_transcript(self, url: str) -> str:
        """Enhanced transcript retrieval with improved fallback handling"""
        video_id = self._extract_video_id(url)
        if not video_id:
            raise ValueError("無効なYouTube URLです")
        
        transcript = self._get_subtitles_with_priority(video_id)
        if not transcript:
            raise ValueError("字幕を取得できませんでした")
        
        return self._clean_text(transcript)

    def _get_subtitles_with_priority(self, video_id: str) -> Optional[str]:
        """Get subtitles with enhanced language priority handling"""
        language_priority = [
            ['ja'],
            ['ja-JP'],
            ['en-JP'],
            ['en'],
            ['en-US'],
            None  # Auto-generated captions
        ]
        
        for lang in language_priority:
            try:
                logger.debug(f"字幕を試行中: {lang if lang else '自動生成'}")
                transcript_list = YouTubeTranscriptApi.get_transcript(
                    video_id,
                    languages=[lang] if lang else None
                )
                
                # Enhanced transcript processing with context preservation
                transcript_segments = []
                current_segment = []
                
                for entry in transcript_list:
                    if entry.get('duration', 0) <= 0.5:  # Skip very short segments
                        continue
                    
                    text = entry['text']
                    text = re.sub(r'\[.*?\]', '', text)  # Remove bracketed content
                    text = text.strip()
                    
                    if not text:
                        continue
                    
                    # Check if this segment ends with sentence-ending punctuation
                    if re.search(r'[。．.！!？?]$', text):
                        current_segment.append(text)
                        if current_segment:
                            transcript_segments.append(' '.join(current_segment))
                            current_segment = []
                    else:
                        current_segment.append(text)
                
                # Add any remaining segments
                if current_segment:
                    transcript_segments.append(' '.join(current_segment))
                
                if transcript_segments:
                    return '\n'.join(transcript_segments)
                    
            except Exception as e:
                logger.debug(f"字幕取得失敗 ({lang if lang else '自動生成'}): {str(e)}")
                continue
        
        return None

    def _extract_video_id(self, url: str) -> Optional[str]:
        """Extract video ID from YouTube URL with enhanced validation"""
        try:
            patterns = [
                r'(?:v=|\/videos\/|embed\/|youtu.be\/|\/v\/|\/e\/|watch\?v%3D|watch\?feature=player_embedded&v=|%2Fvideos%2F|embed%\u200C\u200B2F|youtu.be%2F|%2Fv%2F)([^#\&\?\n]*)',
                r'(?:youtu\.be\/|youtube\.com(?:\/embed\/|\/v\/|\/watch\?v=|\/watch\?.+&v=))([\w-]{11})'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, url)
                if match:
                    video_id = match.group(1)
                    if len(video_id) == 11:  # Validate ID length
                        return video_id
            
            return None
        except Exception as e:
            logger.error(f"Error extracting video ID: {str(e)}")
            return None

    def proofread_text(self, text: str, max_retries: int = 5, initial_delay: int = 1) -> str:
        """Proofread and enhance text with improved validation and logging"""
        try:
            # Split text into chunks
            text_chunks = self.chunk_text(text, chunk_size=8000)
            total_chunks = len(text_chunks)
            logger.info(f"テキストを{total_chunks}個のチャンクに分割しました")
            
            # Initialize result array with empty strings
            proofread_chunks: List[str] = [""] * total_chunks
            remaining_chunks = list(range(total_chunks))
            
            original_text_length = len(text)
            logger.info(f"Original text length: {original_text_length}")
            
            for chunk_index in remaining_chunks[:]:
                i = chunk_index + 1
                chunk = text_chunks[chunk_index]
                retry_count = 0
                delay = initial_delay
                
                while retry_count < max_retries:
                    try:
                        logger.info(f"チャンク {i}/{total_chunks} を処理中... (試行: {retry_count + 1})")
                        
                        chunk_prompt = f'''
入力テキストを以下の基準で校閲し、改善してください：

校閲基準：
1. 誤字・脱字の修正
2. 不要な繰り返しの削除
3. 口語表現の書き言葉への変換
4. 文章の自然な区切りの改善
5. 文の接続と流れの最適化
6. 読みやすい段落構成
7. 適切な句読点の配置

制約：
- 意味の変更は不可
- 内容の追加・削除は不可
- 文の順序は維持
- オリジナルの文脈を保持

入力テキスト：
{chunk}

校閲後のテキストのみを出力してください。
'''
                        response = self.model.generate_content(
                            chunk_prompt,
                            generation_config=genai.types.GenerationConfig(
                                temperature=0.1,
                                top_p=0.95,
                                top_k=50,
                                max_output_tokens=16384,
                            )
                        )
                        
                        if not response or not response.text:
                            raise ValueError("Empty response from API")
                        
                        proofread_text = response.text.strip()
                        
                        # Validate the proofread text
                        if len(proofread_text) < (len(chunk) * 0.5):
                            raise ValueError("Proofread text is too short")
                        
                        # Clean up the proofread text
                        proofread_text = self._clean_text(proofread_text)
                        proofread_chunks[chunk_index] = proofread_text
                        
                        # Remove successfully processed chunk from remaining
                        remaining_chunks.remove(chunk_index)
                        break
                        
                    except Exception as e:
                        logger.error(f"Error in chunk {i}: {str(e)}")
                        retry_count += 1
                        time.sleep(delay)
                        delay *= 2  # Exponential backoff
                        
                        if retry_count >= max_retries:
                            logger.error(f"Max retries reached for chunk {i}")
                            proofread_chunks[chunk_index] = chunk  # Use original chunk if all retries fail
                
            # Combine all chunks
            proofread_text = '\n\n'.join(filter(None, proofread_chunks))
            
            # Final cleanup
            proofread_text = self._clean_text(proofread_text)
            
            if not proofread_text:
                raise ValueError("Final proofread text is empty")
                
            return proofread_text
            
        except Exception as e:
            logger.error(f"Error in proofread_text: {str(e)}")
            return text

    def chunk_text(self, text: str, chunk_size: int = 8000) -> List[str]:
        """Split text into manageable chunks while preserving sentence boundaries"""
        try:
            if not text:
                return []
                
            chunks = []
            current_chunk = []
            current_length = 0
            
            # Split text into sentences
            sentences = re.split(r'([。．.！!？?])', text)
            
            for i in range(0, len(sentences), 2):
                if i + 1 < len(sentences):
                    # Combine sentence with its punctuation
                    sentence = sentences[i] + sentences[i + 1]
                else:
                    sentence = sentences[i]
                
                sentence_length = len(sentence)
                
                if current_length + sentence_length > chunk_size and current_chunk:
                    # Join current chunk and add to chunks list
                    chunks.append(''.join(current_chunk))
                    current_chunk = []
                    current_length = 0
                
                current_chunk.append(sentence)
                current_length += sentence_length
            
            # Add remaining chunk if any
            if current_chunk:
                chunks.append(''.join(current_chunk))
            
            return chunks
            
        except Exception as e:
            logger.error(f"Error in chunk_text: {str(e)}")
            return [text]

    def generate_summary(self, text: str) -> str:
        """Generate summary with improved text processing"""
        if not text:
            return ""
            
        try:
            prompt = f'''
以下のYouTube動画コンテンツから構造化された要約を生成してください：

入力テキスト:
{text}

必須要素:
1. タイトル（見出し1）
2. 概要（2-3文の簡潔な説明）
3. 主要ポイント（箇条書き）
4. 詳細説明（サブセクション）
5. 結論（まとめ）

出力形式:
# [動画タイトル]

## 概要
[2-3文の説明]

## 主要ポイント
- [重要なポイント1]
- [重要なポイント2]
- [重要なポイント3]

## 詳細説明
### [トピック1]
[詳細な説明]

### [トピック2]
[詳細な説明]

## 結論
[まとめと結論]
'''
            
            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.3,
                    top_p=0.8,
                    top_k=40,
                    max_output_tokens=8192,
                )
            )
            
            if not response or not response.text:
                raise ValueError("Empty response from API")
            
            return response.text
            
        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            raise