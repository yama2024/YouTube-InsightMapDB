import logging
from youtube_transcript_api import YouTubeTranscriptApi
import google.generativeai as genai
import re
import os
import time
from typing import List, Optional, Dict, Any, Tuple
from retrying import retry
from cachetools import TTLCache, cached
import json

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
        self.summary_cache = TTLCache(maxsize=100, ttl=3600)  # 1 hour TTL for summaries
        
        # Maximum chunk size for text processing (in characters)
        self.max_chunk_size = 8000
        
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

    def _chunk_text(self, text: str) -> List[str]:
        """Split text into manageable chunks"""
        sentences = re.split(r'([。！？])', text)
        chunks = []
        current_chunk = ""
        
        for i in range(0, len(sentences), 2):
            sentence = sentences[i] + (sentences[i+1] if i+1 < len(sentences) else '')
            if len(current_chunk) + len(sentence) <= self.max_chunk_size:
                current_chunk += sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = sentence
        
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks

    def generate_summary(self, text: str) -> str:
        """Generate a summary of the input text using Gemini 1.5 Pro with enhanced error handling and validation"""
        logger.info("要約生成を開始します")
        
        try:
            # Input validation
            is_valid, error_msg = self._validate_text(text)
            if not is_valid:
                raise ValueError(f"入力テキストが無効です: {error_msg}")
            
            # Check cache first
            cache_key = hash(text)
            cached_summary = self.summary_cache.get(cache_key)
            if cached_summary:
                logger.info("キャッシュされた要約を使用します")
                return cached_summary

            # Clean and chunk the text
            cleaned_text = self._clean_text(text)
            text_chunks = self._chunk_text(cleaned_text)
            logger.info(f"テキストを{len(text_chunks)}チャンクに分割しました")

            chunk_summaries = []
            for i, chunk in enumerate(text_chunks):
                logger.info(f"チャンク {i+1}/{len(text_chunks)} の処理を開始")
                
                # Prepare the prompt for this chunk
                prompt = f"""
                # 目的と背景
                このテキストはYouTube動画の文字起こしの一部です ({i+1}/{len(text_chunks)})。
                視聴者が内容を効率的に理解できるよう、包括的な要約を生成します。

                # 要約のガイドライン
                1. このチャンクの重要なポイントを簡潔に要約
                2. 専門用語や技術的な概念は以下のように扱う：
                   - 初出時に簡潔な説明を付記
                   - 可能な場合は平易な言葉で言い換え
                   - 重要な専門用語は文脈を保持

                # 入力テキスト：
                {chunk}
                """

                # Generate summary for this chunk with enhanced error handling
                for attempt in range(3):
                    try:
                        response = self.model.generate_content(prompt)
                        if not response or not response.text:
                            raise ValueError("AIモデルからの応答が空でした")
                        
                        chunk_summaries.append(response.text.strip())
                        break
                        
                    except Exception as e:
                        if "429" in str(e) or "Resource has been exhausted" in str(e):
                            logger.error(f"API制限に達しました: {str(e)}")
                            wait_time = min(32, (2 ** attempt) * 5)  # Longer backoff, max 32 seconds
                            logger.info(f"待機中... {wait_time}秒")
                            time.sleep(wait_time)
                            if attempt == 2:
                                raise ValueError("API制限に達しました。しばらく待ってから再試行してください。")
                        elif "blocked" in str(e).lower():
                            logger.error(f"プロンプトがブロックされました: {str(e)}")
                            raise ValueError("不適切なコンテンツが検出されました")
                        else:
                            logger.warning(f"生成エラー (試行 {attempt + 1}/3): {str(e)}")
                            if attempt == 2:  # Last attempt
                                raise ValueError(f"要約の生成に失敗しました: {str(e)}")
                            wait_time = min(32, (2 ** attempt) * 5)  # Longer backoff, max 32 seconds
                            time.sleep(wait_time)

            # Combine chunk summaries into final summary
            if chunk_summaries:
                combined_summary = self._combine_summaries(chunk_summaries)
                self.summary_cache[cache_key] = combined_summary
                logger.info("要約の生成が正常に完了しました")
                return combined_summary
            else:
                raise ValueError("チャンクの要約生成に失敗しました")

        except Exception as e:
            error_msg = f"要約生成中にエラーが発生しました: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)

    def _combine_summaries(self, chunk_summaries: List[str]) -> str:
        """Combine multiple chunk summaries into a coherent final summary"""
        if not chunk_summaries:
            return ""

        try:
            combine_prompt = f"""
            # 目的
            複数のテキストチャンクの要約を1つの包括的な要約にまとめます。

            # 出力フォーマット
            以下の構造で最終的な要約を作成してください：

            # 概要
            [全体の要点を2-3文で簡潔に説明]

            ## 主なポイント
            • [重要なポイント1 - 具体的な例や数値を含める]
            • [重要なポイント2 - 技術用語がある場合は説明を付記]
            • [重要なポイント3 - 実践的な示唆や応用点を含める]

            ## 詳細な解説
            [本文の詳細な解説]

            ## まとめ
            [主要な発見や示唆を1-2文で結論付け]

            # 入力テキスト（チャンク要約）：
            {' '.join(chunk_summaries)}
            """

            for attempt in range(3):
                try:
                    response = self.model.generate_content(combine_prompt)
                    if not response or not response.text:
                        raise ValueError("AIモデルからの応答が空でした")
                    
                    final_summary = response.text.strip()
                    is_valid, error_msg = self._validate_summary_response(final_summary)
                    if not is_valid:
                        raise ValueError(f"生成された要約が無効です: {error_msg}")
                    
                    return final_summary

                except Exception as e:
                    if "429" in str(e) or "Resource has been exhausted" in str(e):
                        logger.error(f"API制限に達しました: {str(e)}")
                        wait_time = min(32, (2 ** attempt) * 5)
                        time.sleep(wait_time)
                        if attempt == 2:
                            raise ValueError("API制限に達しました。しばらく待ってから再試行してください。")
                    else:
                        logger.warning(f"要約の結合中にエラーが発生 (試行 {attempt + 1}/3): {str(e)}")
                        if attempt == 2:
                            raise
                        wait_time = min(32, (2 ** attempt) * 5)
                        time.sleep(wait_time)

        except Exception as e:
            logger.error(f"要約の結合中にエラーが発生しました: {str(e)}")
            raise ValueError(f"要約の結合に失敗しました: {str(e)}")

    def _validate_text(self, text: str) -> Tuple[bool, str]:
        """Validate input text and return validation status and error message"""
        try:
            if not text:
                return False, "入力テキストが空です"
            
            # Check minimum length (100 characters)
            if len(text) < 100:
                return False, "テキストが短すぎます（最小100文字必要）"
            
            # Validate text encoding
            try:
                text.encode('utf-8').decode('utf-8')
            except UnicodeError:
                return False, "テキストのエンコーディングが無効です"
            
            # Check for excessive noise or invalid patterns
            noise_ratio = len(re.findall(r'[^\w\s。、！？」』）「『（]', text)) / len(text)
            if noise_ratio > 0.3:  # More than 30% noise characters
                return False, "テキストにノイズが多すぎます"
            
            return True, ""
        except Exception as e:
            logger.error(f"テキスト検証中にエラーが発生: {str(e)}")
            return False, f"テキスト検証エラー: {str(e)}"

    def _validate_summary_response(self, response: str) -> Tuple[bool, str]:
        """Validate the generated summary response"""
        try:
            if not response:
                return False, "生成された要約が空です"
            
            # Check for required sections
            required_sections = ['概要', '主なポイント', '詳細な解説', 'まとめ']
            for section in required_sections:
                if section not in response:
                    return False, f"必要なセクション '{section}' が見つかりません"
            
            # Check for minimum content length in each section
            sections_content = re.split(r'#{1,2}\s+(?:概要|主なポイント|詳細な解説|まとめ)', response)
            if any(len(section.strip()) < 50 for section in sections_content[1:]):
                return False, "一部のセクションの内容が不十分です"
            
            # Verify bullet points in main points section
            main_points_match = re.search(r'##\s*主なポイント\n(.*?)(?=##|$)', response, re.DOTALL)
            if main_points_match:
                main_points = main_points_match.group(1)
                if len(re.findall(r'•|\*|\-', main_points)) < 2:
                    return False, "主なポイントの箇条書きが不十分です"
            
            return True, ""
        except Exception as e:
            logger.error(f"要約の検証中にエラーが発生: {str(e)}")
            return False, f"要約の検証エラー: {str(e)}"

    def generate_summary(self, text: str) -> str:
        """Generate a summary of the input text using Gemini 1.5 Pro with enhanced error handling and validation"""
        logger.info("要約生成を開始します")
        
        try:
            # Input validation
            is_valid, error_msg = self._validate_text(text)
            if not is_valid:
                raise ValueError(f"入力テキストが無効です: {error_msg}")
            
            # Check cache first
            cache_key = hash(text)
            cached_summary = self.summary_cache.get(cache_key)
            if cached_summary:
                logger.info("キャッシュされた要約を使用します")
                return cached_summary

            # Clean the text before summarization
            logger.debug("テキストのクリーニングを開始")
            cleaned_text = self._clean_text(text)
            
            # Prepare the enhanced prompt
            prompt = f"""
# 目的と背景
このテキストはYouTube動画の文字起こしから生成されたものです。
視聴者が内容を効率的に理解できるよう、包括的な要約を生成します。

# 要約のガイドライン
1. コンテンツの重要なポイントを漏らさず、簡潔に要約
2. 専門用語や技術的な概念は以下のように扱う：
   - 初出時に簡潔な説明を付記
   - 可能な場合は平易な言葉で言い換え
   - 重要な専門用語は文脈を保持
3. 階層的な構造で情報を整理：
   - メインテーマから詳細へと展開
   - 関連する概念をグループ化
4. 読みやすさの確保：
   - 適切な見出しレベルを使用
   - 箇条書きと段落を効果的に組み合わせ
   - 論理的な流れを維持

# 出力フォーマット
以下の構造で要約を作成してください：

# 概要
[全体の要点を2-3文で簡潔に説明]

## 主なポイント
• [重要なポイント1 - 具体的な例や数値を含める]
• [重要なポイント2 - 技術用語がある場合は説明を付記]
• [重要なポイント3 - 実践的な示唆や応用点を含める]

## 詳細な解説
[本文の詳細な解説：
- 重要な概念の詳細な説明
- 具体例や事例の紹介
- 技術的な詳細（必要な場合）
- 関連する背景情報]

## まとめ
[主要な発見や示唆を1-2文で結論付け
実践的な応用や今後の展望を示唆]

# 入力テキスト：
{cleaned_text}
"""
            logger.debug("Gemini APIにリクエストを送信")
            
            # Generate summary with retry mechanism
            for attempt in range(3):
                try:
                    response = self.model.generate_content(prompt)
                    if not response or not response.text:
                        raise ValueError("AIモデルからの応答が空でした")
                    
                    summary = response.text.strip()
                    
                    # Validate the generated summary
                    is_valid, error_msg = self._validate_summary_response(summary)
                    if not is_valid:
                        raise ValueError(f"生成された要約が無効です: {error_msg}")
                    
                    # Cache the validated summary
                    self.summary_cache[cache_key] = summary
                    logger.info("要約の生成が正常に完了しました")
                    return summary
                    
                except genai.types.generation_types.BlockedPromptException as e:
                    logger.error(f"プロンプトがブロックされました: {str(e)}")
                    raise ValueError("不適切なコンテンツが検出されました")
                    
                except Exception as e:
                    if "blocked" in str(e).lower():
                        logger.error(f"プロンプトがブロックされました: {str(e)}")
                        raise ValueError("不適切なコンテンツが検出されました")
                    else:
                        logger.warning(f"生成エラー (試行 {attempt + 1}/3): {str(e)}")
                        if attempt == 2:  # Last attempt
                            raise ValueError(f"要約の生成に失敗しました: {str(e)}")
                        time.sleep(2 ** attempt)  # Exponential backoff
                    
                except Exception as e:
                    logger.error(f"予期しないエラーが発生 (試行 {attempt + 1}/3): {str(e)}")
                    if attempt == 2:  # Last attempt
                        raise
                    time.sleep(2 ** attempt)
            
        except Exception as e:
            error_msg = f"要約生成中にエラーが発生しました: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)

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