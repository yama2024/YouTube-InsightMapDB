from youtube_transcript_api import YouTubeTranscriptApi
import google.generativeai as genai
import re
import os
import tempfile
import pytube

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
                transcript = self._get_subtitles(video_id)
                if transcript:
                    return transcript
            except Exception as e:
                print(f"字幕の取得に失敗しました: {str(e)}")
            
            # If subtitles not available, use Gemini for transcription
            try:
                # Download audio
                yt = pytube.YouTube(url)
                audio_stream = yt.streams.filter(only_audio=True).first()
                
                # Create temp directory and save audio
                with tempfile.TemporaryDirectory() as temp_dir:
                    audio_path = os.path.join(temp_dir, "audio.mp4")
                    audio_stream.download(filename=audio_path)
                    
                    # Use Gemini for transcription
                    with open(audio_path, "rb") as audio_file:
                        prompt = f'''
                        このYouTube動画の音声を文字起こししてください。
                        できるだけ正確に、文章として自然な形で出力してください。
                        フィラー（えー、あの、など）は除外してください。
                        タイムスタンプは除外してください。
                        句読点を適切に使用してください。
                        '''
                        response = self.model.generate_content([
                            {
                                "parts": [
                                    {"text": prompt},
                                    {"audio": audio_file}
                                ]
                            }
                        ])
                        
                        if response and response.text:
                            return response.text
                        else:
                            raise Exception("音声認識に失敗しました")
                    
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
            return response.text
        except Exception as e:
            raise Exception("要約の生成に失敗しました")

    def proofread_text(self, text):
        def chunk_text(text, chunk_size=1000):
            # Split text into sentences
            sentences = text.split('。')
            chunks = []
            current_chunk = []
            current_length = 0
            
            for sentence in sentences:
                if not sentence.strip():
                    continue
                
                # Add period back if it was removed by split
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
            # Split text into manageable chunks
            text_chunks = chunk_text(text)
            proofread_chunks = []
            
            for i, chunk in enumerate(text_chunks, 1):
                generation_config = genai.types.GenerationConfig(
                    temperature=0.3,
                    top_p=0.8,
                    top_k=40,
                    max_output_tokens=2048,
                )
                
                safety_settings = {
                    "HARM_CATEGORY_DANGEROUS": "BLOCK_NONE"
                }
                
                chunk_prompt = f"""
# あなたの目的:
ユーザーが入力したテキストを校閲します。

文字起こししたYouTubeの動画について、元の文章の意味を絶対に変更せずに文字起こしと校閲を行います。
あなたが文脈として不自然と感じた文章は全て誤字脱字が含まれており、正確に修正する必要があります。
ステップバイステップで思考しながら校閲を行い、正確に修正して文章を出力してください。

# ルール:
1.校閲した文章以外の出力は決して行ってはいけません。
2.校閲した文章のみを出力します。
3.改行の位置が不自然だった場合は文章と共に適切に改行位置も修正してください。
4.時間を意味するような表示として"(00:00)"といった記載がある場合がありますが、それは文章ではないので、文章から削除して校閲を行ってください。
5.スピーチtoテキストで文章を入力している場合、「えー」、「まあ」、「あのー」といったフィラーが含まれている場合があります。こちらも削除して校閲を行ってください。
6.テキストを出力するときには、「。」で改行を行って見やすい文章を出力してください。

テキスト:
{chunk}
"""
                
                response = self.model.generate_content(
                    chunk_prompt,
                    generation_config=generation_config,
                    safety_settings=safety_settings
                )
                
                if not response.text:
                    raise ValueError(f"チャンク {i} の校閲結果が空です")
                    
                proofread_chunks.append(response.text)
                
            # Combine all proofread chunks
            final_text = '\n'.join(proofread_chunks)
            return final_text
                
        except Exception as e:
            raise Exception(f"テキストの校閲に失敗しました: {str(e)}")

    def _extract_video_id(self, url):
        """URLからビデオIDを抽出"""
        video_id_match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', url)
        if video_id_match:
            return video_id_match.group(1)
        return None
