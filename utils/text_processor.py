import google.generativeai as genai
import os
import re
import json
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from youtube_transcript_api import YouTubeTranscriptApi
from typing import Dict, List, Optional, Tuple

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TextProcessor:
    def __init__(self, max_workers: int = 3, chunk_size: int = 1000):
        """Initialize the TextProcessor with parallel processing capabilities"""
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("Gemini API key is not set in environment variables")
            
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-pro')
        self._cache = {}
        self.max_workers = max_workers
        self.chunk_size = chunk_size

    def get_transcript(self, video_url: str) -> str:
        """Get transcript from YouTube video"""
        try:
            video_id = self._extract_video_id(video_url)
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            
            # Try Japanese first, then English, then manual
            for lang in ['ja', 'en', 'a.ja', 'a.en']:
                try:
                    transcript = transcript_list.find_transcript([lang])
                    return ' '.join(entry['text'] for entry in transcript.fetch())
                except Exception as e:
                    logger.debug(f"Failed to get transcript in {lang}: {str(e)}")
                    continue
                    
            raise ValueError("No suitable transcript found")
            
        except Exception as e:
            logger.error(f"Transcript extraction failed: {str(e)}")
            raise ValueError(f"Failed to get transcript: {str(e)}")

    def _extract_video_id(self, url: str) -> str:
        """Extract video ID from YouTube URL"""
        patterns = [
            r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
            r'(?:embed\/)([0-9A-Za-z_-]{11})',
            r'(?:watch\?v=)([0-9A-Za-z_-]{11})'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        raise ValueError("Invalid YouTube URL format")

    def _split_text(self, text: str) -> List[str]:
        """Split text into chunks with proper sentence boundaries"""
        sentences = re.split(r'([。.!?！？]+)', text)
        chunks = []
        current_chunk = ""
        
        for i in range(0, len(sentences)-1, 2):
            sentence = sentences[i] + (sentences[i+1] if i+1 < len(sentences) else '')
            if len(current_chunk) + len(sentence) > self.chunk_size:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = sentence
            else:
                current_chunk += sentence
                
        if current_chunk:
            chunks.append(current_chunk)
            
        return chunks

    def _create_summary_prompt(self, text: str) -> str:
        """Create a prompt for the summary generation"""
        return f'''
テキストを要約して、以下の形式で出力してください：

{{
    "主要ポイント": [
        {{
            "タイトル": "トピック",
            "説明": "詳細説明",
            "重要度": 3
        }}
    ]
}}

テキストの内容:
{text}

注意事項:
- 重要度は1から5の整数で表現
- タイトルは簡潔に
- 説明は具体的に
'''

    def _process_chunk_with_retry(self, chunk: str, chunk_index: int) -> Dict:
        """Process a single chunk with retry logic"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                logger.info(f"Processing chunk {chunk_index + 1}, attempt {attempt + 1}")
                response = self.model.generate_content(
                    self._create_summary_prompt(chunk),
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.3,
                        top_p=0.8,
                        top_k=40,
                        max_output_tokens=4096,
                    )
                )
                
                if not response or not response.text:
                    logger.warning(f"Empty response for chunk {chunk_index + 1}")
                    continue
                    
                # Always return a valid summary structure
                return self._validate_summary_response(response.text)
                
            except Exception as e:
                logger.error(f"Error processing chunk {chunk_index + 1}: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
        
        # Return minimal valid structure if all retries fail
        return {
            "主要ポイント": [{
                "タイトル": f"チャンク {chunk_index + 1}",
                "説明": "処理中にエラーが発生しました。",
                "重要度": 1
            }]
        }

    def _validate_summary_response(self, response_text: str) -> dict:
        """Validate and clean up the summary response"""
        try:
            # Extract JSON from response
            json_str = response_text.strip()
            json_match = re.search(r'({[\s\S]*})', json_str)
            if json_match:
                json_str = json_match.group(1)
                
            # Remove code blocks if present
            if '```' in json_str:
                json_str = re.sub(r'```(?:json)?(.*?)```', r'\1', json_str, flags=re.DOTALL)
            
            # Parse JSON with minimal validation
            data = json.loads(json_str)
            
            # Ensure basic structure exists
            if not isinstance(data, dict):
                data = {"主要ポイント": []}
            
            # Add missing sections with defaults
            if "主要ポイント" not in data or not data["主要ポイント"]:
                data["主要ポイント"] = [{
                    "タイトル": "主要ポイント",
                    "説明": "テキストの要約",
                    "重要度": 3
                }]
                
            return data
            
        except Exception as e:
            logger.error(f"Response validation failed: {str(e)}")
            # Return minimal valid structure
            return {
                "主要ポイント": [{
                    "タイトル": "エラー",
                    "説明": "要約の生成中にエラーが発生しました",
                    "重要度": 1
                }]
            }

    def _merge_summaries(self, summaries: List[Dict]) -> Dict:
        """Merge multiple chunk summaries into one coherent summary"""
        merged = {"主要ポイント": []}
        
        for summary in summaries:
            if "主要ポイント" in summary:
                merged["主要ポイント"].extend(summary["主要ポイント"])
                
        return merged

    def evaluate_summary_quality(self, original_text: str, summary_json: str) -> Dict[str, float]:
        """Evaluate the quality of the generated summary"""
        try:
            summary_data = json.loads(summary_json)
            quality_scores = {
                "構造の完全性": 0.0,
                "情報量": 0.0,
                "簡潔性": 0.0,
                "総合スコア": 0.0
            }

            # 構造の完全性をチェック (30%)
            structure_score = 0.0
            if isinstance(summary_data, dict) and "主要ポイント" in summary_data:
                points = summary_data["主要ポイント"]
                if isinstance(points, list) and points:
                    required_fields = {"タイトル", "説明", "重要度"}
                    field_scores = []
                    for point in points:
                        field_score = len(set(point.keys()) & required_fields) / len(required_fields)
                        field_scores.append(field_score)
                    structure_score = sum(field_scores) / len(field_scores)
            quality_scores["構造の完全性"] = structure_score * 10

            # 情報量を評価 (40%)
            total_content = ""
            for point in summary_data.get("主要ポイント", []):
                total_content += point.get("タイトル", "") + " " + point.get("説明", "")
            
            # 情報量スコアを計算
            original_length = len(original_text)
            summary_length = len(total_content)
            ideal_ratio = 0.3  # 理想的な要約は元のテキストの30%程度
            actual_ratio = summary_length / original_length
            information_score = max(0, 1 - abs(actual_ratio - ideal_ratio) / ideal_ratio)
            quality_scores["情報量"] = information_score * 10

            # 簡潔性を評価 (30%)
            conciseness_score = 0.0
            if summary_length > 0:
                # 重複フレーズをチェック
                phrases = re.findall(r'\b\w+(?:\s+\w+){2,}\b', total_content)
                unique_phrases = set(phrases)
                if phrases:
                    conciseness_score = len(unique_phrases) / len(phrases)
            quality_scores["簡潔性"] = conciseness_score * 10

            # 総合スコアを計算
            quality_scores["総合スコア"] = (
                quality_scores["構造の完全性"] * 0.3 +
                quality_scores["情報量"] * 0.4 +
                quality_scores["簡潔性"] * 0.3
            )

            return quality_scores

        except Exception as e:
            logger.error(f"要約品質の評価中にエラーが発生しました: {str(e)}")
            return {
                "構造の完全性": 0.0,
                "情報量": 0.0,
                "簡潔性": 0.0,
                "総合スコア": 0.0
            }

    def generate_summary(self, text: str) -> Tuple[str, Dict[str, float]]:
        """Generate a summary using parallel processing and evaluate its quality"""
        try:
            if not text or len(text.strip()) < 10:
                raise ValueError("テキストが短すぎるか空です")
                
            cache_key = hash(text)
            if cache_key in self._cache:
                summary = self._cache[cache_key]
                quality_scores = self.evaluate_summary_quality(text, summary)
                return summary, quality_scores
                
            chunks = self._split_text(text)
            summaries = []
            
            # Process chunks in parallel
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_chunk = {
                    executor.submit(self._process_chunk_with_retry, chunk, i): i
                    for i, chunk in enumerate(chunks)
                }
                
                for future in as_completed(future_to_chunk):
                    try:
                        summary = future.result()
                        if summary:
                            summaries.append(summary)
                    except Exception as e:
                        logger.error(f"Chunk processing failed: {str(e)}")

            if not summaries:
                logger.error("No valid summaries were generated")
                raise ValueError("要約の生成に失敗しました")

            try:
                merged_summary = self._merge_summaries(summaries)
                summary_json = json.dumps(merged_summary, ensure_ascii=False, indent=2)
                quality_scores = self.evaluate_summary_quality(text, summary_json)
                
                self._cache[cache_key] = summary_json
                return summary_json, quality_scores
            except Exception as e:
                logger.error(f"Error in summary finalization: {str(e)}")
                raise ValueError("要約の生成に失敗しました")
            
        except Exception as e:
            logger.error(f"要約の生成中にエラーが発生しました: {str(e)}")
            raise Exception(f"要約の生成に失敗しました: {str(e)}")
