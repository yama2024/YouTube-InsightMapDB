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
        """Generate Mermaid mindmap syntax with proper formatting for version 10.2.4"""
        try:
            logger.debug(f"Starting mindmap creation with data structure: {list(data.keys())}")
            lines = ["mindmap"]
            
            # Root node with proper Mermaid 10.2.4 syntax
            overview = self._clean_text(data.get("動画の概要", "コンテンツ概要"))
            MAX_OVERVIEW_LENGTH = 50  # Reduced for better display
            if len(overview) > MAX_OVERVIEW_LENGTH:
                overview = overview[:MAX_OVERVIEW_LENGTH-3] + "..."
            lines.append(f"  root((概要：{overview}))")
            logger.debug(f"Added root node: {overview}")
            
            # Process points with enhanced validation
            points = data.get("ポイント", [])
            if not points or not isinstance(points, list):
                logger.warning("Invalid or empty points structure")
                return self._create_fallback_mindmap()
            
            logger.debug(f"Processing {len(points)} points")
            
            # Group points by importance for better organization
            points_by_importance = {i: [] for i in range(1, 6)}
            for point in points:
                if isinstance(point, dict):
                    importance = min(max(int(point.get("重要度", 3)), 1), 5)
                    points_by_importance[importance].append(point)
            
            # Process points by importance (high to low)
            point_counter = 1
            for importance in reversed(range(1, 6)):
                for point in points_by_importance[importance]:
                    title = self._clean_text(point.get("タイトル", ""))
                    if not title or len(title.strip()) < 2:
                        logger.warning(f"Skipping point {point_counter} due to invalid title")
                        continue
                    
                    # Enhanced importance indicators
                    importance_marks = {
                        5: "🔥 重要",
                        4: "⭐ 注目",
                        3: "📌",
                        2: "・",
                        1: "∙"
                    }
                    importance_mark = importance_marks[importance]
                    
                    # Add formatted title node with consistent indentation
                    title_node = f"  {point_counter}[{importance_mark} {title}]"
                    lines.append(title_node)
                    
                    # Process content with improved chunking
                    content = self._clean_text(point.get("内容", ""))
                    if content:
                        # Optimized content chunking
                        chunk_size = 40  # Consistent chunk size
                        content_parts = []
                        current_part = ""
                        
                        # Split by Japanese sentence endings for more natural breaks
                        sentences = [s.strip() for s in re.split('[。．！？]', content) if s.strip()]
                        for sentence in sentences:
                            if len(sentence) <= chunk_size:
                                content_parts.append(sentence)
                            else:
                                # Split long sentences
                                words = sentence.split()
                                for word in words:
                                    if len(current_part) + len(word) + 1 <= chunk_size:
                                        current_part += f" {word}" if current_part else word
                                    else:
                                        if current_part:
                                            content_parts.append(current_part.strip())
                                        current_part = word
                                if current_part:
                                    content_parts.append(current_part.strip())
                                    current_part = ""
                        
                        # Add content nodes with proper indentation
                        for j, part in enumerate(content_parts, 1):
                            if part.strip():
                                content_node = f"    {point_counter}.{j}[{part}]"
                                lines.append(content_node)
                    
                    # Enhanced supplementary info handling
                    if "補足情報" in point and point["補足情報"]:
                        suppl_info = self._clean_text(point["補足情報"])
                        if suppl_info:
                            lines.append(f"      {point_counter}.s[💡 {suppl_info[:45]}...]")
                    
                    point_counter += 1
            
            # Conclusion formatting with proper Mermaid syntax
            conclusion = self._clean_text(data.get("結論", ""))
            if conclusion:
                lines.append("  c[結論]")
                # Split conclusion into meaningful chunks
                sentences = [s.strip() for s in re.split('[。．！？]', conclusion) if s.strip()]
                for i, sentence in enumerate(sentences, 1):
                    if len(sentence) > 40:
                        # Split long sentences into smaller chunks
                        chunks = []
                        current_chunk = ""
                        words = sentence.split()
                        for word in words:
                            if len(current_chunk) + len(word) + 1 <= 40:
                                current_chunk += f" {word}" if current_chunk else word
                            else:
                                if current_chunk:
                                    chunks.append(current_chunk.strip())
                                current_chunk = word
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                        
                        # Add chunked sentences
                        for j, chunk in enumerate(chunks, 1):
                            lines.append(f"    c.{i}.{j}[{chunk}]")
                    else:
                        # Add short sentences directly
                        lines.append(f"    c.{i}[{sentence}]")
            
            mindmap = "\n".join(lines)
            logger.debug(f"Generated mindmap structure:\n{mindmap}")
            return mindmap
            
        except Exception as e:
            logger.error(f"Error in mindmap creation: {str(e)}", exc_info=True)
            return self._create_fallback_mindmap()

    def _clean_text(self, text: str) -> str:
        """Clean and normalize text for Mermaid 10.2.4 syntax with strict character handling"""
        try:
            # Input validation
            if not isinstance(text, str):
                text = str(text)
            if not text.strip():
                return "内容なし"
                
            # Length validation
            MAX_LENGTH = 150  # Reduced for better display
            if len(text) > MAX_LENGTH:
                text = text[:MAX_LENGTH-3] + "..."
            
            # Basic normalization
            text = text.strip()
            text = " ".join(text.split())  # Normalize whitespace
            
            # Mermaid syntax characters that need escaping
            replacements = {
                '"': "'",    # Replace quotes
                '\n': " ",   # Replace newlines
                '[': "［",   # Safe brackets
                ']': "］",
                '(': "（",   # Safe parentheses
                ')': "）",
                '<': "＜",   # Safe angle brackets
                '>': "＞",
                '|': "｜",   # Safe vertical bar
                '*': "＊",   # Safe asterisk
                '#': "＃",   # Safe hash
                '^': "＾",   # Safe caret
                '~': "～",   # Safe tilde
                '`': "｀",   # Safe backtick
                ':': "：",   # Safe colon
                ';': "；",   # Safe semicolon
                '&': "＆",   # Safe ampersand
                '%': "％",   # Safe percent
                '$': "＄",   # Safe dollar
                '@': "＠",   # Safe at
                '!': "！",   # Safe exclamation
                '?': "？",   # Safe question mark
                '+': "＋",   # Safe plus
                '=': "＝",   # Safe equals
                '{': "｛",   # Safe braces
                '}': "｝",
            }
            
            # Apply replacements while preserving important formatting
            for old, new in replacements.items():
                text = text.replace(old, new)
            
            # Preserve important formatting markers
            preserved_markers = ['!', '？', '！', '。', '、']
            for marker in preserved_markers:
                text = text.replace(f"{marker} ", marker)
            
            # Final cleanup
            text = text.strip()
            
            # Validate final length
            if not text:
                return "内容なし"
            
            return text
            
        except Exception as e:
            logger.error(f"Text cleaning error: {str(e)}")
            return "テキスト処理エラー"

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
        """Validate the JSON structure with strict validation, quality checks, and detailed error messages"""
        try:
            # Enhanced logging
            logger.debug(f"Starting JSON validation for data type: {type(data)}")
            logger.debug(f"Available keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
            
            # Strict type validation
            if not isinstance(data, dict):
                logger.error(f"データ形式が無効です。辞書型が必要ですが、{type(data)}が与えられました。")
                return False
            
            # Required keys validation with enhanced content checks
            validation_rules = {
                "動画の概要": {
                    "type": str,
                    "min_length": 20,
                    "max_length": 500,
                    "required_chars": ["。", "、"],
                    "error_prefix": "動画概要"
                },
                "ポイント": {
                    "type": list,
                    "min_items": 1,
                    "max_items": 10,
                    "error_prefix": "ポイント配列"
                },
                "結論": {
                    "type": str,
                    "min_length": 15,
                    "max_length": 300,
                    "required_chars": ["。"],
                    "error_prefix": "結論"
                }
            }
            
            # Validate each required key
            for key, rules in validation_rules.items():
                # Check existence
                if key not in data:
                    logger.error(f"{rules['error_prefix']}が見つかりません")
                    return False
                
                value = data[key]
                
                # Type validation
                if not isinstance(value, rules["type"]):
                    logger.error(
                        f"{rules['error_prefix']}の型が無効です: "
                        f"{rules['type'].__name__}が必要ですが、{type(value).__name__}が与えられました"
                    )
                    return False
                
                # Content validation for strings
                if rules["type"] == str:
                    cleaned_value = value.strip()
                    if len(cleaned_value) < rules["min_length"]:
                        logger.error(
                            f"{rules['error_prefix']}が短すぎます: "
                            f"最小{rules['min_length']}文字必要ですが、{len(cleaned_value)}文字です"
                        )
                        return False
                    if len(cleaned_value) > rules["max_length"]:
                        logger.error(
                            f"{rules['error_prefix']}が長すぎます: "
                            f"最大{rules['max_length']}文字までですが、{len(cleaned_value)}文字です"
                        )
                        return False
                    
                    # Check for required characters
                    if "required_chars" in rules:
                        missing_chars = [c for c in rules["required_chars"] if c not in cleaned_value]
                        if missing_chars:
                            logger.error(
                                f"{rules['error_prefix']}に必要な文字が含まれていません: "
                                f"{', '.join(missing_chars)}"
                            )
                            return False
                
                # Content validation for lists
                if rules["type"] == list:
                    if len(value) < rules["min_items"]:
                        logger.error(
                            f"{rules['error_prefix']}の項目数が少なすぎます: "
                            f"最小{rules['min_items']}項目必要ですが、{len(value)}項目です"
                        )
                        return False
                    if len(value) > rules["max_items"]:
                        logger.error(
                            f"{rules['error_prefix']}の項目数が多すぎます: "
                            f"最大{rules['max_items']}項目までですが、{len(value)}項目です"
                        )
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
        """Validate individual point structure with improved null handling"""
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
            
            # Handle missing or None values
            if value is None:
                logger.error(f"Point {index} field {field} is missing or None")
                return False
                
            # Type validation
            if not isinstance(value, expected_type):
                try:
                    # Try type conversion for numbers
                    if expected_type == int:
                        value = int(value)
                        point[field] = value
                    else:
                        logger.error(f"Point {index} field {field} has wrong type: expected {expected_type}, got {type(value)}")
                        return False
                except (ValueError, TypeError):
                    logger.error(f"Point {index} field {field} cannot be converted to {expected_type}")
                    return False
                
            # Length/range validation
            if expected_type == str:
                cleaned_value = value.strip()
                if not cleaned_value or len(cleaned_value) < min_val or len(cleaned_value) > max_val:
                    logger.error(f"Point {index} field {field} length out of range: {len(cleaned_value)} not in [{min_val}, {max_val}]")
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
            
            # Parse JSON text and validate structure
            try:
                data = json.loads(text)
                logger.debug(f"Parsed JSON data structure: {list(data.keys())}")
                
                # Validate JSON structure
                if not self._validate_json_structure(data):
                    logger.error("Invalid JSON structure")
                    return self._create_fallback_mindmap(), False
                    
                # Generate mindmap
                mindmap = self._create_mermaid_mindmap(data)
                return mindmap, True
                    
            except json.JSONDecodeError as e:
                logger.error(f"JSON parsing error: {str(e)}")
                return self._create_fallback_mindmap(), False
            except Exception as e:
                logger.error(f"Mindmap generation error: {str(e)}")
                return self._create_fallback_mindmap(), False
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
