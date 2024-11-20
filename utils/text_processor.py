import os
import json
import google.generativeai as genai
from youtube_transcript_api import YouTubeTranscriptApi
import logging

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
        """YouTubeの字幕を取得"""
        try:
            video_id = url.split("v=")[-1].split("&")[0]
            
            # Check cache first
            cache_key = f"transcript_{video_id}"
            if cache_key in self._cache:
                return self._cache[cache_key]

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
            "key_themes": []
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
        
        # Remove duplicates
        context["continuing_themes"] = list(set(context["continuing_themes"]))
        return context

    def _create_summary_prompt(self, chunk: str, context: dict) -> str:
        """コンテキストを考慮した要約プロンプトを生成"""
        prompt = f'''
        以下のテキストを要約してください。元の文章の30%程度の長さに抑え、簡潔に重要なポイントを抽出してください。

        前のセクションからの文脈情報：
        - 継続中のトピック: {", ".join(context.get("continuing_themes", []))}
        - 主要テーマ: {json.dumps([theme["topic"] for theme in context.get("key_themes", [])[:3]], ensure_ascii=False)}
        
        テキスト:
        {chunk}
        
        出力フォーマット:
        {{
            "主要ポイント": [
                {{
                    "タイトル": "簡潔なトピック",
                    "説明": "30文字以内の説明",
                    "重要度": 1-5の数値
                }}
            ],
            "詳細分析": [
                {{
                    "セクション": "セクション名",
                    "キーポイント": ["重要ポイント（各15文字以内）"]
                }}
            ],
            "文脈連携": {{
                "継続するトピック": ["トピック名"],
                "新規トピック": ["新トピック名"]
            }},
            "キーワード": [
                {{
                    "用語": "キーワード",
                    "説明": "20文字以内の説明"
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
                
                # Add main points
                formatted_text.append("### 主要ポイント")
                for point in summary["主要ポイント"]:
                    importance = "🔥" * point.get("重要度", 1)
                    formatted_text.append(f"- {point['タイトル']} {importance}")
                    if "説明" in point:
                        formatted_text.append(f"  - {point['説明']}")
                        
                # Add detailed analysis
                formatted_text.append("\n### 詳細分析")
                for analysis in summary["詳細分析"]:
                    formatted_text.append(f"#### {analysis['セクション']}")
                    for point in analysis.get("キーポイント", []):
                        formatted_text.append(f"- {point}")
                        
                # Add keywords
                formatted_text.append("\n### キーワード")
                for keyword in summary["キーワード"]:
                    formatted_text.append(f"- **{keyword['用語']}**: {keyword['説明']}")
                    
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
