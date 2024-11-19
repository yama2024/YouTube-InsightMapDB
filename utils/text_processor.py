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

    def _chunk_text(self, text: str, chunk_size: int = 1500, overlap: int = 200) -> List[str]:
        if not text:
            return []
            
        # Split into sentences first
        sentences = re.split('([。!?！？]+)', text)
        sentences = [''.join(i) for i in zip(sentences[0::2], sentences[1::2])]
        
        chunks = []
        current_chunk = []
        current_length = 0
        
        for sentence in sentences:
            sentence_length = len(sentence)
            
            if current_length + sentence_length > chunk_size:
                if current_chunk:
                    chunks.append(''.join(current_chunk))
                    # Keep last sentence for overlap
                    current_chunk = current_chunk[-1:] if overlap > 0 else []
                    current_length = sum(len(s) for s in current_chunk)
                
            current_chunk.append(sentence)
            current_length += sentence_length
            
        if current_chunk:
            chunks.append(''.join(current_chunk))
            
        return chunks

    def generate_summary(self, text: str) -> str:
        """Generate summary with improved chunking and error handling"""
        try:
            # Smaller chunks for better processing
            chunk_size = 800  # Reduced from 1500
            overlap = 100
            chunks = self._chunk_text(text, chunk_size, overlap)
            
            summaries = []
            for i, chunk in enumerate(chunks):
                try:
                    # Add delay between chunks
                    if i > 0:
                        time.sleep(2)
                    
                    prompt = f'''
                    以下のテキストを要約してください：
                    
                    {chunk}
                    
                    ポイント：
                    - 重要な情報を保持
                    - 簡潔に表現
                    - 文脈を維持
                    '''
                    
                    # Improved retry logic
                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            logger.info(f"チャンク {i+1}/{len(chunks)} の処理を試行中 (試行 {attempt+1}/{max_retries})")
                            response = self.model.generate_content(
                                prompt,
                                generation_config=genai.types.GenerationConfig(
                                    temperature=0.3,
                                    top_p=0.8,
                                    top_k=40,
                                    max_output_tokens=1024,
                                )
                            )
                            
                            if response and response.text:
                                summaries.append(response.text.strip())
                                logger.info(f"チャンク {i+1} の要約が成功しました")
                                break
                            
                        except Exception as e:
                            logger.warning(f"チャンク {i+1} の処理中にエラーが発生 (試行 {attempt+1}): {str(e)}")
                            if attempt < max_retries - 1:
                                wait_time = (2 ** attempt) + 1  # Exponential backoff
                                logger.info(f"再試行まで {wait_time} 秒待機します")
                                time.sleep(wait_time)
                                continue
                            raise
                            
                except Exception as e:
                    logger.error(f"チャンク {i+1} の処理に失敗: {str(e)}")
                    continue

            if not summaries:
                logger.error("要約の生成に失敗: 有効な要約が生成されませんでした")
                raise ValueError("要約を生成できませんでした")
            
            # Combine summaries with better formatting
            logger.info("個別の要約を結合して最終要約を生成します")
            combined = "\n\n".join(summaries)
            final_prompt = f'''
            以下の要約をさらに整理して、簡潔にまとめてください：
            
            {combined}
            '''
            
            # Final summary with retry
            for attempt in range(3):
                try:
                    logger.info(f"最終要約の生成を試行中 (試行 {attempt+1}/3)")
                    final_response = self.model.generate_content(
                        final_prompt,
                        generation_config=genai.types.GenerationConfig(
                            temperature=0.3,
                            top_p=0.8,
                            top_k=40,
                            max_output_tokens=1024,
                        )
                    )
                    if final_response and final_response.text:
                        logger.info("最終要約の生成が完了しました")
                        return final_response.text.strip()
                except Exception as e:
                    logger.warning(f"最終要約の生成中にエラーが発生 (試行 {attempt+1}): {str(e)}")
                    if attempt < 2:
                        wait_time = 2 ** attempt
                        logger.info(f"再試行まで {wait_time} 秒待機します")
                        time.sleep(wait_time)
                        continue
                    raise

            logger.error("最終要約の生成に失敗しました")
            raise ValueError("最終要約の生成に失敗しました")
            
        except Exception as e:
            logger.error(f"要約生成エラー: {str(e)}")
            raise Exception(f"要約の生成に失敗しました: {str(e)}")

    def proofread_text(self, text: str, progress_callback=None) -> str:
        """Proofread and enhance text readability with progress tracking"""
        if not text:
            return ""
            
        try:
            if progress_callback:
                progress_callback(0.1, "🔍 テキスト解析を開始")
            
            # Initial text cleaning with detailed progress
            cleaning_steps = {
                0.15: "📝 フィラーワードを除去中...",
                0.20: "🔤 文字の正規化を実行中...",
                0.25: "📊 タイムスタンプを処理中...",
                0.30: "✨ 不要な記号を削除中..."
            }
            
            for progress, message in cleaning_steps.items():
                if progress_callback:
                    progress_callback(progress, message)
                time.sleep(0.3)  # Visual feedback
            
            text = self._clean_text(text, lambda p, m: progress_callback(0.3 + p * 0.2, m) if progress_callback else None)
            
            if progress_callback:
                progress_callback(0.5, "🤖 AIモデルによる文章校正を準備中...")
            
            # AI Processing steps
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
                progress_callback(0.6, "🧠 AIによる文章解析中...")
                time.sleep(0.3)
                progress_callback(0.7, "📝 文章の校正を実行中...")
            
            response = self.model.generate_content(prompt)
            if not response.text:
                logger.error("AIモデルからの応答が空でした")
                if progress_callback:
                    progress_callback(1.0, "❌ エラー: AIモデルからの応答が空です")
                return text
            
            if progress_callback:
                progress_callback(0.8, "🎨 文章の最終調整中...")
            
            enhanced_text = response.text
            enhanced_text = self._clean_text(enhanced_text)
            
            if progress_callback:
                progress_callback(0.9, "📊 文章構造を最適化中...")
            
            enhanced_text = self._improve_sentence_structure(enhanced_text)
            enhanced_text = re.sub(r'([。])', r'\1\n', enhanced_text)
            enhanced_text = re.sub(r'\n{3,}', '\n\n', enhanced_text)
            enhanced_text = enhanced_text.strip()
            
            if progress_callback:
                progress_callback(1.0, "✨ 校正処理が完了しました!")
            
            return enhanced_text
            
        except Exception as e:
            logger.error(f"テキストの校正中にエラーが発生しました: {str(e)}")
            if progress_callback:
                progress_callback(1.0, f"❌ エラー: {str(e)}")
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
            
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['ja', 'ja-JP', 'en'])
            transcript = ' '.join([entry['text'] for entry in transcript_list])
            
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
                r'(?:watch\?v=|/v/|youtu\.be/)([^&?/]+)'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, url)
                if match:
                    return match.group(1)
            return None
            
        except Exception as e:
            logger.error(f"動画ID抽出エラー: {str(e)}")
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