import os
import google.generativeai as genai
import logging
import json
from typing import List, Dict, Optional
from youtube_transcript_api import YouTubeTranscriptApi
from cachetools import TTLCache
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
        self.model = genai.GenerativeModel('gemini-1.5-pro')
        self._cache = TTLCache(maxsize=100, ttl=3600)  # 1-hour cache
        self._context_memory = []  # Store context across multiple summaries

    def _extract_video_id(self, url: str) -> str:
        """Extract video ID from YouTube URL"""
        if "youtu.be" in url:
            return url.split("/")[-1].split("?")[0]
        
        patterns = [
            r"(?:v=|\/)([0-9A-Za-z_-]{11}).*",
            r"(?:embed\/)([0-9A-Za-z_-]{11})",
            r"(?:watch\?v=)([0-9A-Za-z_-]{11})"
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        raise ValueError("Invalid YouTube URL format")

    def _validate_json_response(self, response_text: str) -> Optional[Dict]:
        try:
            # First, clean up the response text
            cleaned_text = response_text.strip()
            # Remove any markdown code block markers if present
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

    def _format_summaries(self, summaries: List[Dict]) -> str:
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

    def _create_summary_prompt(self, chunk: str, context: Dict) -> str:
        """Create a context-aware summary prompt"""
        prompt = f'''
        以下のテキストを要約し、文脈を考慮したJSONフォーマットで出力してください。

        前のセクションからの文脈情報：
        - 継続中のトピック: {", ".join(context.get("continuing_themes", []))}
        - 主要テーマ: {json.dumps([theme["topic"] for theme in context.get("key_themes", [])[:3]], ensure_ascii=False)}
        - トピック間の関連: {json.dumps(context.get("topic_connections", [])[:3], ensure_ascii=False)}
        - トピック階層: {json.dumps(context.get("topic_hierarchy", {}), ensure_ascii=False)}
        
        テキスト:
        {chunk}
        
        出力フォーマット:
        {{
            "主要ポイント": [
                {{
                    "タイトル": "トピック",
                    "重要度": 1-5の数値,
                    "前セクションとの関連": "説明",
                    "継続性": "新規/継続/発展"
                }}
            ],
            "詳細分析": [
                {{
                    "セクション": "セクション名",
                    "キーポイント": ["ポイント1", "ポイント2"],
                    "文脈説明": "前セクションとの関連性",
                    "発展度": "基礎/応用/深化"
                }}
            ],
            "文脈連携": {{
                "継続するトピック": ["トピック1", "トピック2"],
                "新規トピック": ["新トピック1", "新トピック2"],
                "トピック遷移": "トピック間の関連性の説明",
                "理解度要件": "前セクションの理解が必要な度合い（1-5）"
            }},
            "キーワード": [
                {{
                    "用語": "キーワード",
                    "説明": "説明文",
                    "関連トピック": ["関連トピック1", "関連トピック2"],
                    "重要度": 1-5の数値
                }}
            ]
        }}
        '''
        return prompt

    def generate_summary(self, text: str) -> str:
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
                
            # Format final summary
            return self._format_summaries(summaries)
            
        except Exception as e:
            logger.error(f"Error in summary generation: {str(e)}")
            raise Exception(f"Failed to generate summary: {str(e)}")

    def get_transcript(self, youtube_url: str) -> str:
        """Get transcript from YouTube video with improved error handling"""
        try:
            # Extract video ID
            video_id = self._extract_video_id(youtube_url)
            
            # Check cache first
            cache_key = f"transcript_{video_id}"
            if cache_key in self._cache:
                return self._cache[cache_key]
            
            # Try Japanese transcript first
            try:
                transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['ja'])
            except Exception as e:
                logger.warning(f"Japanese transcript not available: {str(e)}")
                # Fallback to English
                try:
                    transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['en'])
                except Exception as e:
                    logger.error(f"Failed to get transcript in both Japanese and English: {str(e)}")
                    raise Exception("No transcript available in Japanese or English")

            # Combine transcript entries with proper text cleaning
            full_text = ""
            for entry in transcript:
                text = entry.get('text', '').strip()
                if text:
                    # Remove redundant whitespace and normalize punctuation
                    text = re.sub(r'\s+', ' ', text)
                    text = text.replace(' .', '.').replace(' ,', ',')
                    full_text += text + " "

            full_text = full_text.strip()
            if not full_text:
                raise ValueError("Empty transcript")

            # Cache the result
            self._cache[cache_key] = full_text
            return full_text

        except Exception as e:
            logger.error(f"Error getting transcript: {str(e)}")
            raise Exception(f"Failed to get transcript: {str(e)}")

    def _chunk_text(self, text: str, chunk_size: int = 1000) -> List[str]:
        """Split text into manageable chunks while preserving context and semantic boundaries"""
        # First, split by obvious break points
        paragraphs = text.split('\n\n')
        chunks = []
        current_chunk = []
        current_length = 0
        
        for paragraph in paragraphs:
            # Further split long paragraphs
            if len(paragraph) > chunk_size:
                sentences = re.split(r'([。.!?！？] )', paragraph)
                for i in range(0, len(sentences), 2):
                    sentence = sentences[i] + (sentences[i+1] if i+1 < len(sentences) else '')
                    sentence_length = len(sentence)
                    
                    if current_length + sentence_length > chunk_size and current_chunk:
                        chunks.append(' '.join(current_chunk))
                        current_chunk = []
                        current_length = 0
                    
                    current_chunk.append(sentence)
                    current_length += sentence_length
            else:
                if current_length + len(paragraph) > chunk_size and current_chunk:
                    chunks.append(' '.join(current_chunk))
                    current_chunk = []
                    current_length = 0
                
                current_chunk.append(paragraph)
                current_length += len(paragraph)
        
        if current_chunk:
            chunks.append(' '.join(current_chunk))
        
        return chunks

    def _build_topic_hierarchy(self, summaries: List[Dict]) -> Dict:
        """Build topic hierarchy from previous summaries with improved context tracking"""
        hierarchy = {
            "main_topics": [],
            "subtopics": {},
            "relationships": [],
            "topic_importance": {},
            "topic_flow": [],
            "context_connections": {}
        }
        
        for summary in summaries:
            if "主要ポイント" in summary:
                for point in summary["主要ポイント"]:
                    topic = point.get("タイトル", "")
                    importance = point.get("重要度", 1)
                    context = point.get("前セクションとの関連", "")
                    
                    if topic:
                        if topic not in hierarchy["main_topics"]:
                            hierarchy["main_topics"].append(topic)
                            hierarchy["subtopics"][topic] = []
                            hierarchy["topic_importance"][topic] = importance
                            hierarchy["context_connections"][topic] = context
                            
                            # Track topic flow
                            if hierarchy["topic_flow"]:
                                hierarchy["topic_flow"].append({
                                    "from": hierarchy["topic_flow"][-1]["topic"],
                                    "to": topic,
                                    "transition_context": context
                                })
                            hierarchy["topic_flow"].append({"topic": topic, "importance": importance})
                        else:
                            # Update importance and merge context if topic is mentioned again
                            hierarchy["topic_importance"][topic] = max(
                                hierarchy["topic_importance"][topic],
                                importance
                            )
                            if context:
                                existing_context = hierarchy["context_connections"].get(topic, "")
                                hierarchy["context_connections"][topic] = f"{existing_context} {context}".strip()
                    
            if "詳細分析" in summary:
                for analysis in summary["詳細分析"]:
                    section = analysis.get("セクション", "")
                    points = analysis.get("キーポイント", [])
                    context_explanation = analysis.get("文脈説明", "")
                    
                    if section in hierarchy["main_topics"]:
                        # Avoid duplicate subtopics while preserving context
                        new_points = []
                        for point in points:
                            if point not in hierarchy["subtopics"][section]:
                                new_points.append(point)
                                
                                # Check for cross-references with other topics
                                for other_topic in hierarchy["main_topics"]:
                                    if other_topic != section and (
                                        other_topic.lower() in point.lower() or
                                        any(sub.lower() in point.lower() 
                                            for sub in hierarchy["subtopics"].get(other_topic, []))
                                    ):
                                        relationship = {
                                            "from": section,
                                            "to": other_topic,
                                            "context": point,
                                            "type": "cross_reference"
                                        }
                                        if relationship not in hierarchy["relationships"]:
                                            hierarchy["relationships"].append(relationship)
                        
                        hierarchy["subtopics"][section].extend(new_points)
                        
                        # Update context connections
                        if context_explanation:
                            existing_context = hierarchy["context_connections"].get(section, "")
                            hierarchy["context_connections"][section] = f"{existing_context} {context_explanation}".strip()
                    
        return hierarchy

    def _get_chunk_context(self, previous_summaries: List[Dict]) -> Dict:
        """Get enhanced context from previous chunks for better continuity"""
        context = {
            "previous_topics": [],
            "key_points": [],
            "continuing_themes": [],
            "topic_hierarchy": {},
            "importance_scores": {},
            "related_terms": {},
            "topic_transitions": [],
            "context_memory": self._context_memory.copy()  # Use persistent context memory
        }
        
        if not previous_summaries:
            return context

        # Build enhanced topic hierarchy with improved context tracking
        context["topic_hierarchy"] = self._build_topic_hierarchy(previous_summaries)
        
        # Analyze all summaries for global context patterns
        all_topics = set()
        topic_frequency = {}
        topic_connections = {}
        
        for summary in previous_summaries:
            current_topics = set()
            
            # Track topics and their importance
            if "主要ポイント" in summary:
                for point in summary["主要ポイント"]:
                    topic = point.get("タイトル", "")
                    importance = point.get("重要度", 1)
                    if topic:
                        current_topics.add(topic)
                        all_topics.add(topic)
                        topic_frequency[topic] = topic_frequency.get(topic, 0) + 1
                        context["importance_scores"][topic] = max(
                            context["importance_scores"].get(topic, 0),
                            importance
                        )
            
            # Track topic connections
            for topic1 in current_topics:
                for topic2 in current_topics:
                    if topic1 != topic2:
                        key = tuple(sorted([topic1, topic2]))
                        topic_connections[key] = topic_connections.get(key, 0) + 1
        
        # Identify strongest topic relationships
        strong_connections = [
            {"topics": list(topics), "strength": count}
            for topics, count in topic_connections.items()
            if count > 1  # Topics that appear together more than once
        ]
        context["topic_connections"] = strong_connections
        
        # Update context memory with new patterns
        self._context_memory.extend([
            {
                "type": "topic_pattern",
                "topics": list(topic_pair),
                "frequency": count,
                "timestamp": len(self._context_memory)
            }
            for topic_pair, count in topic_connections.items()
            if count > 1
        ])
        
        # Limit context memory size
        if len(self._context_memory) > 100:
            self._context_memory = self._context_memory[-100:]
        
        # Sort topics by frequency and importance
        context["key_themes"] = [
            {
                "topic": topic,
                "frequency": topic_frequency[topic],
                "importance": context["importance_scores"].get(topic, 1)
            }
            for topic in all_topics
        ]
        context["key_themes"].sort(
            key=lambda x: (x["frequency"], x["importance"]),
            reverse=True
        )
        
        return context
