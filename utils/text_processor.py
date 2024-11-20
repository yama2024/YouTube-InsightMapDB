import os
import google.generativeai as genai
import logging
import json
from typing import List, Dict, Optional
from youtube_transcript_api import YouTubeTranscriptApi
from cachetools import TTLCache

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

    def _build_topic_hierarchy(self, summaries: List[Dict]) -> Dict:
        """Build topic hierarchy from previous summaries"""
        hierarchy = {
            "main_topics": [],
            "subtopics": {},
            "relationships": []
        }
        
        for summary in summaries:
            if "主要ポイント" in summary:
                for point in summary["主要ポイント"]:
                    topic = point.get("タイトル", "")
                    if topic and topic not in hierarchy["main_topics"]:
                        hierarchy["main_topics"].append(topic)
                        hierarchy["subtopics"][topic] = []
                    
            if "詳細分析" in summary:
                for analysis in summary["詳細分析"]:
                    section = analysis.get("セクション", "")
                    points = analysis.get("キーポイント", [])
                    if section in hierarchy["main_topics"]:
                        hierarchy["subtopics"][section].extend(points)
                    
        return hierarchy

    def _get_chunk_context(self, previous_summaries: List[Dict]) -> Dict:
        """Get context from previous chunks for better continuity"""
        context = {
            "previous_topics": [],
            "key_points": [],
            "continuing_themes": [],
            "topic_hierarchy": {},
            "importance_scores": {},
            "related_terms": {}
        }
        
        if not previous_summaries:
            return context

        # Build topic hierarchy from previous summaries
        context["topic_hierarchy"] = self._build_topic_hierarchy(previous_summaries)
        
        # Analyze last 3 summaries for immediate context
        recent_summaries = previous_summaries[-3:]
        
        for summary in recent_summaries:
            # Track topics and their importance
            if "主要ポイント" in summary:
                for point in summary["主要ポイント"]:
                    topic = point.get("タイトル", "")
                    importance = point.get("重要度", 1)
                    if topic:
                        context["previous_topics"].append(topic)
                        context["importance_scores"][topic] = importance
            
            # Track continuing themes
            if "文脈連携" in summary:
                context["continuing_themes"].extend(
                    summary["文脈連携"].get("継続するトピック", [])
                )
                
            # Build related terms dictionary
            if "キーワード" in summary:
                for keyword in summary["キーワード"]:
                    term = keyword.get("用語", "")
                    if term:
                        context["related_terms"][term] = keyword.get("説明", "")
        
        # Remove duplicates while preserving order
        context["previous_topics"] = list(dict.fromkeys(context["previous_topics"]))
        context["continuing_themes"] = list(dict.fromkeys(context["continuing_themes"]))
        
        return context

    def _chunk_text(self, text: str, chunk_size: int = 1000) -> List[str]:
        """Split text into manageable chunks while preserving context"""
        words = text.split()
        chunks = []
        current_chunk = []
        current_length = 0
        
        for word in words:
            word_length = len(word)
            if current_length + word_length > chunk_size and current_chunk:
                chunks.append(" ".join(current_chunk))
                current_chunk = []
                current_length = 0
            current_chunk.append(word)
            current_length += word_length + 1  # +1 for space
            
        if current_chunk:
            chunks.append(" ".join(current_chunk))
            
        return chunks

    def get_transcript(self, youtube_url: str) -> str:
        """Get transcript from YouTube video"""
        try:
            # Extract video ID from URL
            video_id = youtube_url.split("v=")[1].split("&")[0]
            
            # Check cache first
            cache_key = f"transcript_{video_id}"
            if cache_key in self._cache:
                return self._cache[cache_key]
            
            # Get transcript
            transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['ja', 'en'])
            full_text = " ".join([entry['text'] for entry in transcript])
            
            # Cache the result
            self._cache[cache_key] = full_text
            return full_text
            
        except Exception as e:
            logger.error(f"Error getting transcript: {str(e)}")
            raise Exception(f"Failed to get transcript: {str(e)}")

    def generate_summary(self, text: str) -> str:
        """Generate context-aware summary using Gemini API"""
        try:
            chunks = self._chunk_text(text)
            summaries = []
            previous_summaries = []
            
            for i, chunk in enumerate(chunks):
                # Get context from previous summaries
                context = self._get_chunk_context(previous_summaries)
                
                # Build prompt with context
                prompt = f'''
                以下のテキストを要約し、JSONフォーマットで出力してください。
                前のセクションからの文脈情報：
                - 継続中のトピック: {", ".join(context["continuing_themes"])}
                - 重要キーワード: {json.dumps(context["related_terms"], ensure_ascii=False)}
                
                テキスト:
                {chunk}
                
                出力フォーマット:
                {{
                    "主要ポイント": [
                        {{"タイトル": "トピック", "重要度": 1-5の数値}}
                    ],
                    "詳細分析": [
                        {{"セクション": "セクション名", "キーポイント": ["ポイント1", "ポイント2"]}}
                    ],
                    "文脈連携": {{
                        "継続するトピック": ["トピック1", "トピック2"],
                        "新規トピック": ["新トピック1", "新トピック2"]
                    }},
                    "キーワード": [
                        {{"用語": "キーワード", "説明": "説明文"}}
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
                    
                    # Format summary for display
                    formatted_summary = self._format_summary(summary_data, i == 0)
                    summaries.append(formatted_summary)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse JSON from chunk {i}, using raw text")
                    summaries.append(response.text)
            
            return "\n\n".join(summaries)
            
        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            raise Exception(f"Failed to generate summary: {str(e)}")

    def _format_summary(self, summary_data: Dict, is_first_chunk: bool = False) -> str:
        """Format summary data into readable markdown"""
        lines = []
        
        # Add main points
        if is_first_chunk:
            lines.append("# 📝 コンテンツ要約")
            
        if "主要ポイント" in summary_data:
            lines.append("\n## 🎯 主要ポイント")
            for point in summary_data["主要ポイント"]:
                stars = "⭐" * point.get("重要度", 1)
                lines.append(f"- **{point['タイトル']}** {stars}")
        
        # Add detailed analysis
        if "詳細分析" in summary_data:
            lines.append("\n## 📊 詳細分析")
            for analysis in summary_data["詳細分析"]:
                lines.append(f"\n### {analysis['セクション']}")
                for point in analysis['キーポイント']:
                    lines.append(f"- {point}")
        
        # Add keywords
        if "キーワード" in summary_data:
            lines.append("\n## 🔍 重要キーワード")
            for keyword in summary_data["キーワード"]:
                lines.append(f"- **{keyword['用語']}**: {keyword['説明']}")
        
        return "\n".join(lines)
