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

    def chunk_text(self, text, chunk_size=8000):  # Increased chunk size
        """Split text into chunks while preserving sentence integrity"""
        logger.debug(f"Starting text chunking with chunk_size: {chunk_size}")
        logger.debug(f"Original text length: {len(text)}")
        
        sentences = text.split('。')
        chunks = []
        current_chunk = []
        current_length = 0
        total_processed = 0
        
        for sentence in sentences:
            if not sentence.strip():
                continue
            
            sentence = sentence + '。'
            sentence_length = len(sentence)
            total_processed += sentence_length
            
            if current_length + sentence_length > chunk_size and current_chunk:
                chunk_text = ''.join(current_chunk)
                chunks.append(chunk_text)
                logger.debug(f"Created chunk of length: {len(chunk_text)}")
                current_chunk = [sentence]
                current_length = sentence_length
            else:
                current_chunk.append(sentence)
                current_length += sentence_length
        
        if current_chunk:
            chunk_text = ''.join(current_chunk)
            chunks.append(chunk_text)
            logger.debug(f"Created final chunk of length: {len(chunk_text)}")
        
        # Validate no text was lost with stricter validation
        total_chunks_length = sum(len(chunk) for chunk in chunks)
        logger.debug(f"Total processed text length: {total_processed}")
        logger.debug(f"Total chunks length: {total_chunks_length}")
        
        if total_chunks_length < (total_processed * 0.98):  # Stricter validation
            logger.error("Text chunking validation failed: Content loss detected")
            raise ValueError("Text chunking resulted in content loss")
            
        logger.info(f"Successfully created {len(chunks)} chunks")
        return chunks

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
                    return transcript
            except Exception as e:
                print(f"字幕の取得に失敗しました: {str(e)}")
            
            # If subtitles not available, use Speech-to-Text
            try:
                print("音声認識による文字起こしを開始します...")
                # Download audio
                yt = pytube.YouTube(url)
                if not yt:
                    raise Exception("YouTubeの動画情報を取得できませんでした")
                    
                audio_stream = yt.streams.filter(only_audio=True).first()
                if not audio_stream:
                    raise Exception("音声ストリームを取得できませんでした")
                
                print("音声ファイルをダウンロード中...")
                # Create temp directory and save audio
                with tempfile.TemporaryDirectory() as temp_dir:
                    audio_path = os.path.join(temp_dir, "audio.mp4")
                    try:
                        audio_stream.download(filename=audio_path)
                    except Exception as e:
                        raise Exception(f"音声ファイルのダウンロードに失敗しました: {str(e)}")
                    
                    print("音声認識の準備中...")
                    # Initialize Speech client
                    client = speech.SpeechClient()
                    
                    # Load the audio file
                    with io.open(audio_path, "rb") as audio_file:
                        content = audio_file.read()
                    
                    # Configure audio and recognition settings
                    audio = speech.RecognitionAudio(content=content)
                    config = speech.RecognitionConfig(
                        encoding=speech.RecognitionConfig.AudioEncoding.MP3,
                        sample_rate_hertz=16000,
                        language_code="ja-JP",
                        enable_automatic_punctuation=True,
                        model="video",
                        use_enhanced=True,
                        audio_channel_count=2
                    )
                    
                    # Perform the transcription
                    print("音声認識を実行中...")
                    operation = client.long_running_recognize(config=config, audio=audio)
                    if not operation:
                        raise Exception("音声認識の開始に失敗しました")
                        
                    response = operation.result()
                    if not response or not hasattr(response, 'results'):
                        raise Exception("音声認識の結果を取得できませんでした")
                    
                    # Combine all transcripts
                    transcript = ""
                    for result in response.results:
                        if result.alternatives:
                            transcript += result.alternatives[0].transcript + "\n"
                    
                    if not transcript:
                        raise Exception("音声認識に失敗しました")
                    
                    print("文章を整形中...")
                    # Use Gemini to enhance the transcript
                    enhanced_prompt = f'''
                    以下の文字起こしテキストを自然な日本語に整形してください：
                    - 文章を適切に区切る
                    - 句読点を追加
                    - フィラーワードを削除
                    - 重複した表現を整理
                    - 文脈を保持
                    
                    テキスト：
                    {transcript}
                    '''
                    
                    response = self.model.generate_content(
                        enhanced_prompt,
                        generation_config=genai.types.GenerationConfig(
                            temperature=0.3,
                            top_p=0.8,
                            top_k=40,
                            max_output_tokens=8192,
                        )
                    )
                    
                    print("文字起こし完了")
                    return response.text if response.text else transcript
                    
            except Exception as e:
                raise Exception(f"音声認識による文字起こしに失敗しました: {str(e)}")
                
        except Exception as e:
            error_msg = f"文字起こしの取得に失敗しました: {str(e)}"
            print(error_msg)
            raise Exception(error_msg)

    def _get_subtitles(self, video_id):
        languages_to_try = [
            ['ja'],
            ['ja-JP'],
            ['en'],
            ['en-US'],
            None
        ]
        
        for lang in languages_to_try:
            try:
                if lang:
                    transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=lang)
                else:
                    transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
                return ' '.join([entry['text'] for entry in transcript_list])
            except Exception:
                continue
        
        return None

    def generate_summary(self, text, max_retries=5, initial_delay=2):
        print("AI要約の生成を開始します...")
        
        retry_count = 0
        delay = initial_delay
        last_error = None
        
        while retry_count < max_retries:
            try:
                prompt = f'''
                YouTube動画の文字起こしテキストを元に、内容をわかりやすく簡潔にまとめたリッチなデザインの要約を生成してください。

                # 必須条件
                - 文字起こしのテキスト内容を正確に反映しつつ、重要なポイントを抽出してください。
                - 要約は視覚的にわかりやすく、以下のフォーマットで出力してください。
                  - **タイトル**: 動画全体を表す簡潔なタイトル
                  - **サブタイトル**: タイトルを補足する簡単な説明
                  - **箇条書き**: 重要なポイントを3～5個の箇条書きで列挙
                  - **結論**: 動画の主要なメッセージまたは結論

                # 出力フォーマット
                以下の形式で要約を作成してください：

                タイトル: [動画全体の内容を要約したタイトル]
                サブタイトル: [タイトルの補足説明や要点]
                ポイント:
                [重要ポイント1]
                [重要ポイント2]
                [重要ポイント3]
                [重要ポイント4] (必要に応じて)
                [重要ポイント5] (必要に応じて)
                結論:
                [動画全体の主要なメッセージや結論]

                テキスト:
                {text}
                '''
                
                generation_config = genai.types.GenerationConfig(
                    temperature=0.3,
                    top_p=0.8,
                    top_k=40,
                    max_output_tokens=4096,
                )
                
                response = self.model.generate_content(
                    prompt,
                    generation_config=generation_config
                )
                
                if response and response.text:
                    print("要約が完了しました")
                    return response.text
                else:
                    raise ValueError("要約の生成結果が空です")
                    
            except Exception as e:
                last_error = str(e)
                retry_count += 1
                
                if retry_count < max_retries:
                    print(f"要約の生成に失敗しました。{delay}秒後に再試行します... ({retry_count}/{max_retries})")
                    print(f"エラー内容: {last_error}")
                    time.sleep(delay)
                    delay *= 2  # Exponential backoff
                else:
                    print(f"要約の生成が{max_retries}回失敗しました")
                    error_msg = f"要約の生成に失敗しました: {last_error}"
                    print(f"最終エラー: {error_msg}")
                    raise Exception(error_msg)

    def _extract_video_id(self, url):
        """URLからビデオIDを抽出"""
        video_id_match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', url)
        if video_id_match:
            return video_id_match.group(1)
        return None