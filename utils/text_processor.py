import logging
from youtube_transcript_api import YouTubeTranscriptApi
import google.generativeai as genai
from google.cloud import speech_v1p1beta1 as speech
import re
import os
import tempfile
import pytube
import io
import time
from typing import List, Optional, Dict, Any

# Set up logging with more detailed format
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
        self.noise_patterns: Dict[str, Any] = {
            'timestamps': r'\[?\(?\d{1,2}:\d{2}(?::\d{2})?\]?\)?',  # Enhanced timestamp pattern
            'speaker_tags': r'\[[^\]]*\]|\([^)]*\)',  # Remove speaker labels
            'filler_words': r'\b(えーと|えっと|えー|あの|あのー|まぁ|んー|そのー|なんか|こう|ね|ねぇ|さぁ|うーん|あー|そうですね|ちょっと|まあ|そうですね|はい|あれ|そう|うん)\b',
            'repeated_chars': r'([^\W\d_])\1{2,}',  # Reduced threshold for repeated characters
            'multiple_spaces': r'[\s　]{2,}',  # Include full-width spaces
            'empty_lines': r'\n\s*\n',
            'punctuation': r'([。．！？])\1+',  # Handle repeated punctuation
            'noise_symbols': r'[♪♫♬♩†‡◊◆◇■□▲△▼▽○●◎⊕⊖⊗⊘⊙⊚⊛⊜⊝]'
        }
        
        # Additional patterns for Japanese text
        self.jp_patterns = {
            'normalize_periods': {
                '．': '。',
                '…': '。',
                '.': '。'
            },
            'remove_emphasis': r'[﹅﹆゛゜]'
        }

    def _clean_text(self, text: str) -> str:
        """Enhanced text cleaning with improved noise removal and Japanese text handling"""
        if not text:
            return text
            
        original_length = len(text)
        logger.debug(f"Original text length: {original_length}")
        
        try:
            # Normalize periods
            for old, new in self.jp_patterns['normalize_periods'].items():
                text = text.replace(old, new)
            
            # Remove emphasis marks
            text = re.sub(self.jp_patterns['remove_emphasis'], '', text)
            
            # Apply noise removal patterns
            for pattern_name, pattern in self.noise_patterns.items():
                before_length = len(text)
                text = re.sub(pattern, '', text if pattern_name != 'multiple_spaces' else ' ', text)
                after_length = len(text)
                logger.debug(f"Pattern {pattern_name}: Removed {before_length - after_length} characters")
            
            # Normalize spaces and line breaks
            text = re.sub(r'\s+', ' ', text)
            text = re.sub(r'\n{2,}', '\n', text)
            
            # Additional Japanese text cleanup
            text = re.sub(r'([。．！？、]) ?', r'\1', text)  # Remove spaces after Japanese punctuation
            text = re.sub(r'([。．！？、])([^」』】）\s])', r'\1\n\2', text)  # Add line breaks after sentences
            
            # Validate the cleaned text
            cleaned_length = len(text.strip())
            if cleaned_length < (original_length * 0.3):
                logger.warning(f"Significant content loss after cleaning: {cleaned_length}/{original_length} characters remaining")
                if cleaned_length < 100:  # Minimum viable length
                    logger.error("Cleaned text is too short, might have lost important content")
                    return text
            
            return text.strip() or text
            
        except Exception as e:
            logger.error(f"Error during text cleaning: {str(e)}")
            return text

    def generate_summary(self, text: str, max_retries: int = 5, initial_delay: int = 2) -> str:
        print("AI要約の生成を開始します...")
        
        # First clean the text
        cleaned_text = self._clean_text(text)
        
        retry_count = 0
        delay = initial_delay
        last_error = None
        
        while retry_count < max_retries:
            try:
                prompt = f'''
以下のYouTube動画コンテンツから構造化された要約を生成してください：

入力テキスト:
{cleaned_text}

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

上記のフォーマットに従って、簡潔で分かりやすい要約を生成してください。
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
                
                print("要約の生成が完了しました")
                return response.text
                
            except Exception as e:
                retry_count += 1
                delay *= 2  # Exponential backoff
                last_error = str(e)
                
                if retry_count < max_retries:
                    print(f"要約の生成に失敗しました。{delay}秒後に再試行します... ({retry_count}/{max_retries})")
                    time.sleep(delay)
                else:
                    error_msg = f"要約の生成に失敗しました: {last_error}"
                    print(error_msg)
                    raise Exception(error_msg)

    def get_transcript(self, url: str) -> str:
        video_id = self._extract_video_id(url)
        if not video_id:
            raise Exception("無効なYouTube URLです")
        
        try:
            # First try getting subtitles
            try:
                print("字幕の取得を試みています...")
                transcript = self._get_subtitles(video_id)
                if transcript:
                    # Clean and validate subtitle text
                    cleaned_transcript = self._clean_text(transcript)
                    if cleaned_transcript:
                        return cleaned_transcript
            except Exception as e:
                print(f"字幕の取得に失敗しました: {str(e)}")
            
            # If subtitles not available, use enhanced Speech-to-Text
            try:
                print("音声認識による文字起こしを開始します...")
                # Download audio with enhanced error handling
                yt = pytube.YouTube(url)
                if not yt:
                    raise Exception("YouTubeの動画情報を取得できませんでした")
                    
                audio_stream = yt.streams.filter(only_audio=True).first()
                if not audio_stream:
                    raise Exception("音声ストリームを取得できませんでした")
                
                print("音声ファイルをダウンロード中...")
                with tempfile.TemporaryDirectory() as temp_dir:
                    audio_path = os.path.join(temp_dir, "audio.mp4")
                    try:
                        audio_stream.download(filename=audio_path)
                    except Exception as e:
                        raise Exception(f"音声ファイルのダウンロードに失敗しました: {str(e)}")
                    
                    print("音声認識の準備中...")
                    client = speech.SpeechClient()
                    
                    # Enhanced audio configuration
                    with io.open(audio_path, "rb") as audio_file:
                        content = audio_file.read()
                    
                    audio = speech.RecognitionAudio(content=content)
                    config = speech.RecognitionConfig(
                        encoding=speech.RecognitionConfig.AudioEncoding.MP3,
                        sample_rate_hertz=16000,
                        language_code="ja-JP",
                        enable_automatic_punctuation=True,
                        model="video",
                        use_enhanced=True,
                        audio_channel_count=2,
                        enable_word_time_offsets=True,
                        enable_word_confidence=True,
                        profanity_filter=True
                    )
                    
                    print("音声認識を実行中...")
                    operation = client.long_running_recognize(config=config, audio=audio)
                    response = operation.result()
                    
                    # Enhanced transcript processing
                    transcript = ""
                    if response and hasattr(response, 'results'):
                        for result in response.results:
                            if result.alternatives:
                                # Only include high confidence results
                                if result.alternatives[0].confidence >= 0.8:
                                    transcript += result.alternatives[0].transcript + "\n"
                    
                    if not transcript:
                        raise Exception("音声認識に失敗しました")
                    
                    # Clean and enhance the transcript
                    cleaned_transcript = self._clean_text(transcript)
                    
                    print("文字起こし完了")
                    return cleaned_transcript
                    
            except Exception as e:
                raise Exception(f"音声認識による文字起こしに失敗しました: {str(e)}")
                
        except Exception as e:
            error_msg = f"文字起こしの取得に失敗しました: {str(e)}"
            print(error_msg)
            raise Exception(error_msg)

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
                    return match.group(1)
            
            return None
        except Exception as e:
            logger.error(f"Error extracting video ID: {str(e)}")
            return None

    def _get_subtitles(self, video_id: str) -> Optional[str]:
        """Enhanced subtitle retrieval with better language handling"""
        languages_to_try = [
            ['ja'],
            ['ja-JP'],
            ['en'],
            ['en-US'],
            None  # Try auto-generated captions as last resort
        ]
        
        for lang in languages_to_try:
            try:
                if lang:
                    transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=lang)
                else:
                    transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
                
                # Enhanced transcript processing
                transcript_text = []
                for entry in transcript_list:
                    # Only include entries with duration > 0.5 seconds
                    if entry.get('duration', 0) > 0.5:
                        text = entry['text']
                        # Basic cleaning before joining
                        text = re.sub(r'\[.*?\]', '', text)  # Remove bracketed content
                        text = text.strip()
                        if text:
                            transcript_text.append(text)
                
                return ' '.join(transcript_text)
            except Exception:
                continue
        
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
入力テキストを校閲し、以下の基準で改善してください：

1. 誤字・脱字の修正
2. 句読点の適切な配置
3. 自然な日本語表現への修正
4. 冗長な表現の簡潔化

制約：
- 意味の変更は不可
- 内容の追加・削除は不可
- 文の順序は維持

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
                        
                        proofread_chunks[chunk_index] = response.text.strip()
                        break
                        
                    except Exception as e:
                        retry_count += 1
                        delay *= 2
                        logger.error(f"Error processing chunk {i}: {str(e)}")
                        
                        if retry_count >= max_retries:
                            logger.error(f"Failed to process chunk {i} after {max_retries} attempts")
                            proofread_chunks[chunk_index] = chunk  # Use original chunk on failure
                            break
                        else:
                            time.sleep(delay)
            
            # Combine all chunks
            final_text = '\n'.join(chunk for chunk in proofread_chunks if chunk)
            return final_text
            
        except Exception as e:
            logger.error(f"Error during proofreading: {str(e)}")
            return text

    def chunk_text(self, text: str, chunk_size: int = 8000) -> List[str]:
        """Split text into manageable chunks while preserving sentence boundaries"""
        if not text:
            return []
            
        sentences = re.split(r'([。．！？\n])', text)
        current_chunk = []
        chunks = []
        current_length = 0
        
        for i in range(0, len(sentences)-1, 2):
            sentence = sentences[i] + (sentences[i+1] if i+1 < len(sentences) else '')
            sentence_length = len(sentence)
            
            if current_length + sentence_length > chunk_size and current_chunk:
                chunks.append(''.join(current_chunk))
                current_chunk = []
                current_length = 0
            
            current_chunk.append(sentence)
            current_length += sentence_length
        
        if current_chunk:
            chunks.append(''.join(current_chunk))
        
        return chunks
