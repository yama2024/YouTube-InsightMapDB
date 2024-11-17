from youtube_transcript_api import YouTubeTranscriptApi
import google.generativeai as genai
import re
import os

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
            # Try multiple language options in sequence
            languages_to_try = [
                ['ja'],           # Japanese
                ['ja-JP'],        # Japanese auto-generated
                ['en'],           # English
                ['en-US'],        # English auto-generated
                None             # Any available language
            ]
            
            transcript = None
            for lang in languages_to_try:
                try:
                    if lang:
                        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=lang)
                    else:
                        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
                    transcript = ' '.join([entry['text'] for entry in transcript_list])
                    break
                except Exception:
                    continue
                    
            if not transcript:
                raise Exception("この動画には字幕が設定されていません。\n字幕が設定されている動画を選択してください。")
                
            return transcript
            
        except Exception as e:
            error_msg = f"文字起こしの取得に失敗しました: {str(e)}"
            print(error_msg)  # For debugging
            raise Exception(error_msg)

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
        try:
            # Process entire text at once first
            generation_config = genai.types.GenerationConfig(
                temperature=0.3,
                top_p=0.8,
                top_k=40,
                max_output_tokens=8192,  # Increased token limit
            )
            
            prompt = f'''
# あなたの目的:
ユーザーが入力したテキストを校閲します。

文字起こししたYouTubeの動画について、元の文章の意味を絶対に変更せずに文字起こしと校閲を行います。
入力されたすべてのテキストを必ず完全に校閲して出力してください。

# ルール:
1.校閲した文章以外の出力は決して行ってはいけません。
2.校閲した文章のみを出力します。
3.改行の位置が不自然だった場合は文章と共に適切に改行位置も修正してください。
4.時間を意味するような表示として"(00:00)"といった記載がある場合がありますが、それは文章ではないので、文章から削除して校閲を行ってください。
5.スピーチtoテキストで文章を入力している場合、「えー」、「まあ」、「あのー」といったフィラーが含まれている場合があります。こちらも削除して校閲を行ってください。
6.テキストを出力するときには、「。」で改行を行って見やすい文章を出力してください。
7.入力されたテキストをすべて校閲して出力してください。一部だけの校閲は許可されません。

テキスト:
{text}
'''
            response = self.model.generate_content(
                prompt,
                generation_config=generation_config
            )
            
            if not response.text:
                raise ValueError("校閲結果が空です")
                
            return response.text.strip()
                
        except Exception as e:
            raise Exception(f"テキストの校閲に失敗しました: {str(e)}")

    def _extract_video_id(self, url):
        """URLからビデオIDを抽出"""
        video_id_match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', url)
        if video_id_match:
            return video_id_match.group(1)
        return None