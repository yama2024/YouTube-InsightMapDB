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
        self.base_interval = 1.0  # 基本待機時間（秒）
        self.response_times = []
        self.max_samples = 10
        self.backoff_factor = 1.5

    def update_interval(self, response_time: float):
        """応答時間に基づいて待機時間を動的に調整"""
        self.response_times.append(response_time)
        if len(self.response_times) > self.max_samples:
            self.response_times.pop(0)
        
        # 直近の応答時間の平均に基づいて基本待機時間を調整
        if self.response_times:
            avg_response_time = sum(self.response_times) / len(self.response_times)
            self.base_interval = max(1.0, min(5.0, avg_response_time * self.backoff_factor))

    def wait(self):
        """動的な待機時間を適用"""
        now = time.time()
        elapsed = now - self.last_request
        if elapsed < self.base_interval:
            sleep_time = self.base_interval - elapsed + uniform(0.1, 0.5)
            sleep(sleep_time)
        self.last_request = time.time()

class TextProcessor:
    def __init__(self):
        self._initialize_api()
        self.rate_limiter = DynamicRateLimiter()
        # Initialize cache with 1-hour TTL
        self.cache = TTLCache(maxsize=100, ttl=3600)
        self.chunk_size = 4000  # Initial chunk size
        self.max_retries = 5
        self.json_validation_retries = 3

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
        remaining_retries = self.json_validation_retries
        last_error = None
        
        while remaining_retries > 0:
            try:
                start_time = time.time()
                
                # チャンクの前処理
                if len(chunk.strip()) < 100:
                    return {
                        "概要": chunk,
                        "主要ポイント": [{"タイトル": "概要", "説明": chunk, "重要度": 3}],
                        "詳細分析": [{"セクション": "概要", "内容": chunk, "キーポイント": [chunk]}],
                        "キーワード": [{"用語": "概要", "説明": chunk, "関連語": []}]
                    }
                
                def process_single_chunk():
                    prompt = self._create_summary_prompt(chunk, context)
                    self.rate_limiter.wait()  # レート制限を適用
                    response = self.model.generate_content(
                        prompt,
                        generation_config=genai.types.GenerationConfig(
                            temperature=0.2,
                            top_p=0.95,
                            top_k=40,
                            max_output_tokens=8192,
                        )
                    )
                    return response.text

                # チャンク処理の実行
                chunk_response = process_single_chunk()
                
                # レスポンスの検証
                if not chunk_response:
                    raise ValueError("Empty response received")
                
                # JSON解析
                parsed_response = self._validate_json_response(chunk_response)
                if parsed_response:
                    required_fields = ["概要", "主要ポイント", "詳細分析", "キーワード"]
                    if all(field in parsed_response for field in required_fields):
                        return parsed_response
                
                remaining_retries -= 1
                if remaining_retries > 0:
                    logger.warning(f"Retry attempt {self.json_validation_retries - remaining_retries}")
                    sleep(1 * (self.json_validation_retries - remaining_retries))
                
            except Exception as e:
                error_msg = str(e).lower()
                if "quota" in error_msg:
                    try:
                        self._initialize_api()
                        continue
                    except Exception as key_error:
                        raise Exception(f"APIキーの更新に失敗しました: {str(key_error)}")
                
                last_error = e
                remaining_retries -= 1
                if remaining_retries > 0:
                    wait_time = (2 ** (self.json_validation_retries - remaining_retries)) + uniform(0, 1)
                    logger.warning(f"Error during chunk processing: {str(e)}, retrying in {wait_time:.2f} seconds...")
                    sleep(wait_time)
        
        error_message = str(last_error) if last_error else "Unknown error"
        logger.error(f"Failed to process chunk after all retries: {error_message}")
        return None

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

    def _split_text_into_chunks(self, text: str) -> List[str]:
        """テキストを適切なサイズのチャンクに分割"""
        chunks = []
        current_chunk = ""
        current_size = 0
        
        # 文章単位で分割（。や！や？で区切る）
        sentences = re.split(r'([。！？])', text)
        
        for i in range(0, len(sentences)-1, 2):
            sentence = sentences[i] + (sentences[i+1] if i+1 < len(sentences) else '')
            sentence_size = len(sentence)
            
            if current_size + sentence_size > self.chunk_size:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = sentence
                current_size = sentence_size
            else:
                current_chunk += sentence
                current_size += sentence_size
        
        if current_chunk:
            chunks.append(current_chunk)
            
        return chunks

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
            
            try:
                transcript = transcript_list.find_transcript(['ja'])
            except:
                transcript = transcript_list.find_transcript(['en'])
                transcript = transcript.translate('ja')
            
            formatted_transcript = TextFormatter().format_transcript(transcript.fetch())
            return formatted_transcript
            
        except Exception as e:
            logger.error(f"Error getting transcript: {str(e)}")
            raise Exception(f"文字起こしの取得に失敗しました: {str(e)}")