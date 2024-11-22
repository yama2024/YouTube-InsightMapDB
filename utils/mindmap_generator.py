import json
import hashlib
import logging
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)

class MindMapGenerator:
    def __init__(self):
        self._cache = {}

    def generate_mindmap(self, text: str) -> Tuple[Optional[Dict], bool]:
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
            mindmap_data = self._create_mindmap(data)
            
            # Cache only valid results
            if mindmap_data:
                self._cache[cache_key] = mindmap_data
                logger.info("新しいマインドマップを生成してキャッシュしました")
                return mindmap_data, True
            
            logger.warning("生成されたマインドマップが無効です")
            return self._create_fallback_mindmap(), False
            
        except Exception as e:
            logger.error(f"マインドマップの生成中にエラーが発生しました: {str(e)}")
            return self._create_fallback_mindmap(), False

    def _validate_data(self, text: str) -> Optional[Dict]:
        """Validate and parse the input data"""
        try:
            data = json.loads(text)
            if not isinstance(data, dict):
                logger.error("Invalid data format")
                return None
            
            required_fields = ["タイトル", "ポイント"]
            if not all(field in data for field in required_fields):
                logger.error("Required fields missing in data")
                return None
                
            return data
        except json.JSONDecodeError:
            logger.error("Invalid JSON format")
            return None
        except Exception as e:
            logger.error(f"Data validation error: {str(e)}")
            return None

    def _create_mindmap(self, data: Dict) -> Optional[Dict]:
        """Create a hierarchical mindmap structure"""
        try:
            # Create root node
            mindmap = {
                "text": data.get("タイトル", "マインドマップ"),
                "class": "root",
                "children": []
            }
            
            # Process main categories
            categories = self._categorize_points(data.get("ポイント", []))
            
            for category, points in categories.items():
                category_node = {
                    "text": f"{self._get_category_icon(category)} {category}",
                    "class": self._get_category_class(category),
                    "children": []
                }
                
                # Add points under categories
                for point in points:
                    content = point.get("内容", "")
                    importance = point.get("重要度", 2)
                    
                    # Split long content into chunks
                    chunks = self._chunk_content(content)
                    
                    # Create point node
                    point_node = {
                        "text": chunks[0],
                        "class": self._get_importance_class(importance),
                        "children": []
                    }
                    
                    # Add additional chunks as child nodes if necessary
                    if len(chunks) > 1:
                        for chunk in chunks[1:]:
                            point_node["children"].append({
                                "text": chunk,
                                "class": "continuation"
                            })
                    
                    category_node["children"].append(point_node)
                
                mindmap["children"].append(category_node)
            
            return mindmap
            
        except Exception as e:
            logger.error(f"Error creating mindmap structure: {str(e)}")
            return None

    def _categorize_points(self, points: List[Dict]) -> Dict[str, List[Dict]]:
        """Categorize points based on their content and importance"""
        categories = {
            "重要ポイント": [],
            "主要な情報": [],
            "補足説明": []
        }
        
        for point in points:
            importance = point.get("重要度", 2)
            if importance >= 4:
                categories["重要ポイント"].append(point)
            elif importance >= 2:
                categories["主要な情報"].append(point)
            else:
                categories["補足説明"].append(point)
                
        return {k: v for k, v in categories.items() if v}

    def _get_category_icon(self, category: str) -> str:
        """Get appropriate icon for each category"""
        icons = {
            "重要ポイント": "🎯",
            "主要な情報": "📌",
            "補足説明": "ℹ️"
        }
        return icons.get(category, "•")

    def _get_category_class(self, category: str) -> str:
        """Get CSS class for category styling"""
        classes = {
            "重要ポイント": "critical-category",
            "主要な情報": "main-category",
            "補足説明": "sub-category"
        }
        return classes.get(category, "default-category")

    def _get_importance_class(self, importance: int) -> str:
        """Get CSS class based on importance level"""
        if importance >= 4:
            return "critical"
        elif importance >= 3:
            return "important"
        elif importance >= 2:
            return "normal"
        return "auxiliary"

    def _chunk_content(self, content: str, max_length: int = 40) -> List[str]:
        """Split content into manageable chunks"""
        if len(content) <= max_length:
            return [content]
            
        chunks = []
        current_chunk = ""
        
        for char in content:
            current_chunk += char
            if len(current_chunk) >= max_length and (char in "。、.,!?！？"):
                chunks.append(current_chunk)
                current_chunk = ""
        
        if current_chunk:
            chunks.append(current_chunk)
            
        return chunks if chunks else [content]

    def _create_fallback_mindmap(self) -> Dict:
        """Create a simple fallback mindmap when generation fails"""
        return {
            "text": "エラー",
            "class": "root",
            "children": [{
                "text": "マインドマップの生成に失敗しました",
                "class": "error"
            }]
        }