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
        self.chunk_size = 4000  # Reduced chunk size for better reliability
        self.max_retries = 5  # Increased from 3 to 5
        self.json_validation_retries = 3  # Increased from 2 to 3

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

    def _process_chunk_with_retries(self, chunk: str, context: Dict) -> Optional[Dict]:
        """Enhanced chunk processing with improved validation and error handling"""
        remaining_retries = self.json_validation_retries
        last_error = None

        while remaining_retries > 0:
            try:
                def process_single_chunk():
                    prompt = self._create_summary_prompt(chunk, context)
                    response = self.model.generate_content(
                        prompt,
                        generation_config=genai.types.GenerationConfig(
                            temperature=0.2,  # Reduced for more consistent output
                            top_p=0.95,
                            top_k=40,
                            max_output_tokens=8192,
                        )
                    )
                    return response.text

                chunk_response = self._retry_with_backoff(process_single_chunk)
                
                # Validate JSON response
                parsed_response = self._validate_json_response(chunk_response)
                if parsed_response:
                    # Verify required fields
                    required_fields = ["概要", "主要ポイント", "詳細分析", "キーワード"]
                    if all(field in parsed_response for field in required_fields):
                        return parsed_response
                    else:
                        logger.warning("Response missing required fields")
                        missing_fields = [f for f in required_fields if f not in parsed_response]
                        logger.warning(f"Missing fields: {', '.join(missing_fields)}")
                
                remaining_retries -= 1
                if remaining_retries > 0:
                    logger.warning(f"Retry attempt {self.json_validation_retries - remaining_retries}: Invalid or incomplete response")
                    sleep(1 * (self.json_validation_retries - remaining_retries))
                
            except Exception as e:
                error_msg = str(e).lower()
                if "quota" in error_msg:
                    logger.error("API quota exceeded, attempting to refresh API key")
                    try:
                        self._initialize_api()
                        continue
                    except Exception as key_error:
                        raise Exception(f"API key refresh failed: {str(key_error)}")
                
                last_error = e
                remaining_retries -= 1
                if remaining_retries > 0:
                    logger.warning(f"Error during chunk processing: {str(e)}, retrying...")
                    sleep(1 * (self.json_validation_retries - remaining_retries))

        if last_error:
            logger.error(f"All retry attempts failed: {str(last_error)}")
            return None
        
        logger.error("Failed to generate valid response after all retries")
        return None

    def _combine_chunk_summaries(self, summaries: List[Dict]) -> Dict:
        """チャンクサマリーの統合処理の改善"""
        if not summaries:
            raise ValueError("No valid summaries to combine")

        combined = {
            "概要": "",
            "主要ポイント": [],
            "詳細分析": [],
            "キーワード": []
        }

        # Combine summaries with deduplication
        seen_points = set()
        seen_keywords = set()

        for summary in summaries:
            combined["概要"] += summary.get("概要", "") + " "
            
            for point in summary.get("主要ポイント", []):
                point_key = f"{point['タイトル']}_{point['説明'][:50]}"
                if point_key not in seen_points:
                    seen_points.add(point_key)
                    combined["主要ポイント"].append(point)
            
            for analysis in summary.get("詳細分析", []):
                combined["詳細分析"].append(analysis)
            
            for keyword in summary.get("キーワード", []):
                if keyword["用語"] not in seen_keywords:
                    seen_keywords.add(keyword["用語"])
                    combined["キーワード"].append(keyword)

        # Trim and clean up
        combined["概要"] = combined["概要"].strip()[:150]
        combined["主要ポイント"] = combined["主要ポイント"][:5]  # Keep top 5 points
        
        return combined

    def _retry_with_backoff(self, func, max_retries=5):
        """改善された再試行ロジック with Gemini特有のエラーハンドリング"""
        last_error = None
        for attempt in range(max_retries):
            try:
                start_time = time.time()
                self.rate_limiter.wait()
                result = func()
                # 成功した場合は応答時間を更新
                self.rate_limiter.update_interval(time.time() - start_time)
                return result
            except Exception as e:
                error_msg = str(e).lower()
                wait_time = (2 ** attempt) + uniform(0, 1)
                
                if "quota" in error_msg:
                    logger.error("API quota exceeded, attempting to refresh API key")
                    try:
                        self._initialize_api()
                        continue
                    except Exception as key_error:
                        raise Exception(f"APIキーの更新に失敗しました: {str(key_error)}")
                elif "rate" in error_msg:
                    logger.warning(f"Rate limit hit, waiting {wait_time:.2f} seconds...")
                    sleep(wait_time)
                else:
                    logger.warning(f"Unexpected error: {str(e)}, retrying in {wait_time:.2f} seconds...")
                    sleep(wait_time)
                
                last_error = e
                
                if attempt == max_retries - 1:
                    if "quota" in error_msg:
                        raise Exception("API利用クォータを超過しました。新しいAPIキーを設定してください。")
                    elif "rate" in error_msg:
                        raise Exception("API制限に達しました。しばらく待ってから再試行してください。")
                    else:
                        raise Exception(f"要約生成中にエラーが発生しました: {str(e)}")

        raise last_error

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

            # JSONを整形されたテキストに変換
            final_summary = f"# 概要\n{final_summary_data['概要']}\n\n"
            final_summary += "# 主要ポイント\n"
            for point in final_summary_data['主要ポイント']:
                final_summary += f"- {point['タイトル']}: {point['説明']}\n"
            
            final_summary += "\n# 詳細分析\n"
            for analysis in final_summary_data['詳細分析']:
                final_summary += f"## {analysis['ポイント']}\n{analysis['分析']}\n\n"
            
            final_summary += "# キーワードと重要概念\n"
            for keyword in final_summary_data['キーワード']:
                final_summary += f"- {keyword['用語']}: {keyword['説明']}\n"

            # キャッシュに保存
            self.cache[cache_key] = final_summary

            if progress_callback:
                progress_callback(1.0, "✨ 要約が完了しました")

            return final_summary

        except Exception as e:
            error_msg = str(e)
            if "quota" in error_msg.lower():
                error_msg = "API利用クォータを超過しました。新しいAPIキーを設定してください。"
            elif "rate" in error_msg.lower():
                error_msg = "API制限に達しました。しばらく待ってから再試行してください。"
            
            logger.error(f"Error generating summary: {error_msg}")
            if progress_callback:
                progress_callback(1.0, f"❌ エラーが発生しました: {error_msg}")
            raise Exception(f"要約の生成に失敗しました: {error_msg}")

    def get_transcript(self, url: str) -> str:
        """Get transcript from YouTube video with error handling and caching."""
        try:
            video_id = self._extract_video_id(url)
            
            # Check cache first
            if video_id in self.cache:
                return self.cache[video_id]
            
            def fetch_transcript():
                transcript = YouTubeTranscriptApi.get_transcript(
                    video_id,
                    languages=['ja', 'en']
                )
                formatter = TextFormatter()
                return formatter.format_transcript(transcript)
            
            # Use retry logic for transcript fetching
            formatted_transcript = self._retry_with_backoff(fetch_transcript)
            
            # Cache the result
            self.cache[video_id] = formatted_transcript
            
            return formatted_transcript
            
        except Exception as e:
            logger.error(f"Error getting transcript: {str(e)}")
            raise Exception(f"Failed to get transcript: {str(e)}")

    def _extract_video_id(self, url: str) -> str:
        """Extract YouTube video ID from URL."""
        try:
            patterns = [
                r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
                r'(?:youtu\.be\/)([0-9A-Za-z_-]{11})',
                r'(?:embed\/)([0-9A-Za-z_-]{11})'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, url)
                if match:
                    return match.group(1)
            raise ValueError("Invalid YouTube URL format")
        except Exception as e:
            logger.error(f"Error extracting video ID: {str(e)}")
            raise ValueError(f"Could not extract video ID from URL: {str(e)}")

    def _split_text_into_chunks(self, text: str) -> List[str]:
        """テキストを適切なサイズのチャンクに分割"""
        words = text.split()
        chunks = []
        current_chunk = []
        current_length = 0

        for word in words:
            word_length = len(word)
            if current_length + word_length + 1 <= self.chunk_size:
                current_chunk.append(word)
                current_length += word_length + 1
            else:
                chunks.append(' '.join(current_chunk))
                current_chunk = [word]
                current_length = word_length

        if current_chunk:
            chunks.append(' '.join(current_chunk))

        return chunks

    def proofread_text(self, text: str, progress_callback: Optional[Callable] = None) -> str:
        """Proofread and enhance text using Gemini API."""
        try:
            if not text:
                raise ValueError("Input text is empty")

            if progress_callback:
                progress_callback(0.2, "テキストを解析中...")

            # キャッシュをチェック
            cache_key = hashlib.md5(f"proofread_{text}".encode()).hexdigest()
            if cache_key in self.cache:
                if progress_callback:
                    progress_callback(1.0, "✨ キャッシュから校正済みテキストを取得しました")
                return self.cache[cache_key]

            if progress_callback:
                progress_callback(0.4, "文章を校正中...")

            def proofread():
                prompt = """以下のテキストを校正・整形してください。

要件:
1. 文章の明確性と読みやすさの向上
2. 文法・表現の改善
3. 文脈の一貫性確保
4. 専門用語の適切な使用
5. 段落構造の最適化

入力テキスト:
""" + text

                response = self.model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.3,
                        top_p=0.8,
                        top_k=40,
                        max_output_tokens=8192,
                    )
                )
                return response.text

            # 再試行ロジックを使用
            enhanced_text = self._retry_with_backoff(proofread)

            if progress_callback:
                progress_callback(0.8, "最終調整中...")

            if not enhanced_text:
                raise ValueError("Empty response from Gemini API")

            # 成功した場合はキャッシュに保存
            self.cache[cache_key] = enhanced_text

            if progress_callback:
                progress_callback(1.0, "✨ 校正が完了しました")

            return enhanced_text

        except Exception as e:
            error_msg = str(e)
            if "quota" in error_msg.lower():
                error_msg = "API利用クォータを超過しました。新しいAPIキーを設定してください。"
            elif "rate" in error_msg.lower():
                error_msg = "API制限に達しました。しばらく待ってから再試行してください。"
            logger.error(f"Error proofreading text: {error_msg}")
            if progress_callback:
                progress_callback(1.0, f"❌ エラーが発生しました: {error_msg}")
            raise Exception(f"Failed to proofread text: {error_msg}")