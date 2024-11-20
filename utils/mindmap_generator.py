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
        try:
            lines = ["mindmap"]
            
            # Escape special characters and clean the title
            root_title = data.get("タイトル", "コンテンツ概要")
            root_title = root_title.replace('"', "'").replace("\n", " ")
            lines.append(f"  root(({root_title}))")
            
            # Process main points as primary branches
            if "主要ポイント" in data:
                for i, point in enumerate(data["主要ポイント"]):
                    # Clean and escape the title
                    title = point.get("タイトル", "").replace('"', "'").replace("\n", " ")
                    lines.append(f"    {i}({title})")
                    
                    # Add sub-points with proper escaping
                    if "説明" in point:
                        explanation = point["説明"].replace('"', "'").replace("\n", " ")
                        # Truncate long explanations
                        if len(explanation) > 50:
                            explanation = explanation[:47] + "..."
                        lines.append(f"      {i}.1({explanation})")
            
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
                    "タイトル": "コンテンツ概要",
                    "主要ポイント": [{
                        "タイトル": "テキスト概要",
                        "説明": text[:100] + "...",
                    }]
                }

            # Generate mindmap
            mermaid_syntax = self._create_mermaid_mindmap(data)
            
            # Cache the result
            self._cache[cache_key] = mermaid_syntax
            return mermaid_syntax
            
        except Exception as e:
            logger.error(f"マインドマップの生成に失敗しました: {str(e)}")
            return "mindmap\n  root((エラーが発生しました))"
