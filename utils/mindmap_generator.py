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
        """Generate Mermaid mindmap syntax with proper escaping and validation"""
        try:
            logger.debug(f"Starting mindmap creation with data structure: {list(data.keys())}")
            lines = ["mindmap"]
            
            # Root node from video overview
            overview = self._clean_text(data.get("動画の概要", "コンテンツ概要"))
            if len(overview) > 50:
                overview = overview[:47] + "..."
            lines.append(f"  root[{overview}]")
            logger.debug(f"Added root node: {overview}")
            
            # Process points as primary branches
            points = data.get("ポイント", [])
            if not points:
                logger.warning("No points found in data")
                return self._create_fallback_mindmap()
                
            logger.debug(f"Processing {len(points)} points")
            for i, point in enumerate(points, 1):
                if not isinstance(point, dict):
                    logger.error(f"Invalid point structure at index {i}")
                    continue
                    
                title = self._clean_text(point.get("タイトル", ""))
                if not title:
                    logger.warning(f"Empty title for point {i}")
                    continue
                
                # Add importance indicator
                importance = point.get("重要度", 3)
                importance_mark = "🔥" if importance >= 4 else "⭐" if importance >= 2 else "・"
                lines.append(f"    {i}[{importance_mark} {title}]")
                
                # Add content as sub-branch
                content = self._clean_text(point.get("内容", ""))
                if content:
                    # Split long content into multiple lines
                    content_parts = [content[j:j+40] for j in range(0, len(content), 40)]
                    for j, part in enumerate(content_parts, 1):
                        if part.strip():
                            lines.append(f"      {i}.{j}[{part}]")
                
                # Add supplementary info if available
                if "補足情報" in point and point["補足情報"]:
                    suppl_info = self._clean_text(point["補足情報"])
                    if suppl_info:
                        lines.append(f"      {i}.s[💡 {suppl_info[:40]}...]")
            
            # Add conclusion as a separate branch
            conclusion = self._clean_text(data.get("結論", ""))
            if conclusion:
                lines.append("    c[💡 結論]")
                if len(conclusion) > 40:
                    conclusion_parts = [conclusion[i:i+40] for i in range(0, len(conclusion), 40)]
                    for i, part in enumerate(conclusion_parts, 1):
                        if part.strip():
                            lines.append(f"      c.{i}[{part}]")
                else:
                    lines.append(f"      c.1[{conclusion}]")
            
            mindmap = "\n".join(lines)
            logger.debug(f"Generated mindmap structure:\n{mindmap}")
            return mindmap
            
        except Exception as e:
            logger.error(f"Error in mindmap creation: {str(e)}", exc_info=True)
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
        """Validate the JSON structure with enhanced validation and logging"""
        try:
            # Log input data structure
            logger.debug(f"Validating data structure: {type(data)}")
            logger.debug(f"Available keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
            
            # Basic type validation
            if not isinstance(data, dict):
                logger.error(f"Invalid data type: expected dict, got {type(data)}")
                return False
            
            # Required keys validation with content length check
            required_keys = ["動画の概要", "ポイント", "結論"]
            for key in required_keys:
                if key not in data:
                    logger.error(f"Missing required key: {key}")
                    return False
                value = data[key]
                if key == "動画の概要":
                    if not isinstance(value, str) or len(value.strip()) < 10:
                        logger.error(f"Invalid overview: must be string with min length 10, got {type(value)}")
                        return False
                elif key == "結論":
                    if not isinstance(value, str) or len(value.strip()) < 10:
                        logger.error(f"Invalid conclusion: must be string with min length 10, got {type(value)}")
                        return False
            
            # Validate points array
            points = data.get("ポイント", [])
            if not isinstance(points, list) or not points:
                logger.error(f"Points must be non-empty list, got {type(points)}")
                return False
            
            # Validate each point structure
            for i, point in enumerate(points):
                if not self._validate_point_structure(point, i):
                    return False
            
            # Additional validation for nested structures
            if "キーワード" in data:
                keywords = data["キーワード"]
                if not isinstance(keywords, list):
                    logger.error("Keywords must be a list")
                    return False
                for i, keyword in enumerate(keywords):
                    if not isinstance(keyword, dict) or "用語" not in keyword or "説明" not in keyword:
                        logger.error(f"Invalid keyword structure at index {i}")
                        return False
            
            logger.info("JSON structure validation successful")
            logger.debug("All validations passed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Validation error: {str(e)}", exc_info=True)
            return False
            
    def _validate_point_structure(self, point: Dict, index: int) -> bool:
        """Validate individual point structure"""
        if not isinstance(point, dict):
            logger.error(f"Point {index} is not a dictionary")
            return False
            
        # Required fields validation
        required_fields = {
            "タイトル": (str, 1, 100),  # (type, min_length, max_length)
            "内容": (str, 10, 1000),
            "重要度": (int, 1, 5)
        }
        
        for field, (expected_type, min_val, max_val) in required_fields.items():
            value = point.get(field)
            if field not in point:
                logger.error(f"Point {index} missing required field: {field}")
                return False
                
            if not isinstance(value, expected_type):
                logger.error(f"Point {index} field {field} has wrong type: expected {expected_type}, got {type(value)}")
                return False
                
            if expected_type == str and (len(value.strip()) < min_val or len(value.strip()) > max_val):
                logger.error(f"Point {index} field {field} length out of range: {len(value)} not in [{min_val}, {max_val}]")
                return False
                
            if expected_type == int and (value < min_val or value > max_val):
                logger.error(f"Point {index} field {field} value out of range: {value} not in [{min_val}, {max_val}]")
                return False
        
        return True
            
    def generate_mindmap(self, text: str) -> Tuple[str, bool]:
        """Generate a mindmap from the analyzed text with enhanced validation"""
        try:
            if not text or not isinstance(text, str):
                logger.error(f"Invalid input text type: {type(text)}")
                return self._create_fallback_mindmap(), False

            logger.info(f"Generating mindmap for text of length: {len(text)}")
            
            # Check cache with reliable key generation
            cache_key = hash(f"{text}_{self.__class__.__name__}")
            if cache_key in self._cache:
                logger.info("キャッシュからマインドマップを取得しました")
                cached_content = self._cache[cache_key]
                logger.debug(f"Cached mindmap length: {len(cached_content)}")
                return cached_content, True

            # Parse and validate JSON
            try:
                logger.debug("Attempting to parse JSON data")
                data = json.loads(text)
                logger.info("JSON parsing successful")
                
                if not self._validate_json_structure(data):
                    logger.warning("Invalid JSON structure detected, using fallback structure")
                    logger.debug(f"Received data structure: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
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
                    logger.info("Using fallback data structure")
            except json.JSONDecodeError as e:
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
