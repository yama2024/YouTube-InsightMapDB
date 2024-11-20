import os
import logging
import time
import asyncio
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
        self.min_interval = 2.0
        self.backoff_multiplier = 1.0
        self.max_interval = 10.0
        self.quota_exceeded = False
        self.lock = asyncio.Lock()
        self.request_times = []
        self.window_size = 60  # 1分間の時間枠
        self.max_requests = 60  # 1分間あたりの最大リクエスト数

    async def wait(self):
        async with self.lock:
            now = time.time()
            self.request_times = [t for t in self.request_times if now - t < self.window_size]
            
            if len(self.request_times) >= self.max_requests:
                sleep_time = self.window_size - (now - self.request_times[0])
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

            if self.quota_exceeded:
                await asyncio.sleep(max(5.0, self.max_interval))
                self.quota_exceeded = False
                return

            wait_time = max(0, self.min_interval * self.backoff_multiplier - (now - self.last_request))
            if wait_time > 0:
                await asyncio.sleep(wait_time)

            self.last_request = now
            self.request_times.append(now)

    def report_success(self):
        self.backoff_multiplier = max(1.0, self.backoff_multiplier * 0.95)

    def report_error(self):
        self.backoff_multiplier = min(self.max_interval, self.backoff_multiplier * 1.5)

    def report_quota_exceeded(self):
        self.quota_exceeded = True
        self.backoff_multiplier = min(self.max_interval, self.backoff_multiplier * 2.0)

class TextProcessor:
    def __init__(self):
        self._initialize_api()
        self.rate_limiter = DynamicRateLimiter()
        self.cache = TTLCache(maxsize=100, ttl=3600)
        self.chunk_size = 1500
        self.overlap_size = 200
        self.max_retries = 3
        self.backoff_factor = 2
        self.context_memory = []
        self.max_context_memory = 5

    def _initialize_api(self):
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("Gemini API key is not set in environment variables")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-1.5-pro')

    def get_transcript(self, url: str) -> str:
        try:
            video_id = self._extract_video_id(url)
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            
            try:
                transcript = transcript_list.find_transcript(['ja'])
            except Exception:
                try:
                    transcript = transcript_list.find_transcript(['en'])
                except Exception:
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

    def _extract_video_id(self, url: str) -> str:
        video_id_match = re.search(r'(?:v=|/v/|youtu\.be/)([^&?/]+)', url)
        if not video_id_match:
            raise ValueError("Invalid YouTube URL format")
        return video_id_match.group(1)

    def generate_summary(self, text: str, progress_callback: Optional[Callable] = None) -> str:
        """Synchronous wrapper for async summary generation"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(self._generate_summary_async(text, progress_callback))
        finally:
            loop.close()

    async def _generate_summary_async(self, text: str, progress_callback: Optional[Callable] = None) -> str:
        try:
            if not text:
                raise ValueError("入力テキストが空です")

            cache_key = hashlib.md5(text.encode()).hexdigest()
            if cache_key in self.cache:
                if progress_callback:
                    progress_callback(1.0, "✨ キャッシュから要約を取得しました")
                return self.cache[cache_key]

            # Reset context memory for new summary
            self.context_memory = []
            chunks = self._split_text_into_chunks(text)
            total_chunks = len(chunks)

            if progress_callback:
                progress_callback(0.1, f"テキストを {total_chunks} チャンクに分割しました")

            # Process chunks sequentially to maintain context
            summaries = []
            for i, chunk in enumerate(chunks, 1):
                summary = await self._process_chunk_with_retries(chunk, i, total_chunks, progress_callback)
                if summary:
                    summaries.append(summary)
                    if progress_callback:
                        progress = 0.1 + (0.8 * (i / total_chunks))
                        progress_callback(progress, f"チャンク {i}/{total_chunks} を処理中...")

            if not summaries:
                raise ValueError("すべてのチャンクの処理に失敗しました")

            if progress_callback:
                progress_callback(0.9, "要約を統合中...")

            final_summary = self._combine_summaries(summaries)
            formatted_summary = self._format_summary(final_summary)
            self.cache[cache_key] = formatted_summary

            if progress_callback:
                progress_callback(1.0, "✨ 要約が完了しました")

            return formatted_summary

        except Exception as e:
            logger.error(f"Error in summary generation: {str(e)}")
            if progress_callback:
                progress_callback(1.0, f"❌ エラーが発生しました: {str(e)}")
            raise

    def _split_text_into_chunks(self, text: str) -> List[str]:
        """Split text into chunks while preserving context"""
        if not text:
            raise ValueError("入力テキストが空です")

        # Clean and normalize text
        text = text.replace('\n', ' ').strip()
        text = re.sub(r'\s+', ' ', text)

        if len(text) <= self.chunk_size:
            return [text]

        # Split text into sentences
        sentences = []
        current = ''
        for char in text:
            current += char
            if char in ['。', '！', '？', '!', '?', '.']:
                sentences.append(current.strip())
                current = ''
        if current.strip():
            sentences.append(current.strip())

        # Create chunks with overlap
        chunks = []
        current_chunk = []
        current_length = 0

        for sentence in sentences:
            sentence_length = len(sentence)

            # Handle long sentences
            if sentence_length > self.chunk_size:
                if current_chunk:
                    chunks.append(' '.join(current_chunk))
                chunks.extend([sentence[i:i+self.chunk_size] 
                             for i in range(0, len(sentence), self.chunk_size)])
                current_chunk = []
                current_length = 0
                continue

            # Check if adding the sentence would exceed chunk size
            if current_length + sentence_length > self.chunk_size - self.overlap_size and current_chunk:
                chunks.append(' '.join(current_chunk))
                # Keep last sentences for context
                current_chunk = current_chunk[-2:] if len(current_chunk) > 2 else current_chunk[:]
                current_length = sum(len(s) for s in current_chunk)

            current_chunk.append(sentence)
            current_length += sentence_length

        if current_chunk:
            chunks.append(' '.join(current_chunk))

        return chunks

    async def _process_chunk_with_retries(self, chunk: str, chunk_index: int, 
                                        total_chunks: int, 
                                        progress_callback: Optional[Callable]) -> Optional[Dict]:
        """Process a text chunk with retries and context awareness"""
        remaining_retries = self.max_retries
        wait_time = 1

        while remaining_retries > 0:
            try:
                await self.rate_limiter.wait()

                # Create prompt with context
                context = {
                    "chunk_index": chunk_index,
                    "total_chunks": total_chunks,
                    "previous_context": self._get_context_summary()
                }

                response = await self.model.generate_content(
                    self._create_summary_prompt(chunk, context),
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.3,
                        top_p=0.8,
                        top_k=40,
                        max_output_tokens=8192,
                    )
                )

                if not response.text:
                    raise ValueError("Empty response received")

                summary = self._validate_json_response(response.text)
                if summary:
                    self.rate_limiter.report_success()
                    self._update_context_memory(summary)
                    return summary

                raise ValueError("Invalid response format")

            except Exception as e:
                remaining_retries -= 1
                error_message = str(e).lower()

                if "quota" in error_message or "429" in error_message:
                    self.rate_limiter.report_quota_exceeded()
                    if remaining_retries > 0:
                        await asyncio.sleep(wait_time)
                        wait_time *= 2
                else:
                    self.rate_limiter.report_error()
                    if remaining_retries > 0:
                        await asyncio.sleep(1)

                if remaining_retries == 0:
                    logger.error(f"Failed to process chunk after all retries: {str(e)}")
                    return None

        return None

    def _create_summary_prompt(self, text: str, context: Dict) -> str:
        """Create a context-aware summary prompt"""
        previous_context = context.get("previous_context", "")
        chunk_info = f"""
        チャンク情報:
        - 現在のチャンク: {context['chunk_index']}/{context['total_chunks']}
        - チャンクの位置: {"開始" if context['chunk_index'] == 1 else "終了" if context['chunk_index'] == context['total_chunks'] else "中間"}
        """

        return f"""以下のテキストを分析し、前後の文脈を考慮した要約を生成してください。

入力テキスト:
{text}

{chunk_info}

前回までの文脈:
{previous_context}

以下のJSON形式で出力してください:
{{
    "概要": "このセクションの要点（150文字以内）",
    "主要ポイント": [
        {{
            "タイトル": "ポイントの見出し",
            "説明": "詳細な説明",
            "重要度": 1-5の数値
        }}
    ],
    "文脈連携": {{
        "前の内容との関連": "前のセクションとの関連性",
        "継続するトピック": ["継続している話題"],
        "新規トピック": ["新しく導入された話題"]
    }}
}}"""

    def _validate_json_response(self, response_text: str) -> Optional[Dict]:
        """Validate and clean JSON response"""
        try:
            # Extract JSON content
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if not json_match:
                return None
            
            json_str = json_match.group()
            json_str = re.sub(r'[\n\r\t]', ' ', json_str)
            json_str = re.sub(r'\s+', ' ', json_str)
            
            return json.loads(json_str)
        except Exception as e:
            logger.error(f"JSON validation error: {str(e)}")
            return None

    def _get_context_summary(self) -> str:
        """Get summary of previous context"""
        if not self.context_memory:
            return ""

        context_summary = {
            "前回までの要点": [ctx.get("概要", "") for ctx in self.context_memory[-2:]],
            "継続中のトピック": list(set(
                topic for ctx in self.context_memory
                for topic in ctx.get("文脈連携", {}).get("継続するトピック", [])
            ))
        }

        return json.dumps(context_summary, ensure_ascii=False, indent=2)

    def _update_context_memory(self, summary: Dict) -> None:
        """Update context memory with new summary"""
        if isinstance(summary, dict):
            self.context_memory.append(summary)
            if len(self.context_memory) > self.max_context_memory:
                self.context_memory.pop(0)

    def _combine_summaries(self, summaries: List[Dict]) -> Dict:
        """Combine chunk summaries with context awareness"""
        if not summaries:
            raise ValueError("No valid summaries to combine")

        combined = {
            "概要": "",
            "主要ポイント": [],
            "文脈の流れ": []
        }

        # Process summaries sequentially to maintain context
        for i, summary in enumerate(summaries):
            if not isinstance(summary, dict):
                continue

            # Add to overview
            if "概要" in summary:
                combined["概要"] += summary["概要"].strip() + " "

            # Add main points with deduplication
            if "主要ポイント" in summary:
                for point in summary["主要ポイント"]:
                    if isinstance(point, dict) and "タイトル" in point:
                        if not any(p["タイトル"] == point["タイトル"] 
                                 for p in combined["主要ポイント"]):
                            combined["主要ポイント"].append(point)

            # Track context flow
            if "文脈連携" in summary:
                combined["文脈の流れ"].append({
                    "セクション": f"セクション {i+1}",
                    "関連性": summary["文脈連携"].get("前の内容との関連", ""),
                    "継続トピック": summary["文脈連携"].get("継続するトピック", []),
                    "新規トピック": summary["文脈連携"].get("新規トピック", [])
                })

        return combined

    def _format_summary(self, combined: Dict) -> str:
        """Format combined summary into readable markdown"""
        sections = []

        # Add overview
        if "概要" in combined:
            sections.append(f"## 全体の要約\n\n{combined['概要'].strip()}\n")

        # Add main points
        if "主要ポイント" in combined and combined["主要ポイント"]:
            sections.append("## 主要ポイント\n")
            for point in combined["主要ポイント"]:
                if isinstance(point, dict):
                    title = point.get("タイトル", "")
                    desc = point.get("説明", "")
                    importance = point.get("重要度", 3)
                    stars = "⭐" * importance
                    sections.append(f"### {title} {stars}\n{desc}\n")

        # Add context flow
        if "文脈の流れ" in combined and combined["文脈の流れ"]:
            sections.append("## 文脈の流れ\n")
            for flow in combined["文脈の流れ"]:
                sections.append(f"### {flow['セクション']}\n")
                if flow['関連性']:
                    sections.append(f"前のセクションとの関連：{flow['関連性']}\n")
                if flow['継続トピック']:
                    sections.append("継続しているトピック:\n" + 
                                 "\n".join(f"- {topic}" for topic in flow['継続トピック']) + "\n")
                if flow['新規トピック']:
                    sections.append("新しく導入されたトピック:\n" + 
                                 "\n".join(f"- {topic}" for topic in flow['新規トピック']) + "\n")

        return "\n".join(sections)

if __name__ == "__main__":
    import sys

    async def main():
        text_processor = TextProcessor()
        url = sys.argv[1]  # コマンドライン引数からYouTubeのURLを取得
        transcript = text_processor.get_transcript(url)
        summary = await text_processor.generate_summary(transcript)
        print(summary)

    asyncio.run(main())