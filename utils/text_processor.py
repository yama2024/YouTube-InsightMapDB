import os
import json
import google.generativeai as genai
from youtube_transcript_api import YouTubeTranscriptApi
import logging
import re

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TextProcessor:
    def __init__(self):
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("Gemini API key is not set in environment variables")
        
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-pro')
        self._cache = {}

    def get_transcript(self, url):
        try:
            # Extract video ID from URL
            if "youtu.be" in url:
                video_id = url.split("/")[-1].split("?")[0]
            else:
                # Try to extract ID from regular YouTube URL
                patterns = [
                    r"(?:v=|\/)([0-9A-Za-z_-]{11}).*",
                    r"(?:embed\/)([0-9A-Za-z_-]{11})",
                    r"(?:watch\?v=)([0-9A-Za-z_-]{11})"
                ]
                video_id = None
                for pattern in patterns:
                    match = re.search(pattern, url)
                    if match:
                        video_id = match.group(1)
                        break
            
            if not video_id:
                raise ValueError("Invalid YouTube URL format")
                
            # Check cache first
            cache_key = f"transcript_{video_id}"
            if cache_key in self._cache:
                return self._cache[cache_key]
                
            # Get transcript
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['ja', 'en'])
            transcript = ' '.join([entry['text'] for entry in transcript_list])
            
            # Cache the result
            self._cache[cache_key] = transcript
            return transcript
            
        except Exception as e:
            logger.error(f"字幕の取得中にエラーが発生しました: {str(e)}")
            raise Exception(f"字幕の取得に失敗しました: {str(e)}")

    def _validate_json_response(self, response_text: str) -> dict:
        """JSON responseのバリデーション"""
        try:
            # Clean up the response text
            cleaned_text = response_text.strip()
            if cleaned_text.startswith('```json'):
                cleaned_text = cleaned_text[7:]
            if cleaned_text.endswith('```'):
                cleaned_text = cleaned_text[:-3]
                
            # Try to parse JSON
            data = json.loads(cleaned_text)
            
            # Validate required fields
            required_fields = ["主要ポイント", "詳細分析", "文脈連携", "キーワード"]
            if not all(field in data for field in required_fields):
                logger.warning("Missing required fields in JSON response")
                return None
                
            return data
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error validating JSON response: {str(e)}")
            return None

    def _get_chunk_context(self, previous_summaries: list) -> dict:
        """前のセクションからコンテキスト情報を抽出"""
        context = {
            "continuing_themes": [],
            "key_themes": [],
            "importance_factors": []
        }
        
        if not previous_summaries:
            return context
            
        # Get themes from previous summaries
        for summary in previous_summaries[-2:]:  # Look at last 2 summaries
            if "文脈連携" in summary:
                context["continuing_themes"].extend(summary["文脈連携"].get("継続するトピック", []))
                
            if "主要ポイント" in summary:
                for point in summary["主要ポイント"]:
                    if point.get("重要度", 0) >= 4:  # Only include high importance points
                        context["key_themes"].append({
                            "topic": point["タイトル"],
                            "importance": point["重要度"]
                        })
                        
            # Extract importance factors based on keyword frequency and context
            if "キーワード" in summary:
                for keyword in summary["キーワード"]:
                    context["importance_factors"].append({
                        "term": keyword["用語"],
                        "weight": 1.0
                    })
        
        # Remove duplicates and normalize weights
        context["continuing_themes"] = list(set(context["continuing_themes"]))
        context["importance_factors"] = self._normalize_importance_weights(context["importance_factors"])
        return context

    def _normalize_importance_weights(self, factors: list) -> list:
        """重要度の重みを正規化"""
        if not factors:
            return []
            
        # Calculate total weight
        total_weight = sum(factor["weight"] for factor in factors)
        
        # Normalize weights
        if total_weight > 0:
            return [{
                "term": factor["term"],
                "weight": factor["weight"] / total_weight
            } for factor in factors]
        return factors

    def _create_summary_prompt(self, chunk: str, context: dict) -> str:
        """コンテキストを考慮した要約プロンプトを生成"""
        prompt = f'''
        以下のテキストを要約してください。文脈を考慮し、前のセクションとの関連性を維持しながら、
        元の文章の30%程度の長さに抑え、簡潔に重要なポイントを抽出してください。

        前のセクションからの文脈情報：
        - 継続中のトピック: {", ".join(context.get("continuing_themes", []))}
        - 主要テーマ: {json.dumps([theme["topic"] for theme in context.get("key_themes", [])[:3]], ensure_ascii=False)}
        - 重要キーワード: {json.dumps([{
            "term": factor["term"],
            "weight": f"{factor['weight']:.2f}"
        } for factor in context.get("importance_factors", [])[:5]], ensure_ascii=False)}
        
        テキスト:
        {chunk}
        
        出力フォーマット:
        {{
            "主要ポイント": [
                {{
                    "タイトル": "簡潔なトピック",
                    "説明": "30文字以内の説明",
                    "重要度": 1-5の数値,
                    "文脈関連度": 0-1の数値
                }}
            ],
            "詳細分析": [
                {{
                    "セクション": "セクション名",
                    "キーポイント": ["重要ポイント（各15文字以内）"],
                    "前セクションとの関連": ["関連するポイント"]
                }}
            ],
            "文脈連携": {{
                "継続するトピック": ["トピック名"],
                "新規トピック": ["新トピック名"],
                "トピック関連度": 0-1の数値
            }},
            "キーワード": [
                {{
                    "用語": "キーワード",
                    "説明": "20文字以内の説明",
                    "重要度": 1-5の数値
                }}
            ]
        }}
        '''
        return prompt

    def _chunk_text(self, text: str, chunk_size: int = 1500) -> list:
        """テキストを適切なサイズのチャンクに分割"""
        words = text.split()
        chunks = []
        current_chunk = []
        current_length = 0
        
        for word in words:
            word_length = len(word)
            if current_length + word_length + 1 <= chunk_size:
                current_chunk.append(word)
                current_length += word_length + 1
            else:
                chunks.append(' '.join(current_chunk))
                current_chunk = [word]
                current_length = word_length
                
        if current_chunk:
            chunks.append(' '.join(current_chunk))
            
        return chunks

    def _format_summaries(self, summaries: list) -> str:
        """要約をフォーマット"""
        try:
            formatted_text = []
            
            for i, summary in enumerate(summaries, 1):
                formatted_text.append(f"## セクション {i}\n")
                
                # Add main points with context relevance
                formatted_text.append("### 主要ポイント")
                for point in summary["主要ポイント"]:
                    importance = "🔥" * point.get("重要度", 1)
                    context_relevance = f"(文脈関連度: {point.get('文脈関連度', 0):.1f})"
                    formatted_text.append(f"- {point['タイトル']} {importance} {context_relevance}")
                    if "説明" in point:
                        formatted_text.append(f"  - {point['説明']}")
                        
                # Add detailed analysis with context connections
                formatted_text.append("\n### 詳細分析")
                for analysis in summary["詳細分析"]:
                    formatted_text.append(f"#### {analysis['セクション']}")
                    for point in analysis.get("キーポイント", []):
                        formatted_text.append(f"- {point}")
                    if "前セクションとの関連" in analysis:
                        formatted_text.append("\n*前セクションとの関連:*")
                        for relation in analysis["前セクションとの関連"]:
                            formatted_text.append(f"- → {relation}")
                        
                # Add context linkage information
                if "文脈連携" in summary:
                    formatted_text.append("\n### 文脈連携")
                    context_info = summary["文脈連携"]
                    if "トピック関連度" in context_info:
                        formatted_text.append(f"*トピック関連度: {context_info['トピック関連度']:.1f}*")
                    if context_info.get("継続するトピック"):
                        formatted_text.append("\n**継続するトピック:**")
                        for topic in context_info["継続するトピック"]:
                            formatted_text.append(f"- {topic}")
                    if context_info.get("新規トピック"):
                        formatted_text.append("\n**新規トピック:**")
                        for topic in context_info["新規トピック"]:
                            formatted_text.append(f"- {topic}")
                            
                # Add keywords with importance
                formatted_text.append("\n### キーワード")
                for keyword in summary["キーワード"]:
                    importance = "⭐" * keyword.get("重要度", 1)
                    formatted_text.append(f"- **{keyword['用語']}** {importance}: {keyword['説明']}")
                    
                formatted_text.append("\n---\n")
                
            return "\n".join(formatted_text)
            
        except Exception as e:
            logger.error(f"Error formatting summaries: {str(e)}")
            return "要約のフォーマットに失敗しました。"

    def generate_summary(self, text: str) -> str:
        """コンテキストを考慮した要約を生成"""
        try:
            chunks = self._chunk_text(text)
            summaries = []
            previous_summaries = []
            
            for i, chunk in enumerate(chunks):
                context = self._get_chunk_context(previous_summaries)
                
                # Add retry logic for API calls
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        response = self.model.generate_content(
                            self._create_summary_prompt(chunk, context),
                            generation_config=genai.types.GenerationConfig(
                                temperature=0.3,
                                top_p=0.8,
                                top_k=40,
                                max_output_tokens=8192,
                            )
                        )
                        
                        if not response.text:
                            continue
                            
                        result = self._validate_json_response(response.text)
                        if result:
                            summaries.append(result)
                            previous_summaries.append(result)
                            break
                    except Exception as e:
                        logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")
                        if attempt == max_retries - 1:
                            logger.error(f"All attempts failed for chunk {i}")
            
            if not summaries:
                raise ValueError("No valid summaries generated")
                
            return self._format_summaries(summaries)
            
        except Exception as e:
            logger.error(f"Error in summary generation: {str(e)}")
            raise Exception(f"Failed to generate summary: {str(e)}")
