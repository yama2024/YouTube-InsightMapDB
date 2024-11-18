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
        # Update to use Gemini 1.5 Pro
        self.model = genai.GenerativeModel('gemini-1.5-pro')
        
        # Enhanced noise patterns
        self.noise_patterns = {
            'timestamps': r'\(\d{2}:\d{2}(?::\d{2})?\)',
            'filler_words': r'\b(えーと|えっと|えー|あの|あのー|まぁ|んー|そのー|なんか|こう|ね|ねぇ|さぁ|うーん|あー)\b',
            'repeated_chars': r'([^\W\d_])\1{3,}',
            'multiple_spaces': r' +',
            'empty_lines': r'\n\s*\n'
        }

    def _clean_text(self, text):
        """Enhanced text cleaning with better noise removal"""
        if not text:
            return text
            
        # Keep original length for validation
        original_length = len(text)
        
        try:
            # Remove timestamps
            text = re.sub(self.noise_patterns['timestamps'], '', text)
            
            # Remove filler words
            text = re.sub(self.noise_patterns['filler_words'], '', text)
            
            # Fix repeated characters
            text = re.sub(self.noise_patterns['repeated_chars'], r'\1', text)
            
            # Normalize spaces
            text = re.sub(self.noise_patterns['multiple_spaces'], ' ', text)
            
            # Fix empty lines
            text = re.sub(self.noise_patterns['empty_lines'], '\n', text)
            
            # Additional cleaning steps
            text = text.replace('...', '。').replace('…', '。')
            text = re.sub(r'([。．！？])\1+', r'\1', text)  # Remove repeated punctuation
            text = re.sub(r'[\r\t]', '', text)  # Remove special characters
            
            # Validate the cleaned text
            if len(text.strip()) < (original_length * 0.3):  # Text is too short after cleaning
                logger.warning("Significant content loss after cleaning")
                return text
                
            return text.strip()
            
        except Exception as e:
            logger.error(f"Error during text cleaning: {str(e)}")
            return text

    def chunk_text(self, text, chunk_size=8000):
        """Improved text chunking with better sentence preservation"""
        logger.debug(f"Starting text chunking with chunk_size: {chunk_size}")
        logger.debug(f"Original text length: {len(text)}")
        
        # Clean text before chunking
        text = self._clean_text(text)
        
        # Split by sentences while preserving Japanese periods
        sentence_pattern = r'([。．！？][\s]*)'
        sentences = re.split(sentence_pattern, text)
        
        # Recombine sentences with their punctuation
        sentences = [''.join(i) for i in zip(sentences[0::2], sentences[1::2] + [''])]
        
        chunks = []
        current_chunk = []
        current_length = 0
        total_processed = 0
        
        for sentence in sentences:
            if not sentence.strip():
                continue
            
            sentence_length = len(sentence)
            total_processed += sentence_length
            
            # Check if adding this sentence would exceed chunk size
            if current_length + sentence_length > chunk_size and current_chunk:
                chunk_text = ''.join(current_chunk)
                chunks.append(chunk_text)
                logger.debug(f"Created chunk of length: {len(chunk_text)}")
                current_chunk = [sentence]
                current_length = sentence_length
            else:
                current_chunk.append(sentence)
                current_length += sentence_length
        
        # Add the last chunk if it exists
        if current_chunk:
            chunk_text = ''.join(current_chunk)
            chunks.append(chunk_text)
            logger.debug(f"Created final chunk of length: {len(chunk_text)}")
        
        # Validate chunking results
        total_chunks_length = sum(len(chunk) for chunk in chunks)
        logger.debug(f"Total processed text length: {total_processed}")
        logger.debug(f"Total chunks length: {total_chunks_length}")
        
        if total_chunks_length < (total_processed * 0.98):
            logger.error("Text chunking validation failed: Content loss detected")
            raise ValueError("Text chunking resulted in content loss")
        
        logger.info(f"Successfully created {len(chunks)} chunks")
        return chunks

    def get_transcript(self, url):
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
                        enable_word_time_offsets=True,  # Added for better timing
                        enable_word_confidence=True,    # Added for confidence scoring
                        profanity_filter=True          # Added to filter inappropriate content
                    )
                    
                    print("音声認識を実行中...")
                    operation = client.long_running_recognize(config=config, audio=audio)
                    response = operation.result()
                    
                    # Enhanced transcript processing
                    transcript = ""
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

    def _extract_video_id(self, url):
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

    def _get_subtitles(self, video_id):
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

    def generate_summary(self, text, max_retries=5, initial_delay=2):
        print("AI要約の生成を開始します...")
        
        # First clean the text
        cleaned_text = self._clean_text(text)
        
        retry_count = 0
        delay = initial_delay
        last_error = None
        
        while retry_count < max_retries:
            try:
                prompt = f'''
                以下のYouTube動画の文字起こしテキストから、重要なポイントを抽出し、簡潔で読みやすい要約を生成してください。

                # 必須条件
                1. 文字起こしの内容を正確に反映
                2. 重要なポイントを明確に抽出
                3. 簡潔で分かりやすい日本語
                4. 論理的な構造化

                # 出力フォーマット
                タイトル: [内容を端的に表現]
                
                概要:
                [全体の要約を2-3文で]
                
                主要ポイント:
                ・[ポイント1]
                ・[ポイント2]
                ・[ポイント3]
                
                結論:
                [メインメッセージや重要な結論]

                テキスト:
                {cleaned_text}
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
                
                if not response.text:
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

    def proofread_text(self, text, max_retries=5, initial_delay=1):
        """Proofread and enhance text with improved validation and logging"""
        try:
            # Split text into chunks
            text_chunks = self.chunk_text(text, chunk_size=8000)
            total_chunks = len(text_chunks)
            logger.info(f"テキストを{total_chunks}個のチャンクに分割しました")
            
            # Initialize result array with None values to maintain order
            proofread_chunks = [None] * total_chunks
            remaining_chunks = list(range(total_chunks))
            
            original_text_length = len(text)
            logger.info(f"Original text length: {original_text_length}")
            
            while remaining_chunks:
                for chunk_index in remaining_chunks[:]:
                    i = chunk_index + 1
                    chunk = text_chunks[chunk_index]
                    retry_count = 0
                    delay = initial_delay
                    
                    while retry_count < max_retries:
                        try:
                            logger.info(f"チャンク {i}/{total_chunks} を処理中... (試行: {retry_count + 1})")
                            logger.debug(f"Processing chunk of length: {len(chunk)}")
                            
                            generation_config = genai.types.GenerationConfig(
                                temperature=0.1,  # Lower temperature for more consistent output
                                top_p=0.95,
                                top_k=50,
                                max_output_tokens=16384,  # Increased token limit
                            )
                            
                            chunk_prompt = f'''
# あなたの目的:
{chunk}のテキストを完全に漏れなく校閲します。

文字起こしした{chunk}のテキストについて、元の文章の意味を絶対に変更せずに文字起こしと校閲を行います。最後まで処理が完了するまで{max_retries}回繰り返して、実行してください。

# 追加のルール:
1. 校閲した文章以外の出力は決して行ってはいけません。
2. 校閲した文章のみを出力します。
3. 改行の位置が不自然だった場合は文章と共に適切に改行位置も修正してください。
4. 時間を意味するような表示として"(00:00)"といった記載がある場合がありますが、それは文章ではないので、文章から削除して校閲を行ってください。
5. スピーチtoテキストで文章を入力している場合、「えー」、「まあ」、「あのー」といったフィラーが含まれている場合があります。こちらも削除して校閲を行ってください。
6. テキストを出力するときには、「。」で改行を行って見やすい文章を出力してください。
'''
                            response = self.model.generate_content(
                                chunk_prompt,
                                generation_config=generation_config
                            )
                            
                            if response and response.text:
                                proofread_chunk = response.text.strip()
                                logger.debug(f"Processed chunk length: {len(proofread_chunk)}")
                                
                                # Stricter validation for chunk processing
                                if len(proofread_chunk) < (len(chunk) * 0.8):  # Increased threshold
                                    raise ValueError(f"Processed chunk is incomplete: {len(proofread_chunk)} vs {len(chunk)}")
                                
                                proofread_chunks[chunk_index] = proofread_chunk
                                remaining_chunks.remove(chunk_index)
                                logger.info(f"チャンク {i}/{total_chunks} の処理が完了しました")
                                break
                            else:
                                raise ValueError(f"チャンク {i}/{total_chunks} の校閲結果が空です")
                                
                        except Exception as e:
                            retry_count += 1
                            if retry_count < max_retries:
                                logger.warning(f"チャンク {i} の処理に失敗しました。{delay}秒後に再試行します...")
                                time.sleep(delay)
                                delay *= 2  # Exponential backoff
                            else:
                                logger.error(f"チャンク {i} の処理が{max_retries}回失敗しました。元のテキストを使用します。")
                                proofread_chunks[chunk_index] = chunk
                                remaining_chunks.remove(chunk_index)
                                break
            
            # Verify all chunks were processed
            if None in proofread_chunks:
                raise Exception("一部のチャンクが処理されていません")
            
            # Join all proofread chunks with proper spacing
            final_text = '\n\n'.join(chunk.strip() for chunk in proofread_chunks if chunk)
            
            # Validate final text
            final_text_length = len(final_text)
            logger.info(f"Final text length: {final_text_length}")
            
            if final_text_length < (original_text_length * 0.5):
                logger.error(f"Final text is too short: {final_text_length} vs {original_text_length}")
                raise ValueError("校閲後のテキストが元のテキストと比べて極端に短くなっています")
            
            logger.info("すべてのチャンクの処理が完了しました")
            return final_text
                
        except Exception as e:
            error_msg = f"テキストの校閲に失敗しました: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)