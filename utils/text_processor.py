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

    def _build_topic_hierarchy(self, summaries: List[Dict]) -> Dict:
        """Build topic hierarchy from previous summaries with improved context tracking"""
        hierarchy = {
            "main_topics": [],
            "subtopics": {},
            "relationships": [],
            "topic_importance": {}
        }
        
        for summary in summaries:
            if "主要ポイント" in summary:
                for point in summary["主要ポイント"]:
                    topic = point.get("タイトル", "")
                    importance = point.get("重要度", 1)
                    if topic:
                        if topic not in hierarchy["main_topics"]:
                            hierarchy["main_topics"].append(topic)
                            hierarchy["subtopics"][topic] = []
                            hierarchy["topic_importance"][topic] = importance
                        else:
                            # Update importance if topic is mentioned again
                            hierarchy["topic_importance"][topic] = max(
                                hierarchy["topic_importance"][topic],
                                importance
                            )
                    
            if "詳細分析" in summary:
                for analysis in summary["詳細分析"]:
                    section = analysis.get("セクション", "")
                    points = analysis.get("キーポイント", [])
                    if section in hierarchy["main_topics"]:
                        # Avoid duplicate subtopics
                        new_points = [p for p in points if p not in hierarchy["subtopics"][section]]
                        hierarchy["subtopics"][section].extend(new_points)
                        
                        # Track relationships between topics
                        for point in new_points:
                            for topic in hierarchy["main_topics"]:
                                if topic != section and any(word in point for word in topic.split()):
                                    relationship = {"from": section, "to": topic, "context": point}
                                    if relationship not in hierarchy["relationships"]:
                                        hierarchy["relationships"].append(relationship)
                    
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
            "topic_transitions": []
        }
        
        if not previous_summaries:
            return context

        # Build enhanced topic hierarchy
        context["topic_hierarchy"] = self._build_topic_hierarchy(previous_summaries)
        
        # Analyze last 3 summaries for immediate context with improved tracking
        recent_summaries = previous_summaries[-3:]
        previous_topics = set()
        
        for summary in recent_summaries:
            current_topics = set()
            
            # Track topics and their importance
            if "主要ポイント" in summary:
                for point in summary["主要ポイント"]:
                    topic = point.get("タイトル", "")
                    importance = point.get("重要度", 1)
                    if topic:
                        current_topics.add(topic)
                        context["previous_topics"].append(topic)
                        context["importance_scores"][topic] = importance
            
            # Track topic transitions
            if previous_topics:
                context["topic_transitions"].append({
                    "from": list(previous_topics),
                    "to": list(current_topics)
                })
            previous_topics = current_topics
            
            # Track continuing themes with improved context
            if "文脈連携" in summary:
                themes = summary["文脈連携"].get("継続するトピック", [])
                context["continuing_themes"].extend(themes)
                
                # Track new topics for context transitions
                new_topics = summary["文脈連携"].get("新規トピック", [])
                if new_topics:
                    context["topic_transitions"].append({
                        "type": "new_topics",
                        "topics": new_topics
                    })
                
            # Build enhanced related terms dictionary with context
            if "キーワード" in summary:
                for keyword in summary["キーワード"]:
                    term = keyword.get("用語", "")
                    if term:
                        context["related_terms"][term] = {
                            "説明": keyword.get("説明", ""),
                            "関連トピック": [
                                topic for topic in context["previous_topics"]
                                if term in topic or topic in term
                            ]
                        }
        
        # Remove duplicates while preserving order
        context["previous_topics"] = list(dict.fromkeys(context["previous_topics"]))
        context["continuing_themes"] = list(dict.fromkeys(context["continuing_themes"]))
        
        return context

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

    def generate_summary(self, text: str) -> str:
        """Generate context-aware summary using Gemini API"""
        try:
            chunks = self._chunk_text(text)
            summaries = []
            previous_summaries = []
            
            for i, chunk in enumerate(chunks):
                # Get enhanced context from previous summaries
                context = self._get_chunk_context(previous_summaries)
                
                # Build prompt with enhanced context
                prompt = f'''
                以下のテキストを要約し、文脈を考慮したJSONフォーマットで出力してください。

                前のセクションからの文脈情報：
                - 継続中のトピック: {", ".join(context["continuing_themes"])}
                - 重要キーワード: {json.dumps(context["related_terms"], ensure_ascii=False)}
                - トピック階層: {json.dumps(context["topic_hierarchy"], ensure_ascii=False)}
                
                テキスト:
                {chunk}
                
                出力フォーマット:
                {{
                    "主要ポイント": [
                        {{"タイトル": "トピック", "重要度": 1-5の数値, "前セクションとの関連": "説明"}}
                    ],
                    "詳細分析": [
                        {{"セクション": "セクション名", "キーポイント": ["ポイント1", "ポイント2"], "文脈説明": "前セクションとの関連性"}}
                    ],
                    "文脈連携": {{
                        "継続するトピック": ["トピック1", "トピック2"],
                        "新規トピック": ["新トピック1", "新トピック2"],
                        "トピック遷移": "トピック間の関連性の説明"
                    }},
                    "キーワード": [
                        {{"用語": "キーワード", "説明": "説明文", "関連トピック": ["関連トピック1", "関連トピック2"]}}
                    ]
                }}
                '''
                
                response = self.model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.3,
                        top_p=0.8,
                        top_k=40,
                        max_output_tokens=8192,
                    )
                )
                
                try:
                    summary_data = json.loads(response.text)
                    previous_summaries.append(summary_data)
                    
                    # Format summary with enhanced context awareness
                    formatted_summary = self._format_summary(summary_data, i == 0, context)
                    summaries.append(formatted_summary)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse JSON from chunk {i}, using raw text")
                    summaries.append(response.text)
            
            return "\n\n".join(summaries)
            
        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            raise Exception(f"Failed to generate summary: {str(e)}")

    def _format_summary(self, summary_data: Dict, is_first_chunk: bool = False, context: Dict = None) -> str:
        """Format summary data into readable markdown with enhanced context awareness"""
        lines = []
        
        # Add header for first chunk
        if is_first_chunk:
            lines.append("# 📝 コンテンツ要約")
        
        # Add main points with context
        if "主要ポイント" in summary_data:
            lines.append("\n## 🎯 主要ポイント")
            for point in summary_data["主要ポイント"]:
                stars = "⭐" * point.get("重要度", 1)
                title = point['タイトル']
                context_info = point.get("前セクションとの関連", "")
                
                if context_info:
                    lines.append(f"- **{title}** {stars}\n  > {context_info}")
                else:
                    lines.append(f"- **{title}** {stars}")
        
        # Add detailed analysis with context
        if "詳細分析" in summary_data:
            lines.append("\n## 📊 詳細分析")
            for analysis in summary_data["詳細分析"]:
                section = analysis['セクション']
                context_explanation = analysis.get("文脈説明", "")
                
                if context_explanation:
                    lines.append(f"\n### {section}\n> {context_explanation}")
                else:
                    lines.append(f"\n### {section}")
                    
                for point in analysis['キーポイント']:
                    lines.append(f"- {point}")
        
        # Add context connections
        if "文脈連携" in summary_data:
            lines.append("\n## 🔄 文脈の連続性")
            context_data = summary_data["文脈連携"]
            
            if context_data.get("トピック遷移"):
                lines.append(f"\n**トピックの展開**: {context_data['トピック遷移']}")
            
            if context_data.get("継続するトピック"):
                lines.append("\n**継続するトピック**:")
                for topic in context_data["継続するトピック"]:
                    lines.append(f"- {topic}")
            
            if context_data.get("新規トピック"):
                lines.append("\n**新しく導入されたトピック**:")
                for topic in context_data["新規トピック"]:
                    lines.append(f"- {topic}")
        
        # Add keywords with enhanced context
        if "キーワード" in summary_data:
            lines.append("\n## 🔍 重要キーワード")
            for keyword in summary_data["キーワード"]:
                term = keyword['用語']
                description = keyword['説明']
                related_topics = keyword.get("関連トピック", [])
                
                if related_topics:
                    topics_str = ", ".join(related_topics)
                    lines.append(f"- **{term}**: {description}\n  > 関連トピック: {topics_str}")
                else:
                    lines.append(f"- **{term}**: {description}")
        
        return "\n".join(lines)
