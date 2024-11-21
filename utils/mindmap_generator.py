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
            lines.append(f"  root[{root_title}]")
            
            # Process main points as primary branches
            if "主要ポイント" in data:
                for i, point in enumerate(data["主要ポイント"], 1):
                    # Clean and escape the title
                    title = self._clean_text(point.get("タイトル", ""))
                    if not title:
                        continue
                    
                    # Add importance indicator
                    importance = point.get("重要度", 3)
                    importance_mark = "🔥" if importance >= 4 else "⭐" if importance >= 2 else "・"
                    lines.append(f"    {i}[{importance_mark} {title}]")
                    
                    # Add sub-points with proper escaping
                    if "説明" in point:
                        explanation = self._clean_text(point["説明"])
                        # Split long explanations into multiple lines
                        if len(explanation) > 50:
                            parts = [explanation[i:i+50] for i in range(0, len(explanation), 50)]
                            for j, part in enumerate(parts, 1):
                                lines.append(f"      {i}.{j}[{part}]")
                        else:
                            lines.append(f"      {i}.1[{explanation}]")
                    
                    # Add keywords if available
                    if "キーワード" in point:
                        for j, keyword in enumerate(point["キーワード"], 1):
                            keyword_text = self._clean_text(keyword)
                            lines.append(f"        {i}.k{j}[📌 {keyword_text}]")
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.error(f"マインドマップの生成中にエラーが発生しました: {str(e)}")
            return self._create_fallback_mindmap()

    def _clean_text(self, text: str) -> str:
        """Clean and escape text for Mermaid syntax"""
        if not isinstance(text, str):
            text = str(text)
        return (text.replace('"', "'")
                   .replace("\n", " ")
                   .replace("[", "「")
                   .replace("]", "」")
                   .replace("(", "（")
                   .replace(")", "）")
                   .replace("<", "＜")
                   .replace(">", "＞")
                   .strip())

    def _create_fallback_mindmap(self) -> str:
        """Create a more informative fallback mindmap when generation fails"""
        return """mindmap
  root[コンテンツ解析結果]
    1[⚠️ 処理状態]
      1.1[マインドマップの生成に問題が発生しました]
      1.2[以下をご確認ください]
        1.2.1[・入力データの形式]
        1.2.2[・テキストの長さ]
        1.2.3[・特殊文字の使用]
    2[🔄 次のステップ]
      2.1[・ページを更新]
      2.2[・入力を確認]
      2.3[・再度実行]"""

    def _validate_json_structure(self, data: Dict) -> bool:
        """Validate the JSON structure for mindmap generation"""
        try:
            # Check for required keys
            if not isinstance(data, dict):
                return False
                
            # Validate main structure
            if "動画の概要" not in data or "ポイント" not in data or "結論" not in data:
                return False
                
            # Validate points structure
            points = data.get("ポイント", [])
            if not isinstance(points, list) or not points:
                return False
                
            for point in points:
                if not isinstance(point, dict):
                    return False
                if "タイトル" not in point or "内容" not in point:
                    return False
                    
            return True
            
        except Exception as e:
            logger.error(f"JSON構造の検証中にエラーが発生しました: {str(e)}")
            return False
            
    def generate_mindmap(self, text: str) -> Tuple[str, bool]:
        """Generate a mindmap from the analyzed text with enhanced validation"""
        try:
            # Check cache with reliable key generation
            cache_key = hash(f"{text}_{self.__class__.__name__}")
            if cache_key in self._cache:
                logger.info("キャッシュからマインドマップを取得しました")
                return self._cache[cache_key], True

            # Parse and validate JSON
            try:
                data = json.loads(text)
                if not self._validate_json_structure(data):
                    logger.warning("Invalid JSON structure, using fallback structure")
                    data = {
                        "動画の概要": "コンテンツの要約",
                        "ポイント": [
                            {
                                "タイトル": "主要なポイント",
                                "内容": "動画の内容を確認できませんでした",
                                "重要度": 3
                            }
                        ],
                        "結論": "内容を確認できませんでした"
                    }
            except json.JSONDecodeError:
                logger.warning("Invalid JSON format, creating basic structure")
                data = {
                    "動画の概要": "コンテンツ概要",
                    "ポイント": [{
                        "タイトル": "概要",
                        "内容": text[:100] + "..." if len(text) > 100 else text,
                        "重要度": 3
                    }],
                    "結論": "テキストの解析に失敗しました"
                }

            # Generate mindmap with validated data
            mermaid_syntax = self._create_mermaid_mindmap(data)
            
            # Cache only valid results
            if mermaid_syntax and mermaid_syntax.count('\n') > 2:
                self._cache[cache_key] = mermaid_syntax
                logger.info("新しいマインドマップを生成してキャッシュしました")
                return mermaid_syntax, True
            
            logger.warning("生成されたマインドマップが無効です")
            return self._create_fallback_mindmap(), False
            
        except Exception as e:
            logger.error(f"マインドマップの生成中にエラーが発生しました: {str(e)}")
            return self._create_fallback_mindmap(), False
