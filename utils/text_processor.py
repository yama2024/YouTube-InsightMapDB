import os
import logging
import time
from time import sleep
from random import uniform
import hashlib
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter
import re
from cachetools import TTLCache
from typing import Optional, Callable, List, Dict
import json
import google.generativeai as genai

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DynamicRateLimiter:
    def __init__(self):
        self.last_request = 0
        self.min_interval = 1.0
        self.backoff_multiplier = 1.0
        self.max_interval = 5.0
        self.success_count = 0
        self.error_count = 0

    def wait(self):
        now = time.time()
        elapsed = now - self.last_request
        
        # エラー率に基づいて待機時間を調整
        if self.error_count + self.success_count > 0:
            error_rate = self.error_count / (self.error_count + self.success_count)
            self.backoff_multiplier = 1.0 + (error_rate * 2.0)
        
        wait_time = max(0, self.min_interval * self.backoff_multiplier - elapsed)
        if wait_time > 0:
            time.sleep(wait_time)
        
        self.last_request = time.time()

    def report_success(self):
        self.success_count += 1
        self.backoff_multiplier = max(1.0, self.backoff_multiplier * 0.95)

    def report_error(self):
        self.error_count += 1
        self.backoff_multiplier = min(self.max_interval, self.backoff_multiplier * 1.5)

class TextProcessor:
    def __init__(self):
        self._initialize_api()
        self.rate_limiter = DynamicRateLimiter()
        self.cache = TTLCache(maxsize=100, ttl=3600)
        self.chunk_size = 1500  # チャンクサイズを1500に縮小
        self.overlap_size = 200  # オーバーラップを200に設定
        self.max_retries = 3    # リトライ回数を3回に設定
        self.backoff_factor = 2 # バックオフ係数を2に設定

    def _initialize_api(self):
        """Initialize or reinitialize the Gemini API with current environment"""
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("Gemini API key is not set in environment variables")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-1.5-pro')

    def _validate_json_response(self, response_text: str) -> Optional[Dict]:
        """Improved JSON response validation with multiple recovery attempts"""
        if not response_text:
            logger.warning("Empty response received")
            return None

        try:
            # Remove any leading/trailing non-JSON content
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            if start_idx >= 0 and end_idx > 0:
                json_str = response_text[start_idx:end_idx]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError as e:
                    logger.warning(f"Initial JSON parsing failed: {str(e)}")
                    
                    # Try to fix common JSON issues
                    json_str = json_str.replace('\n', ' ').replace('\r', '')
                    json_str = re.sub(r'(?<!\\)"(?!,|\s*}|\s*])', '\\"', json_str)
                    try:
                        return json.loads(json_str)
                    except json.JSONDecodeError:
                        logger.warning("Failed to fix JSON structure")
                        return None
            else:
                logger.warning("No JSON structure found in response")
                return None
        except Exception as e:
            logger.warning(f"Unexpected error in JSON validation: {str(e)}")
            return None

    def _process_chunk_with_retries(self, chunk: str, context: Dict) -> Optional[Dict]:
        for attempt in range(self.max_retries):
            try:
                self.rate_limiter.wait()  # レート制限を適用
                
                # チャンクの前処理とバリデーション
                if len(chunk.strip()) < 100:
                    logger.warning("チャンクが短すぎます")
                    return None
                
                # プロンプトの生成と要約処理
                response = self.model.generate_content(
                    self._create_summary_prompt(chunk, context),
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.2,
                        top_p=0.95,
                        top_k=40,
                        max_output_tokens=8192,
                    )
                )
                
                if not response.text:
                    raise ValueError("APIからの応答が空です")
                
                # JSONの解析と検証
                result = self._validate_json_response(response.text)
                if result:
                    self.rate_limiter.report_success()
                    return result
                    
                # 待機時間を計算
                wait_time = self.backoff_factor ** attempt
                logger.warning(f"Attempt {attempt + 1} failed, waiting {wait_time} seconds...")
                time.sleep(wait_time)
                
            except Exception as e:
                logger.error(f"Chunk processing error: {str(e)}")
                self.rate_limiter.report_error()
                if attempt < self.max_retries - 1:
                    wait_time = self.backoff_factor ** attempt
                    time.sleep(wait_time)
                else:
                    logger.error("All retry attempts failed")
                    return None
        
        return None

    def _split_text_into_chunks(self, text: str) -> List[str]:
        if not text:
            raise ValueError("入力テキストが空です")
            
        # 文章の前処理
        text = text.replace('\n', ' ').strip()
        text = re.sub(r'\s+', ' ', text)
        
        # テキストが最小サイズより小さい場合は単一チャンクとして返す
        if len(text) < 200:
            return [text]
        
        # 文単位での分割（句読点も考慮）
        sentences = []
        temp = ''
        for char in text:
            temp += char
            if char in ['。', '！', '？', '!', '?', '.']:
                if temp.strip():
                    sentences.append(temp.strip())
                temp = ''
        if temp.strip():
            sentences.append(temp.strip())
        
        chunks = []
        current_chunk = []
        current_length = 0
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
                
            sentence_length = len(sentence)
            
            # 1文が長すぎる場合は適切な位置で分割
            if sentence_length > self.chunk_size:
                sub_chunks = [sentence[i:i+self.chunk_size] 
                             for i in range(0, len(sentence), self.chunk_size)]
                for sub_chunk in sub_chunks:
                    if sub_chunk:
                        chunks.append(sub_chunk)
                continue
                
            # 通常のチャンク処理
            if current_length + sentence_length > self.chunk_size and current_chunk:
                chunks.append(' '.join(current_chunk))
                current_chunk = []
                current_length = 0
            
            current_chunk.append(sentence)
            current_length += sentence_length
        
        # 残りの文を処理
        if current_chunk:
            chunks.append(' '.join(current_chunk))
        
        # 最終チェック
        if not chunks:
            return [text]  # テキスト全体を1つのチャンクとして返す
        
        return chunks

    def _create_summary_prompt(self, text: str, context: Optional[Dict] = None) -> str:
        """Improved prompt with stricter JSON structure requirements"""
        context_info = ""
        if context:
            context_info = f"\nコンテキスト情報:\n{json.dumps(context, ensure_ascii=False, indent=2)}"

        prompt = f"""以下のテキストを分析し、厳密なJSON形式で構造化された要約を生成してください。

入力テキスト:
{text}
{context_info}

必須出力形式:
{{
    "概要": "150文字以内の簡潔な説明",
    "主要ポイント": [
        {{
            "タイトル": "重要なポイントの見出し",
            "説明": "具体的な説明文",
            "重要度": "1-5の数値"
        }}
    ],
    "詳細分析": [
        {{
            "セクション": "分析セクションの名称",
            "内容": "詳細な分析内容",
            "キーポイント": [
                "重要な点1",
                "重要な点2"
            ]
        }}
    ],
    "キーワード": [
        {{
            "用語": "キーワード",
            "説明": "簡潔な説明",
            "関連語": ["関連キーワード1", "関連キーワード2"]
        }}
    ]
}}

制約事項:
1. 必ず有効なJSONフォーマットを維持すること
2. すべての文字列は適切にエスケープすること
3. 数値は必ず数値型で出力すること
4. 配列は必ず1つ以上の要素を含むこと
5. 主要ポイントは3-5項目を含むこと
6. キーワードは最低3つ含むこと

注意:
- JSONフォーマット以外の装飾や説明は一切含めないでください
- 各セクションは必須です。省略しないでください
- 不正なJSON構造を避けるため、文字列内の二重引用符は必ずエスケープしてください"""

        return prompt

    def _combine_chunk_summaries(self, summaries: List[Dict]) -> Dict:
        """改善されたチャンクサマリーの統合処理"""
        if not summaries:
            raise ValueError("No valid summaries to combine")

        combined = {
            "概要": "",
            "主要ポイント": [],
            "詳細分析": [],
            "キーワード": []
        }

        # キーの存在を確認してから処理
        for summary in summaries:
            if "概要" in summary:
                combined["概要"] += summary["概要"] + " "
            
            if "主要ポイント" in summary:
                for point in summary["主要ポイント"]:
                    if isinstance(point, dict) and "タイトル" in point and "説明" in point:
                        combined["主要ポイント"].append(point)
            
            if "詳細分析" in summary:
                for analysis in summary["詳細分析"]:
                    if isinstance(analysis, dict) and "セクション" in analysis and "内容" in analysis:
                        combined["詳細分析"].append({
                            "セクション": analysis["セクション"],
                            "内容": analysis["内容"],
                            "キーポイント": analysis.get("キーポイント", [])
                        })
            
            if "キーワード" in summary:
                for keyword in summary["キーワード"]:
                    if isinstance(keyword, dict) and "用語" in keyword and "説明" in keyword:
                        combined["キーワード"].append(keyword)

        # Clean up and format
        combined["概要"] = combined["概要"].strip()[:150]
        combined["主要ポイント"] = combined["主要ポイント"][:5]

        return combined

    def generate_summary(self, text: str, progress_callback: Optional[Callable] = None) -> str:
        """Gemini APIを使用した改善された要約生成プロセス"""
        try:
            if not text:
                raise ValueError("入力テキストが空です")

            if progress_callback:
                progress_callback(0.1, "テキストを解析中...")

            # キャッシュチェック
            cache_key = hashlib.md5(text.encode()).hexdigest()
            if cache_key in self.cache:
                if progress_callback:
                    progress_callback(1.0, "✨ キャッシュから要約を取得しました")
                return self.cache[cache_key]

            # テキストを適切なサイズのチャンクに分割
            chunks = self._split_text_into_chunks(text)
            chunk_summaries = []
            failed_chunks = 0

            for i, chunk in enumerate(chunks, 1):
                if progress_callback:
                    progress = 0.1 + (0.7 * (i / len(chunks)))
                    progress_callback(progress, f"チャンク {i}/{len(chunks)} を処理中...")

                context = {
                    "total_chunks": len(chunks),
                    "current_chunk": i,
                    "chunk_position": "開始" if i == 1 else "終了" if i == len(chunks) else "中間"
                }

                chunk_summary = self._process_chunk_with_retries(chunk, context)
                
                if chunk_summary:
                    chunk_summaries.append(chunk_summary)
                else:
                    failed_chunks += 1
                    logger.warning(f"Failed to process chunk {i} after all retries")

            if not chunk_summaries:
                raise Exception("すべてのチャンクの処理に失敗しました")

            if failed_chunks > 0:
                logger.warning(f"{failed_chunks} chunks failed to process")

            if progress_callback:
                progress_callback(0.9, "要約を統合中...")

            # 最終的な要約を生成
            try:
                final_summary_data = self._combine_chunk_summaries(chunk_summaries)
            except Exception as e:
                raise Exception(f"要約の統合に失敗しました: {str(e)}")

            # Generate final summary text
            final_summary = f"# 概要\n{final_summary_data['概要']}\n\n"
            final_summary += "# 主要ポイント\n"
            for point in final_summary_data['主要ポイント']:
                if isinstance(point, dict) and "タイトル" in point and "説明" in point:
                    final_summary += f"## {point['タイトル']}\n{point['説明']}\n\n"

            final_summary += "# 詳細分析\n"
            for analysis in final_summary_data['詳細分析']:
                if isinstance(analysis, dict) and "セクション" in analysis and "内容" in analysis:
                    final_summary += f"## {analysis['セクション']}\n{analysis['内容']}\n"
                    if "キーポイント" in analysis and analysis["キーポイント"]:
                        for point in analysis["キーポイント"]:
                            final_summary += f"- {point}\n"
                    final_summary += "\n"

            final_summary += "# キーワードと重要概念\n"
            for keyword in final_summary_data['キーワード']:
                if isinstance(keyword, dict) and "用語" in keyword and "説明" in keyword:
                    final_summary += f"## {keyword['用語']}\n{keyword['説明']}\n"
                    if "関連語" in keyword and keyword["関連語"]:
                        final_summary += "関連キーワード: " + ", ".join(keyword["関連語"]) + "\n\n"

            # Cache the result
            self.cache[cache_key] = final_summary

            if progress_callback:
                progress_callback(1.0, "✨ 要約が完了しました")

            return final_summary

        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            raise Exception(f"要約の生成に失敗しました: {str(e)}")

    def get_transcript(self, youtube_url: str) -> str:
        """YouTubeの文字起こしを取得"""
        try:
            video_id = re.findall(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', youtube_url)[0]
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            transcript = transcript_list.find_transcript(['ja'])
            if not transcript:
                transcript = transcript_list.find_transcript(['ja-JP'])
            if not transcript:
                transcript = transcript_list.find_transcript(['en'])
                if transcript:
                    transcript = transcript.translate('ja')
            
            formatter = TextFormatter()
            return formatter.format_transcript(transcript.fetch())
            
        except Exception as e:
            logger.error(f"Error getting transcript: {str(e)}")
            raise Exception(f"文字起こしの取得に失敗しました: {str(e)}")
