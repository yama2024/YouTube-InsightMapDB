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

    def proofread_text(self, text: str, progress_callback=None) -> str:
        """Proofread and enhance text readability with progress tracking"""
        if not text:
            return ""
            
        try:
            if progress_callback:
                progress_callback(0.1, "校正処理を開始")
            
            # Initial text cleaning
            text = self._clean_text(text, lambda p, m: progress_callback(p * 0.3, m) if progress_callback else None)
            
            if progress_callback:
                progress_callback(0.4, "AIによる文章校正を実行中")
            
            prompt = f"""
# あなたの目的:
「Original Transcript」のテキストを全文校閲します。

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

入力テキスト：
{text}
"""
            
            if progress_callback:
                progress_callback(0.6, "AIモデルからの応答を処理中")
            
            response = self.model.generate_content(prompt)
            if not response.text:
                logger.error("AIモデルからの応答が空でした")
                return text
            
            if progress_callback:
                progress_callback(0.8, "最終的な文章の整形中")
            
            enhanced_text = response.text
            enhanced_text = self._clean_text(enhanced_text)
            enhanced_text = self._improve_sentence_structure(enhanced_text)
            enhanced_text = re.sub(r'([。])', r'\1\n', enhanced_text)
            enhanced_text = re.sub(r'\n{3,}', '\n\n', enhanced_text)
            enhanced_text = enhanced_text.strip()
            
            if progress_callback:
                progress_callback(1.0, "校正処理が完了しました")
            
            return enhanced_text
            
        except Exception as e:
            logger.error(f"テキストの校正中にエラーが発生しました: {str(e)}")
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
            logger.error(f"文章構造の改善中にエラーが発生しました: {str(e)}")
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
            
            transcript = self._get_subtitles_with_priority(video_id)
            if not transcript:
                raise ValueError("字幕を取得できませんでした。動画に字幕が設定されていないか、アクセスできない可能性があります。")
            
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
            logger.error(f"Video ID抽出エラー: {str(e)}")
            return None

    def _get_subtitles_with_priority(self, video_id: str) -> Optional[str]:
        """Get subtitles with enhanced error handling and caching"""
        try:
            logger.debug(f"字幕取得を開始: video_id={video_id}")
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            logger.debug(f"TranscriptList オブジェクトの型: {type(transcript_list)}")
            
            transcript = None
            error_messages = []
            
            # Try Japanese subtitles first with detailed error logging
            for lang in ['ja', 'ja-JP']:
                try:
                    logger.debug(f"{lang}の手動作成字幕を検索中...")
                    transcript = transcript_list.find_manually_created_transcript([lang])
                    logger.info(f"{lang}の手動作成字幕が見つかりました")
                    break
                except Exception as e:
                    error_messages.append(f"{lang}の手動作成字幕の取得に失敗: {str(e)}")
                    try:
                        logger.debug(f"{lang}の自動生成字幕を検索中...")
                        transcript = transcript_list.find_generated_transcript([lang])
                        logger.info(f"{lang}の自動生成字幕が見つかりました")
                        break
                    except Exception as e:
                        error_messages.append(f"{lang}の自動生成字幕の取得に失敗: {str(e)}")

            # Fallback to English if Japanese is not available
            if not transcript:
                logger.debug("日本語字幕が見つからないため、英語字幕を検索中...")
                try:
                    transcript = transcript_list.find_manually_created_transcript(['en'])
                    logger.info("英語の手動作成字幕が見つかりました")
                except Exception as e:
                    error_messages.append(f"英語の手動作成字幕の取得に失敗: {str(e)}")
                    try:
                        transcript = transcript_list.find_generated_transcript(['en'])
                        logger.info("英語の自動生成字幕が見つかりました")
                    except Exception as e:
                        error_messages.append(f"英語の自動生成字幕の取得に失敗: {str(e)}")

            if not transcript:
                error_detail = "\n".join(error_messages)
                logger.error(f"利用可能な字幕が見つかりませんでした:\n{error_detail}")
                return None

            # Process transcript segments with improved timing and logging
            try:
                transcript_data = transcript.fetch()
                logger.debug(f"取得した字幕データの型: {type(transcript_data)}")
                
                if not isinstance(transcript_data, list):
                    raise ValueError("字幕データが予期しない形式です")
                
                # Process transcript segments with improved timing and logging
                transcript_segments = []
                current_segment = []
                current_time = 0
                
                for entry in transcript_data:
                    if not isinstance(entry, dict):
                        logger.warning(f"不正な字幕エントリ形式: {type(entry)}")
                        continue
                        
                    text = entry.get('text', '').strip()
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
                    logger.warning("有効な字幕セグメントが見つかりませんでした")
                    return None
                    
                return '\n'.join(transcript_segments)

            except Exception as e:
                logger.error(f"字幕データの処理中にエラーが発生しました: {str(e)}")
                return None

        except Exception as e:
            error_msg = f"字幕の取得に失敗しました: {str(e)}"
            logger.error(error_msg)
            return None

    def generate_summary(self, text: str) -> str:
        """Generate summary with improved error handling"""
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
            logger.error(f"要約の生成中にエラーが発生しました: {str(e)}")
            return "要約の生成中にエラーが発生しました。"