import google.generativeai as genai
import os
import logging
import re
from typing import Optional, Dict, Any

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MindMapError(Exception):
    """Custom exception for mindmap generation errors"""
    pass

class MindMapGenerator:
    def __init__(self):
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("Gemini API key is not set in environment variables")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-1.5-pro')
        
        # Style configurations
        self.styles = {
            'root': '::styleclass{fill:url(#grad1),color:#fff}',
            'main': '::styleclass{fill:#1E88E5,color:#fff}',
            'sub': '::styleclass{fill:#42A5F5,color:#fff}',
            'detail': '::styleclass{fill:#90CAF9,color:#333}'
        }
        
        # Maximum text lengths for different node types
        self.max_lengths = {
            'root': 30,
            'main': 40,
            'sub': 50,
            'detail': 60
        }

    def _validate_node_text(self, text: str, node_type: str = 'detail') -> str:
        """Validate and clean node text for Mermaid compatibility"""
        if not text:
            return "No content"
        
        # Remove special characters and emojis, keep basic punctuation and Japanese characters
        cleaned_text = re.sub(r'[^\w\s\u3000-\u9fff\u4e00-\u9faf\.,\-_()]', '', text)
        cleaned_text = cleaned_text.strip()
        
        # Truncate text based on node type
        max_length = self.max_lengths.get(node_type, 60)
        if len(cleaned_text) > max_length:
            cleaned_text = cleaned_text[:max_length-3] + "..."
            
        return cleaned_text

    def _format_mindmap_syntax(self, content: Dict[str, Any]) -> str:
        """Format mindmap with enhanced styling and hierarchy"""
        try:
            lines = ['mindmap']
            
            # Add gradient definition
            lines.append('  %% Apple-inspired gradient')
            lines.append('  %%{')
            lines.append('    init: {')
            lines.append('      "theme": "base",')
            lines.append('      "themeVariables": {')
            lines.append('        "fontSize": "16px"')
            lines.append('      }')
            lines.append('    }')
            lines.append('  }%%')
            
            # Add root node
            root_text = self._validate_node_text(content.get('title', 'Content Summary'), 'root')
            lines.append(f'  root(({root_text}))')
            lines.append('    ::icon(fas fa-lightbulb)')
            lines.append(self.styles['root'])
            
            # Add main topics
            for i, topic in enumerate(content.get('main_topics', [])):
                topic_text = self._validate_node_text(topic['title'], 'main')
                lines.append(f'    main[{topic_text}]')
                lines.append(self.styles['main'])
                
                # Add subtopics
                for subtopic in topic.get('subtopics', []):
                    subtopic_text = self._validate_node_text(subtopic['title'], 'sub')
                    lines.append(f'      sub[{subtopic_text}]')
                    lines.append(self.styles['sub'])
                    
                    # Add details
                    for detail in subtopic.get('details', []):
                        detail_text = self._validate_node_text(detail, 'detail')
                        lines.append(f'        detail[{detail_text}]')
                        lines.append(self.styles['detail'])
            
            return '\n'.join(lines)
            
        except Exception as e:
            logger.error(f"Error formatting mindmap: {str(e)}")
            raise MindMapError(f"マインドマップのフォーマット中にエラーが発生しました: {str(e)}")

    def _process_summary_content(self, summary: str) -> Dict[str, Any]:
        """Process AI summary to extract structured content"""
        prompt = f"""
        以下のAI要約から、階層的なマインドマップ構造を生成してください。

        入力テキスト：
        {summary}

        以下のJSON形式で出力してください：
        {{
            "title": "メインテーマ",
            "main_topics": [
                {{
                    "title": "主要トピック1",
                    "subtopics": [
                        {{
                            "title": "サブトピック1",
                            "details": ["詳細1", "詳細2"]
                        }}
                    ]
                }}
            ]
        }}

        要件：
        1. 最大3つの主要トピック
        2. 各主要トピックに最大2つのサブトピック
        3. 各サブトピックに最大3つの詳細
        4. 簡潔で明確な表現を使用
        """

        try:
            response = self.model.generate_content(prompt)
            if not response or not response.text:
                raise ValueError("AI応答が空です")
            
            # Extract JSON from response
            json_str = re.search(r'\{[\s\S]*\}', response.text)
            if not json_str:
                raise ValueError("JSON構造が見つかりません")
                
            import json
            content = json.loads(json_str.group())
            return content
            
        except Exception as e:
            logger.error(f"Error processing summary content: {str(e)}")
            raise MindMapError(f"要約コンテンツの処理中にエラーが発生しました: {str(e)}")

    def _generate_fallback_mindmap(self) -> str:
        """Generate a simple fallback mindmap with styling"""
        return '''mindmap
  root((コンテンツ概要))
    ::icon(fas fa-lightbulb)
    ::styleclass{fill:#1E88E5,color:#fff}
  main[トピック1]
    ::styleclass{fill:#42A5F5,color:#fff}
    sub[サブトピック1]
      ::styleclass{fill:#90CAF9,color:#333}
  main[トピック2]
    ::styleclass{fill:#42A5F5,color:#fff}
    sub[サブトピック2]
      ::styleclass{fill:#90CAF9,color:#333}'''

    def generate_mindmap(self, summary: str) -> str:
        """Generate mindmap from AI summary with enhanced styling and error handling"""
        if not summary:
            logger.warning("Empty summary provided, using fallback mindmap")
            return self._generate_fallback_mindmap()
            
        try:
            # Process the summary content
            content = self._process_summary_content(summary)
            
            # Generate formatted mindmap
            mindmap = self._format_mindmap_syntax(content)
            
            # Validate basic structure
            if not mindmap.startswith('mindmap'):
                raise MindMapError("Invalid mindmap structure")
                
            return mindmap
            
        except MindMapError as e:
            logger.error(f"Mindmap generation error: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in mindmap generation: {str(e)}")
            return self._generate_fallback_mindmap()
