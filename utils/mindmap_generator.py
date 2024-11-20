import logging
from typing import Dict, List
import json

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MindMapGenerator:
    def __init__(self):
        self._cache = {}

    def _create_mermaid_mindmap(self, data: Dict) -> str:
        """Convert the analyzed data into Mermaid mindmap syntax"""
        try:
            lines = ["mindmap"]
            
            # Root node
            lines.append("  root((コンテンツマップ))")
            
            # Add main points with importance indicators
            for i, point in enumerate(data.get("主要ポイント", []), 1):
                importance = "🔥" * point.get("重要度", 1)
                title = point.get("タイトル", "").replace("'", "")
                lines.append(f"    {i}[{title} {importance}]")
                
                # Add details if available
                if "説明" in point:
                    explanation = point["説明"].replace("'", "")
                    lines.append(f"      {i}.1({explanation})")

            # Add context connections
            if "文脈連携" in data:
                context = data["文脈連携"]
                lines.append("    c[文脈のつながり]")
                
                # Add continuing topics
                if "継続するトピック" in context:
                    for i, topic in enumerate(context["継続するトピック"], 1):
                        topic = topic.replace("'", "")
                        lines.append(f"      c.{i}[{topic}]")
                
                # Add new topics
                if "新規トピック" in context:
                    for i, topic in enumerate(context["新規トピック"], 1):
                        topic = topic.replace("'", "")
                        lines.append(f"      c.n{i}({topic})")

            # Add keywords
            if "キーワード" in data:
                lines.append("    k[重要キーワード]")
                for i, keyword in enumerate(data["キーワード"], 1):
                    term = keyword.get("用語", "").replace("'", "")
                    desc = keyword.get("説明", "").replace("'", "")
                    lines.append(f"      k.{i}[{term}]")
                    lines.append(f"        k.{i}.1({desc})")

            return "\n".join(lines)
            
        except Exception as e:
            logger.error(f"マインドマップの生成中にエラーが発生しました: {str(e)}")
            return "mindmap\n  root((エラーが発生しました))"

    def generate_mindmap(self, text: str) -> str:
        """Generate a mindmap from the analyzed text"""
        try:
            # Check cache first
            cache_key = hash(text)
            if cache_key in self._cache:
                return self._cache[cache_key]

            # If text is already in JSON format (from TextProcessor), parse it
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                # If not JSON, create a simple structure
                data = {
                    "主要ポイント": [{
                        "タイトル": "テキスト概要",
                        "説明": text[:100] + "...",
                        "重要度": 3
                    }],
                    "キーワード": []
                }

            # Generate mindmap
            mermaid_syntax = self._create_mermaid_mindmap(data)
            
            # Cache the result
            self._cache[cache_key] = mermaid_syntax
            return mermaid_syntax
            
        except Exception as e:
            logger.error(f"マインドマップの生成に失敗しました: {str(e)}")
            return "mindmap\n  root((エラーが発生しました))"
