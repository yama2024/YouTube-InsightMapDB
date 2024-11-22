import logging
import hashlib
from typing import Dict, List, Tuple, Optional
import json

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MindMapGenerator:
    def __init__(self):
        self._cache = {}

    def _create_mermaid_mindmap(self, data: Dict) -> str:
        """Generate Mermaid mindmap syntax with enhanced styling and hierarchy"""
        try:
            logger.debug(f"Starting mindmap creation with data structure: {list(data.keys())}")
            lines = ["mindmap"]
            
            # Enhanced style definitions
            lines.extend([
                "  %%{init: {",
                "    'theme': 'base',",
                "    'themeVariables': {",
                "      'primaryColor': '#57C7FF',",
                "      'primaryTextColor': '#000',",
                "      'primaryBorderColor': '#7C0000',",
                "      'lineColor': '#00B5AA',",
                "      'fontSize': '16px'",
                "    },",
                "    'mindmap': {",
                "      'padding': 16,",
                "      'nodeSpacing': 50",
                "    },",
                "    'flowchart': {",
                "      'curve': 'basis',",
                "      'htmlLabels': true,",
                "      'rankSpacing': 80,",
                "      'nodeSpacing': 50",
                "    }",
                "  }}%%",
                "",
                "  classDef root fill:#FF9999,stroke:#FF0000,stroke-width:2px,color:#000",
                "  classDef category fill:#99FF99,stroke:#00FF00,stroke-width:2px,color:#000",
                "  classDef critical fill:#FF7070,stroke:#FF0000,stroke-width:2px,color:#000,font-weight:bold",
                "  classDef important fill:#FFB570,stroke:#FF7F00,stroke-width:2px,color:#000",
                "  classDef normal fill:#70FF70,stroke:#00FF00,stroke-width:1px,color:#000",
                "  classDef auxiliary fill:#70B5FF,stroke:#0000FF,stroke-width:1px,color:#000",
                "  classDef note fill:#FFE070,stroke:#FFD700,stroke-width:1px,color:#000,font-style:italic",
                "  classDef content fill:#FFFFFF,stroke:#CCCCCC,stroke-width:1px,color:#000",
                "  classDef conclusion fill:#FF99CC,stroke:#FF69B4,stroke-width:2px,color:#000,font-weight:bold"
            ])
            
            # Root node with enhanced styling
            overview = self._clean_text(data.get("動画の概要", "コンテンツ概要"))
            if len(overview) > 50:
                overview = overview[:47] + "..."
            lines.append(f"  root((📺 {overview})):::root")
            logger.debug(f"Added root node: {overview}")
            
            # Process points as primary branches with enhanced styling
            points = data.get("ポイント", [])
            if not points:
                logger.warning("No points found in data")
                return self._create_fallback_mindmap()
                
            logger.debug(f"Processing {len(points)} points")
            categories = self._categorize_points(points)
            
            # Process points by category
            for category, cat_points in categories.items():
                # Add category node
                cat_id = self._get_category_id(category)
                lines.append(f"    {cat_id}[{self._get_category_icon(category)} {category}]:::category")
                
                # Process points in this category
                for i, point in enumerate(cat_points, 1):
                    if not isinstance(point, dict):
                        logger.error(f"Invalid point structure at index {i}")
                        continue
                        
                    title = self._clean_text(point.get("タイトル", ""))
                    if not title:
                        logger.warning(f"Empty title for point {i}")
                        continue
                    
                    # Style based on importance
                    importance = point.get("重要度", 3)
                    importance_style = self._get_importance_style(importance)
                    point_id = f"{cat_id}.{i}"
                    
                    # Add point with styled node
                    importance_mark = "🔥" if importance >= 4 else "⭐" if importance >= 2 else "・"
                    lines.append(f"      {point_id}({importance_mark} {title}):::{importance_style}")
                    
                    # Add content with enhanced styling
                    content = self._clean_text(point.get("内容", ""))
                    if content:
                        # Create content chunks with better formatting
                        content_parts = self._chunk_content(content)
                        for j, part in enumerate(content_parts, 1):
                            if part.strip():
                                lines.append(f"        {point_id}.{j}[{part}]:::content")
                    
                    # Add supplementary info with distinct styling
                    if "補足情報" in point and point["補足情報"]:
                        suppl_info = self._clean_text(point["補足情報"])
                        if suppl_info:
                            lines.append(f"        {point_id}.s>💡 {suppl_info[:40]}...]:::note")
            
            # Add conclusion with special styling
            conclusion = self._clean_text(data.get("結論", ""))
            if conclusion:
                lines.append("    c{💡 結論}:::conclusion")
                conclusion_parts = self._chunk_content(conclusion)
                for i, part in enumerate(conclusion_parts, 1):
                    if part.strip():
                        lines.append(f"      c.{i}[{part}]:::conclusion-content")
            
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

    def _create_fallback_mindmap(self, error_details: str = None) -> str:
        """より詳細な情報を含むフォールバックマインドマップの生成"""
        lines = [
            "mindmap",
            "  %%{init: {'theme': 'base'}}%%",
            "  classDef error fill:#FFE6E6,stroke:#FF0000,stroke-width:2px,color:#FF0000",
            "  classDef warning fill:#FFF3E6,stroke:#FFA500,stroke-width:2px,color:#FFA500",
            "  classDef info fill:#E6F3FF,stroke:#0066CC,stroke-width:1px,color:#0066CC",
            "",
            "  root((⚠️ マインドマップ生成エラー)):::error",
            "    error[問題が発生しました]:::error",
            f"      details[\"{error_details if error_details else 'マインドマップの生成に問題が発生しました'}\"]:::warning",
            "    check[確認事項]:::info",
            "      check.1[入力データの形式を確認]:::info",
            "      check.2[テキストの長さを確認]:::info",
            "      check.3[特殊文字の使用を確認]:::info",
            "    solution[対処方法]:::info",
            "      solution.1[ページを更新して再試行]:::info",
            "      solution.2[入力データを修正]:::info",
            "      solution.3[サポートに問い合わせ]:::info",
            "    tips[ヒント]:::info",
            "      tips.1[データ形式はJSONである必要があります]:::info",
            "      tips.2[テキストは適切な長さに収める]:::info",
            "      tips.3[特殊文字は適切にエスケープ]:::info"
        ]
        return "\n".join(lines)

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
                
            if expected_type == str and value is not None:
                stripped_value = value.strip()
                if len(stripped_value) < min_val or len(stripped_value) > max_val:
                    logger.error(f"Point {index} field {field} length out of range: {len(stripped_value)} not in [{min_val}, {max_val}]")
                    return False
                
            if expected_type == int and (value < min_val or value > max_val):
                logger.error(f"Point {index} field {field} value out of range: {value} not in [{min_val}, {max_val}]")
                return False
        
        return True
            
    def _categorize_points(self, points: List[Dict]) -> Dict:
        """ポイントをカテゴリー別に分類する"""
        categories = {}
        
        for point in points:
            # カテゴリーを決定（タイトルとキーワードから推測）
            title = point.get("タイトル", "").lower()
            content = point.get("内容", "").lower()
            importance = point.get("重要度", 3)
            
            # カテゴリー判定ロジック
            if any(key in title or key in content for key in ["概要", "まとめ", "導入"]):
                category = "概要・導入"
            elif any(key in title or key in content for key in ["手順", "方法", "やり方"]):
                category = "手順・方法"
            elif any(key in title or key in content for key in ["結果", "効果", "成果"]):
                category = "結果・効果"
            elif importance >= 4:
                category = "重要ポイント"
            else:
                category = "その他"
            
            # カテゴリーにポイントを追加
            if category not in categories:
                categories[category] = []
            categories[category].append(point)
            
        return categories

    def _get_category_id(self, category: str) -> str:
        """カテゴリー名から一意のIDを生成"""
        # 特殊文字を処理し、短いハッシュを生成
        safe_category = "".join(c for c in category if c.isalnum())
        hash_obj = hashlib.md5(safe_category.encode())
        return f"cat_{hash_obj.hexdigest()[:6]}"

    def _get_category_icon(self, category: str) -> str:
        """カテゴリーに応じた適切なアイコンを割り当て"""
        icons = {
            "概要・導入": "📝",
            "手順・方法": "📌",
            "結果・効果": "🎯",
            "重要ポイント": "⭐",
            "その他": "💡"
        }
        return icons.get(category, "•")

    def _get_importance_style(self, importance: int) -> str:
        """重要度に応じたスタイルクラスを割り当て"""
        if importance >= 5:
            return "critical"
        elif importance >= 4:
            return "important"
        elif importance >= 3:
            return "normal"
        return "auxiliary"
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
            logger.error(f"Error processing text: {str(e)}", exc_info=True)
            return self._create_fallback_mindmap(), False

    def _validate_data(self, text: str) -> Optional[Dict]:
        """Validate and parse the input text data"""
        try:
            # Parse JSON data
            data = json.loads(text)
            
            # Validate structure
            if not self._validate_json_structure(data):
                return None
                
            return data
        except json.JSONDecodeError:
            logger.error("Invalid JSON format")
            return None
        except Exception as e:
            logger.error(f"Data validation error: {str(e)}")
            return None

    def _categorize_points(self, points: List[Dict]) -> Dict:
        """Categorize points based on their content and importance"""
        categories = {
            "重要ポイント": [],
            "主要な情報": [],
            "補足説明": []
        }
        
        for point in points:
            importance = point.get("重要度", 3)
            if importance >= 4:
                categories["重要ポイント"].append(point)
            elif importance >= 2:
                categories["主要な情報"].append(point)
            else:
                categories["補足説明"].append(point)
                
        return {k: v for k, v in categories.items() if v}  # Only return non-empty categories

    def _get_category_id(self, category: str) -> str:
        """Generate a unique ID for each category"""
        category_ids = {
            "重要ポイント": "key",
            "主要な情報": "main",
            "補足説明": "sub"
        }
        return category_ids.get(category, "misc")

    def _get_category_icon(self, category: str) -> str:
        """Get appropriate icon for each category"""
        icons = {
            "重要ポイント": "🎯",
            "主要な情報": "📌",
            "補足説明": "ℹ️"
        }
        return icons.get(category, "•")

    def _get_importance_style(self, importance: int) -> str:
        """Get style class based on importance level"""
        if importance >= 4:
            return "critical"
        elif importance >= 3:
            return "important"
        elif importance >= 2:
            return "normal"
        return "auxiliary"

    def _chunk_content(self, content: str, chunk_size: int = 40) -> List[str]:
        """より自然な文章の分割を実現する改善版チャンク処理"""
        if len(content) <= chunk_size:
            return [content]

        # 句読点による分割を優先
        sentence_delimiters = ['。', '！', '？', '．', '\n']
        parts = []
        current_chunk = ""
        buffer = ""

        for char in content:
            buffer += char
            
            # 句読点で区切る
            if char in sentence_delimiters:
                if len(current_chunk) + len(buffer) <= chunk_size:
                    current_chunk += buffer
                    buffer = ""
                else:
                    if current_chunk:
                        parts.append(current_chunk)
                    current_chunk = buffer
                    buffer = ""
            
            # バッファが一定サイズを超えたら強制分割
            if len(buffer) >= chunk_size:
                if current_chunk:
                    parts.append(current_chunk)
                parts.append(buffer.strip())
                current_chunk = ""
                buffer = ""

        # 残りのテキストを処理
        remaining = current_chunk + buffer
        if remaining:
            if len(remaining) <= chunk_size:
                parts.append(remaining)
            else:
                words = remaining.split()
                current_chunk = ""
                for word in words:
                    if len(current_chunk) + len(word) + 1 <= chunk_size:
                        current_chunk += (" " + word if current_chunk else word)
                    else:
                        if current_chunk:
                            parts.append(current_chunk)
                        current_chunk = word
                if current_chunk:
                    parts.append(current_chunk)

        return [part.strip() for part in parts if part.strip()]

    def generate_mindmap(self, text: str) -> Tuple[str, bool]:
        """Generate a mindmap from the given text"""
        try:
            cache_key = hashlib.md5(text.encode()).hexdigest()
            if cache_key in self._cache:
                logger.info("キャッシュからマインドマップを取得しました")
                return self._cache[cache_key], True

            data = self._validate_data(text)
            if not data:
                logger.error("データの検証に失敗しました")
                return self._create_fallback_mindmap(), False

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
