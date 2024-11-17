from youtube_transcript_api import YouTubeTranscriptApi
import google.generativeai as genai
from google.cloud import speech_v1p1beta1 as speech
import re
import os
import tempfile
import pytube
import io

class TextProcessor:
    def __init__(self):
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("Gemini API key is not set in environment variables")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-pro')

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

    def generate_summary(self, text):
        """テキストの要約を生成"""
        print("AI要約の生成を開始します...")
        prompt = f"""
        以下のテキストを要約してください。要約は以下の点に注意して生成してください：
        - 主要なポイントを3-5個抽出
        - 文章は簡潔に
        - 箇条書きで表示
        
        テキスト:
        {text}
        """
        
        try:
            response = self.model.generate_content(prompt)
            print("要約が完了しました")
            return response.text
        except Exception as e:
            raise Exception("要約の生成に失敗しました")

    def proofread_text(self, text):
        def chunk_text(text, chunk_size=2000):
            sentences = text.split('。')
            chunks = []
            current_chunk = []
            current_length = 0
            
            for sentence in sentences:
                if not sentence.strip():
                    continue
                sentence = sentence + '。'
                sentence_length = len(sentence)
                
                if current_length + sentence_length > chunk_size and current_chunk:
                    chunks.append(''.join(current_chunk))
                    current_chunk = [sentence]
                    current_length = sentence_length
                else:
                    current_chunk.append(sentence)
                    current_length += sentence_length
            
            if current_chunk:
                chunks.append(''.join(current_chunk))
            return chunks

        try:
            text_chunks = chunk_text(text)
            proofread_chunks = []
            total_chunks = len(text_chunks)
            
            print(f"テキストを{total_chunks}個のチャンクに分割しました")
            
            for i, chunk in enumerate(text_chunks, 1):
                print(f"チャンク {i}/{total_chunks} を処理中...")
                
                generation_config = genai.types.GenerationConfig(
                    temperature=0.3,
                    top_p=0.8,
                    top_k=40,
                    max_output_tokens=4096,
                )
                
                chunk_prompt = f'''
# あなたの目的:
ユーザーが入力したテキストを校閲します。

文字起こししたYouTubeの動画について、元の文章の意味を絶対に変更せずに文字起こしと校閲を行います。
これは{total_chunks}分割のうちの{i}番目の部分です。
文章の一貫性を保つため、前後の文脈を意識して校閲してください。

# ルール:
1.校閲した文章以外の出力は決して行ってはいけません。
2.校閲した文章のみを出力します。
3.改行の位置が不自然だった場合は文章と共に適切に改行位置も修正してください。
4.時間を意味するような表示として"(00:00)"といった記載がある場合がありますが、それは文章ではないので、文章から削除して校閲を行ってください。
5.スピーチtoテキストで文章を入力している場合、「えー」、「まあ」、「あのー」といったフィラーが含まれている場合があります。こちらも削除して校閲を行ってください。
6.テキストを出力するときには、「。」で改行を行って見やすい文章を出力してください。

テキスト:
{chunk}
'''
                try:
                    response = self.model.generate_content(
                        chunk_prompt,
                        generation_config=generation_config
                    )
                    
                    if not response or not response.text:
                        raise ValueError(f"チャンク {i}/{total_chunks} の校閲結果が空です")
                        
                    proofread_chunks.append(response.text.strip())
                    print(f"チャンク {i}/{total_chunks} の処理が完了しました")
                    
                except Exception as e:
                    print(f"チャンク {i}/{total_chunks} の処理中にエラー: {str(e)}")
                    raise
            
            # Join all proofread chunks with proper spacing
            final_text = '\n\n'.join(proofread_chunks)
            print("すべてのチャンクの処理が完了しました")
            return final_text
                
        except Exception as e:
            raise Exception(f"テキストの校閲に失敗しました: {str(e)}")

    def _extract_video_id(self, url):
        """URLからビデオIDを抽出"""
        video_id_match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', url)
        if video_id_match:
            return video_id_match.group(1)
        return None
