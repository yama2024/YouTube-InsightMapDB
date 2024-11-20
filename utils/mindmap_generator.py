import logging
from typing import Dict, List, Tuple
import json

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MindMapGenerator:
    def __init__(self):
        self._cache = {}

    def _create_mermaid_mindmap(self, data: Dict) -> str:
        """Generate Mermaid mindmap syntax with proper escaping and fallback"""
        try:
            lines = ["mindmap"]
            
            # Escape special characters and clean the title
            root_title = data.get("タイトル", "コンテンツ概要")
            root_title = self._clean_text(root_title)
            lines.append(f"  root(({root_title}))")
            
            # Process main points as primary branches
            if "主要ポイント" in data:
                for i, point in enumerate(data["主要ポイント"]):
                    # Clean and escape the title
                    title = self._clean_text(point.get("タイトル", ""))
                    lines.append(f"    {i}({title})")
                    
                    # Add sub-points with proper escaping
                    if "説明" in point:
                        explanation = self._clean_text(point["説明"])
                        # Truncate long explanations
                        if len(explanation) > 50:
                            explanation = explanation[:47] + "..."
                        lines.append(f"      {i}.1({explanation})")
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.error(f"マインドマップの生成中にエラーが発生しました: {str(e)}")
            return self._create_fallback_mindmap()

    def _clean_text(self, text: str) -> str:
        """Clean and escape text for Mermaid syntax"""
        return (text.replace('"', "'")
                   .replace("\n", " ")
                   .replace("(", "[")
                   .replace(")", "]")
                   .strip())

    def _create_fallback_mindmap(self) -> str:
        """Create a simple fallback mindmap when generation fails"""
        return """mindmap
  root((コンテンツ概要))
    1((エラーが発生しました))
      1.1((マインドマップの生成に失敗しました))"""

    def generate_mindmap(self, text: str) -> Tuple[str, bool]:
        """Generate a mindmap from the analyzed text with fallback handling"""
        try:
            # Check cache first
            cache_key = hash(text)
            if cache_key in self._cache:
                return self._cache[cache_key], True

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
            return mermaid_syntax, True
            
        except Exception as e:
            logger.error(f"マインドマップの生成に失敗しました: {str(e)}")
            return self._create_fallback_mindmap(), False
