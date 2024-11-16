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
        """YouTubeの文字起こしを取得"""
        video_id = self._extract_video_id(url)
        if not video_id:
            raise Exception("無効なYouTube URLです")
        
        try:
            # First try with Japanese
            try:
                transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['ja'])
            except Exception:
                # If Japanese fails, try with auto-generated Japanese
                try:
                    transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['ja-JP'])
                except Exception:
                    # If that fails too, try getting any transcript and translate
                    try:
                        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
                    except Exception as e:
                        raise Exception("この動画の字幕は利用できません")
                    
            return ' '.join([entry['text'] for entry in transcript_list])
            
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
        """テキストを校閲して整形"""
        prompt = f"""
        以下のテキストを校閲して、読みやすく整形してください：
        - 句読点や改行を適切に追加
        - 誤字脱字を修正
        - 話し言葉を書き言葉に修正
        - 文章の構造を整理
        
        テキスト:
        {text}
        """
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            raise Exception("テキストの校閲に失敗しました")

    def _extract_video_id(self, url):
        """URLからビデオIDを抽出"""
        video_id_match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', url)
        if video_id_match:
            return video_id_match.group(1)
        return None
