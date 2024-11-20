import os
import google.generativeai as genai
import logging
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled
import json
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
        self.model = genai.GenerativeModel('gemini-1.0-pro')
        self._cache = {}

    def _create_summary_prompt(self, text):
        prompt = f"""
あなたは文脈を考慮した要約生成の専門家です。以下のテキストを分析し、文脈の流れと重要度を考慮した要約を生成してください。

出力要件:
1. 各トピックの関連性と重要度を考慮
2. 文脈の流れを保持した自然な要約
3. 重要なキーポイントの抽出と説明

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
    "キーワード": [
        {{
            "用語": "キーワード",
            "説明": "20文字以内の説明"
        }}
    ],
    "文脈連携": {{
        "継続するトピック": ["トピック名"],
        "新規トピック": ["新トピック名"]
    }}
}}

考慮すべきポイント:
1. トピック間の関連性を明確に示す
2. 重要度の判定基準を文脈から導出
3. キーワードの文脈上の役割を考慮
4. トピックの継続性と新規性を区別

分析対象テキスト:
{text}
"""
        return prompt

    def get_transcript(self, video_url):
        """Get transcript from YouTube video"""
        try:
            video_id = self._extract_video_id(video_url)
            
            # Check cache first
            cache_key = f"transcript_{video_id}"
            if cache_key in self._cache:
                return self._cache[cache_key]
            
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            transcript = transcript_list.find_transcript(['ja', 'en'])
            transcript_pieces = transcript.fetch()
            
            # Improved transcript processing with context preservation
            processed_pieces = []
            current_context = ""
            
            for piece in transcript_pieces:
                text = piece['text'].strip()
                # Preserve context between transcript pieces
                if text.endswith(('、', '。', '！', '？')):
                    current_context += text + ' '
                    processed_pieces.append(current_context.strip())
                    current_context = ""
                else:
                    current_context += text + ' '
            
            if current_context:  # Add any remaining context
                processed_pieces.append(current_context.strip())
            
            full_transcript = ' '.join(processed_pieces)
            
            # Cache the result
            self._cache[cache_key] = full_transcript
            return full_transcript
            
        except (NoTranscriptFound, TranscriptsDisabled) as e:
            logger.error(f"字幕の取得に失敗しました: {str(e)}")
            raise Exception("この動画では字幕を利用できません")
        except Exception as e:
            logger.error(f"字幕の取得中にエラーが発生しました: {str(e)}")
            raise Exception(f"字幕の取得に失敗しました: {str(e)}")

    def _extract_video_id(self, url):
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
        raise ValueError("無効なYouTube URLです")

    def generate_summary(self, text):
        """Generate context-aware summary using Gemini"""
        try:
            # Check cache first
            cache_key = hash(text)
            if cache_key in self._cache:
                return self._cache[cache_key]

            # Split text into contextual chunks for better processing
            chunks = self._split_into_contextual_chunks(text)
            
            # Process each chunk while maintaining context
            summaries = []
            context = {}
            
            for chunk in chunks:
                prompt = self._create_summary_prompt(chunk)
                response = self.model.generate_content(prompt)
                
                if not response.text:
                    raise Exception("要約の生成に失敗しました")

                # Extract JSON from response
                json_str = response.text
                if json_str.startswith('```json'):
                    json_str = json_str[7:]
                if json_str.endswith('```'):
                    json_str = json_str[:-3]

                # Parse JSON and update context
                chunk_data = json.loads(json_str)
                self._update_context(context, chunk_data)
                summaries.append(chunk_data)
            
            # Merge summaries with context awareness
            merged_summary = self._merge_summaries(summaries, context)
            formatted_summary = self._format_summary(merged_summary)
            
            # Cache the result
            self._cache[cache_key] = formatted_summary
            return formatted_summary
            
        except Exception as e:
            logger.error(f"要約の生成中にエラーが発生しました: {str(e)}")
            raise Exception(f"要約の生成に失敗しました: {str(e)}")

    def _split_into_contextual_chunks(self, text, chunk_size=1000):
        """Split text into chunks while preserving context"""
        chunks = []
        sentences = re.split('([。！？])', text)
        current_chunk = ""
        
        for i in range(0, len(sentences), 2):
            sentence = sentences[i] + (sentences[i + 1] if i + 1 < len(sentences) else "")
            if len(current_chunk) + len(sentence) > chunk_size:
                chunks.append(current_chunk)
                current_chunk = sentence
            else:
                current_chunk += sentence
                
        if current_chunk:
            chunks.append(current_chunk)
            
        return chunks

    def _update_context(self, context, chunk_data):
        """Update context information from chunk data"""
        # Update continuing topics
        if "文脈連携" in chunk_data:
            if "継続するトピック" not in context:
                context["継続するトピック"] = set()
            if "新規トピック" not in context:
                context["新規トピック"] = set()
                
            context["継続するトピック"].update(chunk_data["文脈連携"]["継続するトピック"])
            context["新規トピック"].update(chunk_data["文脈連携"]["新規トピック"])

    def _merge_summaries(self, summaries, context):
        """Merge chunk summaries with context awareness"""
        merged = {
            "主要ポイント": [],
            "詳細分析": [],
            "キーワード": [],
            "文脈連携": {
                "継続するトピック": list(context.get("継続するトピック", [])),
                "新規トピック": list(context.get("新規トピック", []))
            }
        }
        
        # Merge while maintaining importance and context
        seen_topics = set()
        for summary in summaries:
            # Merge main points with deduplication
            for point in summary.get("主要ポイント", []):
                if point["タイトル"] not in seen_topics:
                    merged["主要ポイント"].append(point)
                    seen_topics.add(point["タイトル"])
            
            # Merge detailed analysis
            merged["詳細分析"].extend(summary.get("詳細分析", []))
            
            # Merge keywords with deduplication
            for keyword in summary.get("キーワード", []):
                if not any(k["用語"] == keyword["用語"] for k in merged["キーワード"]):
                    merged["キーワード"].append(keyword)

        return merged

    def _format_summary(self, data):
        """Format the summary data into a readable markdown string"""
        try:
            sections = []
            
            # Main points section
            if "主要ポイント" in data:
                sections.append("## 📌 主要ポイント\n")
                for point in data["主要ポイント"]:
                    importance = "🔥" * point.get("重要度", 1)
                    sections.append(f"### {point['タイトル']} {importance}\n")
                    sections.append(f"{point['説明']}\n")

            # Detailed analysis section
            if "詳細分析" in data:
                sections.append("\n## 📊 詳細分析\n")
                for analysis in data["詳細分析"]:
                    sections.append(f"### {analysis['セクション']}\n")
                    for point in analysis['キーポイント']:
                        sections.append(f"- {point}\n")

            # Keywords section
            if "キーワード" in data:
                sections.append("\n## 🔍 重要キーワード\n")
                for keyword in data["キーワード"]:
                    sections.append(f"**{keyword['用語']}**: {keyword['説明']}\n")

            # Context connection section
            if "文脈連携" in data:
                sections.append("\n## 🔄 文脈の連携\n")
                
                if data["文脈連携"]["継続するトピック"]:
                    sections.append("### 継続するトピック\n")
                    for topic in data["文脈連携"]["継続するトピック"]:
                        sections.append(f"- {topic}\n")
                
                if data["文脈連携"]["新規トピック"]:
                    sections.append("\n### 新規トピック\n")
                    for topic in data["文脈連携"]["新規トピック"]:
                        sections.append(f"- {topic}\n")

            return "\n".join(sections)
            
        except Exception as e:
            logger.error(f"要約のフォーマット中にエラーが発生しました: {str(e)}")
            return "要約のフォーマットに失敗しました"
