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
            
            # Root node with thumbnail if available
            root_title = data.get("タイトル", "コンテンツマップ")
            lines.append(f"  root(({root_title}))")
            
            # Main branches (color-coded)
            colors = ['#E6E6FA', '#FFE4E1', '#E0FFFF', '#F0FFF0']  # Pastel colors
            
            # Group main points by themes
            themes = self._group_by_themes(data.get("主要ポイント", []))
            
            for i, (theme, points) in enumerate(themes.items()):
                # Main theme branch
                theme_id = f"theme_{i}"
                lines.append(f"    {theme_id}[{theme}]::style{i}")
                
                # Sub-points under theme
                for j, point in enumerate(points):
                    point_id = f"{theme_id}_{j}"
                    title = point.get("タイトル", "").replace("'", "")
                    lines.append(f"      {point_id}({title})")
                    
                    # Add brief explanations if available
                    if "説明" in point:
                        explanation = point["説明"].replace("'", "")[:30]  # Limit length
                        lines.append(f"        {point_id}_exp[\"{explanation}\"]")
            
            # Add style definitions
            lines.append("")
            for i, color in enumerate(colors):
                lines.append(f"  classDef style{i} fill:{color},stroke:#333,stroke-width:1px")
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.error(f"マインドマップの生成中にエラーが発生しました: {str(e)}")
            return "mindmap\n  root((エラーが発生しました))"

    def _group_by_themes(self, points: List[Dict]) -> Dict:
        themes = {}
        for point in points:
            theme = self._identify_theme(point)
            if theme not in themes:
                themes[theme] = []
            themes[theme].append(point)
        return themes

    def _identify_theme(self, point: Dict) -> str:
        # Identify theme based on content and keywords
        # This is a simple implementation - enhance based on your needs
        title = point.get("タイトル", "").lower()
        if "機能" in title or "特徴" in title:
            return "主な機能"
        elif "目的" in title or "概要" in title:
            return "概要と目的"
        elif "効果" in title or "利点" in title:
            return "メリット"
        else:
            return "その他"

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
