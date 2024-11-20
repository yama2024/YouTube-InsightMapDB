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
from typing import Optional, Callable, List, Dict, Any
import json
import google.generativeai as genai

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DynamicRateLimiter:
    def __init__(self):
        self.last_request = 0
        self.min_interval = 3.0  # より長い最小待機時間
        self.backoff_multiplier = 1.0
        self.max_interval = 15.0  # より長い最大待機時間
        self.success_count = 0
        self.error_count = 0
        self.quota_exceeded = False
        self.request_times = []
        self.window_size = 60  # 1分間の時間枠
        self.max_requests = 30  # 1分間あたりの最大リクエスト数を制限

    def wait(self):
        now = time.time()
        
        # 時間枠内のリクエストを更新
        self.request_times = [t for t in self.request_times if now - t < self.window_size]
        
        if len(self.request_times) >= self.max_requests:
            sleep_time = self.window_size - (now - self.request_times[0])
            if sleep_time > 0:
                time.sleep(sleep_time)
        
        if self.quota_exceeded:
            time.sleep(self.max_interval)
            self.quota_exceeded = False
            return
        
        wait_time = max(0, self.min_interval * self.backoff_multiplier)
        if wait_time > 0:
            time.sleep(wait_time)
        
        self.request_times.append(now)
        self.last_request = now

    def report_success(self):
        self.success_count += 1
        self.backoff_multiplier = max(1.0, self.backoff_multiplier * 0.95)

    def report_error(self):
        self.error_count += 1
        self.backoff_multiplier = min(self.max_interval, self.backoff_multiplier * 1.5)

    def report_quota_exceeded(self):
        self.quota_exceeded = True
        self.error_count += 1
        self.backoff_multiplier = min(self.max_interval, self.backoff_multiplier * 2.0)

class TextProcessor:
    def __init__(self):
        self._initialize_api()
        self.rate_limiter = DynamicRateLimiter()
        self.cache = TTLCache(maxsize=100, ttl=3600)
        self.chunk_size = 2500
        self.overlap_size = 200
        self.max_retries = 3  # Updated to match new implementation
        self.backoff_factor = 2
        self.context_memory = []
        self.max_context_memory = 5
        self.summary_cache = {}

    def _initialize_api(self):
        """Initialize or reinitialize the Gemini API with current environment"""
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("Gemini API key is not set in environment variables")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-1.5-pro')

    def _split_text_into_chunks(self, text: str) -> List[str]:
        if len(text) < self.chunk_size:
            return [text]
        
        chunks = []
        current_chunk = []
        current_length = 0
        
        # 文単位での分割（改行も考慮）
        sentences = [s.strip() for s in re.split('[。.!?！？\n]', text) if s.strip()]
        
        for sentence in sentences:
            if current_length + len(sentence) > self.chunk_size and current_chunk:
                chunks.append(' '.join(current_chunk))
                current_chunk = [sentence]
                current_length = len(sentence)
            else:
                current_chunk.append(sentence)
                current_length += len(sentence)
        
        if current_chunk:
            chunks.append(' '.join(current_chunk))
        
        return chunks

    def _process_chunk_with_retries(self, chunk: str, context: Dict) -> Optional[Dict]:
        max_retries = 5  # リトライ回数を増やす
        base_wait_time = 3  # 基本待機時間を増やす
        
        for attempt in range(max_retries):
            try:
                self.rate_limiter.wait()
                
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
                    raise ValueError("Empty response received")
                
                result = self._validate_json_response(response.text)
                if result:
                    self.rate_limiter.report_success()
                    return result
                
                raise ValueError("Invalid JSON response")
                
            except Exception as e:
                error_msg = str(e).lower()
                self.rate_limiter.report_error()
                
                if "quota" in error_msg or "429" in error_msg:
                    self.rate_limiter.report_quota_exceeded()
                    wait_time = base_wait_time * (2 ** attempt)
                    logger.warning(f"API quota exceeded, waiting {wait_time} seconds...")
                    time.sleep(wait_time)
                    
                    # APIキーの再初期化を試みる
                    try:
                        self._initialize_api()
                    except Exception as key_error:
                        logger.error(f"Failed to reinitialize API: {str(key_error)}")
                
                if attempt < max_retries - 1:
                    wait_time = base_wait_time * (2 ** attempt)
                    logger.warning(f"Retrying chunk processing ({max_retries - attempt - 1} attempts left)")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Failed to process chunk after all retries: {str(e)}")
                    return None
        
        return None

    def _extract_video_id(self, url: str) -> str:
        """Extract video ID from YouTube URL"""
        video_id_match = re.search(r'(?:v=|/v/|youtu\.be/)([^&?/]+)', url)
        if not video_id_match:
            raise ValueError("Invalid YouTube URL format")
        return video_id_match.group(1)

    def get_transcript(self, url: str) -> str:
        """Get transcript from YouTube video with improved error handling"""
        try:
            video_id = self._extract_video_id(url)
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            
            # Try to get Japanese transcript first
            try:
                transcript = transcript_list.find_transcript(['ja'])
            except Exception:
                # If Japanese is not available, try English
                try:
                    transcript = transcript_list.find_transcript(['en'])
                except Exception:
                    # If no preferred language is available, get the first available
                    transcript = transcript_list.find_manually_created_transcript()
            
            transcript_data = transcript.fetch()
            formatter = TextFormatter()
            formatted_transcript = formatter.format_transcript(transcript_data)
            
            if not formatted_transcript:
                raise ValueError("空の文字起こしデータが返されました")
            
            return formatted_transcript
            
        except Exception as e:
            logger.error(f"Error getting transcript: {str(e)}")
            raise Exception(f"文字起こしの取得に失敗しました: {str(e)}")

    def generate_summary(self, text: str, progress_callback: Optional[Callable] = None) -> str:
        """Generate summary with improved context handling and progress tracking"""
        try:
            if not text:
                raise ValueError("Input text is empty")

            # Generate cache key based on text content
            cache_key = hashlib.md5(text.encode()).hexdigest()
            if cache_key in self.summary_cache:
                return self.summary_cache[cache_key]

            # Split text into chunks with context preservation
            chunks = self._split_text_into_chunks(text)
            total_chunks = len(chunks)
            summaries = []

            for i, chunk in enumerate(chunks, 1):
                if progress_callback:
                    progress = (i - 1) / total_chunks
                    progress_callback(progress, f"チャンク {i}/{total_chunks} を処理中...")

                # Get context from previous summaries
                context = self._get_chunk_context(summaries)
                
                # Process chunk with retries and context
                chunk_summary = self._process_chunk_with_retries(chunk, context)
                if chunk_summary:
                    summaries.append(chunk_summary)
                    self._update_context_memory(chunk_summary)

            if not summaries:
                raise ValueError("No valid summaries generated")

            # Combine summaries with context awareness
            combined_summary = self._combine_chunk_summaries(summaries)
            
            if progress_callback:
                progress_callback(1.0, "✨ 要約が完了しました")

            # Format the final summary
            final_summary = self._format_final_summary(combined_summary)
            self.summary_cache[cache_key] = final_summary
            return final_summary

        except Exception as e:
            logger.error(f"Error in summary generation: {str(e)}")
            if progress_callback:
                progress_callback(1.0, f"❌ エラーが発生しました: {str(e)}")
            raise

    def _get_chunk_context(self, previous_summaries: List[Dict]) -> Dict:
        """Get context information from previous chunk summaries"""
        if not previous_summaries:
            return {}

        # Get the most recent summary
        latest_summary = previous_summaries[-1]
        
        # Extract relevant context
        context = {
            "previous_topics": [],
            "key_points": [],
            "continuing_themes": []
        }

        if "文脈連携" in latest_summary:
            context["continuing_themes"] = latest_summary["文脈連携"].get("継続するトピック", [])
            context["new_topics"] = latest_summary["文脈連携"].get("新規トピック", [])

        if "主要ポイント" in latest_summary:
            context["key_points"] = [
                point["タイトル"] for point in latest_summary["主要ポイント"]
            ]

        return context

    def _format_final_summary(self, combined_summary: Dict) -> str:
        """Format the combined summary into a readable markdown string"""
        sections = []

        # Add overview
        if "概要" in combined_summary:
            sections.append(f"## 概要\n\n{combined_summary['概要'].strip()}\n")

        # Add main points
        if "主要ポイント" in combined_summary and combined_summary["主要ポイント"]:
            sections.append("## 主要ポイント\n")
            for point in combined_summary["主要ポイント"]:
                if isinstance(point, dict):
                    title = point.get("タイトル", "")
                    desc = point.get("説明", "")
                    importance = point.get("重要度", 3)
                    sections.append(f"### {title} {'🔥' * importance}\n{desc}\n")

        # Add detailed analysis
        if "詳細分析" in combined_summary and combined_summary["詳細分析"]:
            sections.append("## 詳細分析\n")
            for analysis in combined_summary["詳細分析"]:
                if isinstance(analysis, dict):
                    section = analysis.get("セクション", "")
                    content = analysis.get("内容", "")
                    points = analysis.get("キーポイント", [])
                    sections.append(f"### {section}\n{content}\n")
                    if points:
                        sections.append("\n**キーポイント:**\n")
                        for point in points:
                            sections.append(f"- {point}\n")

        # Add keywords
        if "キーワード" in combined_summary and combined_summary["キーワード"]:
            sections.append("## キーワード\n")
            for keyword in combined_summary["キーワード"]:
                if isinstance(keyword, dict):
                    term = keyword.get("用語", "")
                    desc = keyword.get("説明", "")
                    importance = keyword.get("文脈上の重要度", 3)
                    sections.append(f"### {term} {'⭐' * importance}\n{desc}\n")

        return "\n".join(sections)

    def proofread_text(self, text: str, progress_callback: Optional[Callable] = None) -> str:
        """Proofread and enhance text with context awareness"""
        try:
            if not text:
                raise ValueError("入力テキストが空です")

            if progress_callback:
                progress_callback(0.2, "テキストを解析中...")

            # Create context-aware prompt for proofreading
            context = self._get_context_summary()
            prompt = f"""以下のテキストを校正し、読みやすく整形してください。文脈を考慮して改善を行ってください。

入力テキスト:
{text}

コンテキスト情報:
{context}

必要な改善点:
1. 文章の構造と流れの改善
2. 文体の統一
3. 冗長な表現の削除
4. 適切な段落分け
5. 文脈の一貫性確保

結果は整形済みのテキストのみを返してください。"""

            if progress_callback:
                progress_callback(0.5, "テキストを校正中...")

            # Process with retries
            response = None
            for attempt in range(self.max_retries):
                try:
                    self.rate_limiter.wait()
                    response = self.model.generate_content(
                        prompt,
                        generation_config=genai.types.GenerationConfig(
                            temperature=0.3,
                            top_p=0.8,
                            top_k=40,
                            max_output_tokens=8192,
                        )
                    )
                    break
                except Exception as e:
                    if attempt == self.max_retries - 1:
                        raise
                    time.sleep(self.backoff_factor ** attempt)

            if not response or not response.text:
                raise ValueError("校正結果の生成に失敗しました")

            if progress_callback:
                progress_callback(1.0, "✨ テキストの校正が完了しました")

            return response.text.strip()

        except Exception as e:
            logger.error(f"Error in text proofreading: {str(e)}")
            if progress_callback:
                progress_callback(1.0, f"❌ エラーが発生しました: {str(e)}")
            raise

    def _update_context_memory(self, summary: Dict[str, Any]) -> None:
        """Update context memory with new summary information"""
        self.context_memory.append({
            "概要": summary.get("概要", ""),
            "主要ポイント": [point["タイトル"] for point in summary.get("主要ポイント", [])],
            "キーワード": [kw["用語"] for kw in summary.get("キーワード", [])]
        })
        
        # Keep only the most recent context
        if len(self.context_memory) > self.max_context_memory:
            self.context_memory.pop(0)

    def _get_context_summary(self) -> str:
        """Generate a summary of the current context"""
        if not self.context_memory:
            return ""
            
        context_summary = {
            "これまでの概要": [ctx["概要"] for ctx in self.context_memory],
            "重要なポイント": list(set(
                point for ctx in self.context_memory 
                for point in ctx["主要ポイント"]
            )),
            "キーワード": list(set(
                kw for ctx in self.context_memory 
                for kw in ctx["キーワード"]
            ))
        }
        
        return json.dumps(context_summary, ensure_ascii=False, indent=2)

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
        """Enhanced prompt with context awareness and improved structure"""
        context_info = ""
        if context:
            context_info = f"\nコンテキスト情報:\n{json.dumps(context, ensure_ascii=False, indent=2)}"

        previous_context = self._get_context_summary()
        if previous_context:
            context_info += f"\n\n前回までの文脈:\n{previous_context}"

        prompt = f"""以下のテキストを分析し、前後の文脈を考慮した上で、厳密なJSON形式で構造化された要約を生成してください。

入力テキスト:
{text}
{context_info}

必須出力形式:
{{
    "概要": "150文字以内の簡潔な説明（前後の文脈を考慮）",
    "主要ポイント": [
        {{
            "タイトル": "重要なポイントの見出し",
            "説明": "具体的な説明文（前後の文脈との関連性を含む）",
            "重要度": "1-5の数値"
        }}
    ],
    "詳細分析": [
        {{
            "セクション": "分析セクションの名称",
            "内容": "詳細な分析内容（文脈を考慮）",
            "キーポイント": [
                "重要な点1",
                "重要な点2"
            ],
            "前後の関連性": "前後の文脈との関係性の説明"
        }}
    ],
    "キーワード": [
        {{
            "用語": "キーワード",
            "説明": "簡潔な説明",
            "関連語": ["関連キーワード1", "関連キーワード2"],
            "文脈上の重要度": "1-5の数値"
        }}
    ],
    "文脈連携": {{
        "前の内容との関連": "前の部分との関連性の説明",
        "継続するトピック": ["継続して重要な話題1", "継続して重要な話題2"],
        "新規トピック": ["新しく導入された話題1", "新しく導入された話題2"]
    }}
}}

制約事項:
1. 必ず有効なJSONフォーマットを維持すること
2. すべての文字列は適切にエスケープすること
3. 数値は必ず数値型で出力すること
4. 配列は必ず1つ以上の要素を含むこと
5. 主要ポイントは3-5項目を含むこと
6. キーワードは最低3つ含むこと
7. 前後の文脈を必ず考慮すること
8. 文脈連携セクションは必須

注意:
- JSONフォーマット以外の装飾や説明は一切含めないでください
- 各セクションは必須です。省略しないでください
- 不正なJSON構造を避けるため、文字列内の二重引用符は必ずエスケープしてください
- 前後の文脈との一貫性を重視してください"""

        return prompt

    def _process_chunk_with_retries(self, chunk: str, context: Dict) -> Optional[Dict]:
        """Process text chunk with improved error handling and context awareness"""
        remaining_retries = self.max_retries
        backoff_time = 1

        while remaining_retries > 0:
            try:
                self.rate_limiter.wait()
                
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
                    raise ValueError("Empty response received")
                
                result = self._validate_json_response(response.text)
                if result:
                    self.rate_limiter.report_success()
                    self._update_context_memory(result)
                    return result
                
                raise ValueError("Invalid JSON response")
                
            except Exception as e:
                error_msg = str(e).lower()
                remaining_retries -= 1
                
                if "quota" in error_msg or "429" in error_msg:
                    self.rate_limiter.report_quota_exceeded()
                    logger.warning(f"API quota exceeded, waiting {backoff_time} seconds...")
                    time.sleep(backoff_time)
                    backoff_time *= 2
                    
                    try:
                        self._initialize_api()
                    except Exception as key_error:
                        logger.error(f"Failed to reinitialize API: {str(key_error)}")
                else:
                    self.rate_limiter.report_error()
                
                if remaining_retries > 0:
                    logger.warning(f"Retrying chunk processing ({remaining_retries} attempts left)")
                else:
                    logger.error(f"Failed to process chunk after all retries: {str(e)}")
                    return None
        
        return None

    def _split_text_into_chunks(self, text: str) -> List[str]:
        """Split text into chunks with improved context preservation"""
        if not text:
            raise ValueError("入力テキストが空です")
            
        # テキストの前処理
        text = text.replace('\n', ' ').strip()
        text = re.sub(r'\s+', ' ', text)
        
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
        
        for i, sentence in enumerate(sentences):
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
            
            # チャンクの重複を考慮した処理
            if current_length + sentence_length > self.chunk_size - self.overlap_size and current_chunk:
                # 現在のチャンクを保存
                chunks.append(' '.join(current_chunk))
                
                # 重複部分を新しいチャンクの開始点として使用
                overlap_sentences = current_chunk[-2:] if len(current_chunk) > 2 else current_chunk
                current_chunk = overlap_sentences.copy()
                current_length = sum(len(s) for s in current_chunk)
            
            current_chunk.append(sentence)
            current_length += sentence_length
        
        # 残りの文を処理
        if current_chunk:
            chunks.append(' '.join(current_chunk))
        
        # 最終チェック
        if not chunks:
            return [text]
        
        return chunks

    def _combine_chunk_summaries(self, summaries: List[Dict]) -> Dict:
        """Improved chunk summary combination with context awareness"""
        if not summaries:
            raise ValueError("No valid summaries to combine")

        combined = {
            "概要": "",
            "主要ポイント": [],
            "詳細分析": [],
            "キーワード": [],
            "文脈連携": {
                "継続するトピック": set(),
                "新規トピック": set()
            }
        }

        # 文脈の連続性を追跡
        continuous_topics = set()
        new_topics = set()

        for summary in summaries:
            if not isinstance(summary, dict):
                continue

            # 概要の結合
            if "概要" in summary:
                combined["概要"] += summary["概要"].strip() + " "

            # 主要ポイントの統合（重複を考慮）
            if "主要ポイント" in summary:
                for point in summary["主要ポイント"]:
                    if isinstance(point, dict) and "タイトル" in point and "説明" in point:
                        # 既存のポイントと重複チェック
                        if not any(p["タイトル"] == point["タイトル"] for p in combined["主要ポイント"]):
                            combined["主要ポイント"].append(point)

            # 詳細分析の統合
            if "詳細分析" in summary:
                for analysis in summary["詳細分析"]:
                    if isinstance(analysis, dict) and "セクション" in analysis:
                        combined["詳細分析"].append({
                            "セクション": analysis["セクション"],
                            "内容": analysis["内容"],
                            "キーポイント": analysis.get("キーポイント", []),
                            "前後の関連性": analysis.get("前後の関連性", "")
                        })

            # キーワードの統合（重複を除去）
            if "キーワード" in summary:
                for keyword in summary["キーワード"]:
                    if isinstance(keyword, dict) and "用語" in keyword:
                        if not any(k["用語"] == keyword["用語"] for k in combined["キーワード"]):
                            combined["キーワード"].append(keyword)

            # 文脈連携情報の統合
            if "文脈連携" in summary:
                context_info = summary["文脈連携"]
                if isinstance(context_info, dict):
                    if "継続するトピック" in context_info:
                        continuous_topics.update(context_info["継続するトピック"])
                    if "新規トピック" in context_info:
                        new_topics.update(context_info["新規トピック"])

        # 最終的な文脈連携情報の設定
        combined["文脈連携"] = {
            "継続するトピック": list(continuous_topics),
            "新規トピック": list(new_topics)
        }

        # 概要の整形
        combined["概要"] = combined["概要"].strip()[:150]

        # 主要ポイントの制限
        combined["主要ポイント"] = sorted(
            combined["主要ポイント"],
            key=lambda x: x.get("重要度", 0),
            reverse=True
        )[:5]

        return combined

    def generate_summary(self, text: str, progress_callback: Optional[Callable] = None) -> str:
        """Generate context-aware summary with improved processing"""
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

            # コンテキストメモリの初期化
            self.context_memory = []

            # チャンク分割
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
                    "chunk_position": "開始" if i == 1 else "終了" if i == len(chunks) else "中間",
                    "previous_summaries": self._get_context_summary() if self.context_memory else ""
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

            # 最終的な要約テキストの生成
            final_summary = self._format_final_summary(final_summary_data)
            
            # キャッシュに保存
            self.cache[cache_key] = final_summary

            if progress_callback:
                progress_callback(1.0, "✨ 要約が完了しました")

            return final_summary

        except Exception as e:
            logger.error(f"Error in summary generation: {str(e)}")
            if progress_callback:
                progress_callback(1.0, f"❌ エラーが発生しました: {str(e)}")
            raise

    def _format_final_summary(self, summary_data: Dict) -> str:
        """Format the final summary with improved structure and context awareness"""
        sections = []
        
        # 概要セクション
        sections.append(f"# 概要\n{summary_data['概要']}\n")
        
        # 主要ポイント
        sections.append("# 主要ポイント")
        for point in summary_data["主要ポイント"]:
            sections.append(f"## {point['タイトル']}")
            sections.append(f"{point['説明']}")
            sections.append(f"重要度: {'⭐' * int(point['重要度'])}\n")
        
        # 詳細分析
        sections.append("# 詳細分析")
        for analysis in summary_data["詳細分析"]:
            sections.append(f"## {analysis['セクション']}")
            sections.append(analysis['内容'])
            if analysis['キーポイント']:
                sections.append("\n主なポイント:")
                for point in analysis['キーポイント']:
                    sections.append(f"- {point}")
            if "前後の関連性" in analysis:
                sections.append(f"\n前後の関連性: {analysis['前後の関連性']}\n")
        
        # キーワード
        sections.append("# キーワード")
        for keyword in summary_data["キーワード"]:
            sections.append(f"## {keyword['用語']}")
            sections.append(f"{keyword['説明']}")
            if keyword.get('関連語'):
                sections.append("関連キーワード: " + ", ".join(keyword['関連語']))
            if "文脈上の重要度" in keyword:
                sections.append(f"文脈上の重要度: {'⭐' * int(keyword['文脈上の重要度'])}\n")
        
        # 文脈連携
        if "文脈連携" in summary_data:
            sections.append("# 文脈の連続性")
            context_info = summary_data["文脈連携"]
            
            if context_info.get("継続するトピック"):
                sections.append("\n## 継続しているトピック")
                for topic in context_info["継続するトピック"]:
                    sections.append(f"- {topic}")
            
            if context_info.get("新規トピック"):
                sections.append("\n## 新しく導入されたトピック")
                for topic in context_info["新規トピック"]:
                    sections.append(f"- {topic}")
        
        return "\n".join(sections)