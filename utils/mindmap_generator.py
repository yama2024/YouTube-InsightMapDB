import google.generativeai as genai
import os
import logging
import re
from typing import Dict, List, Optional, Tuple
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MindMapGenerator:
    def __init__(self):
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("Gemini API key is not set in environment variables")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-1.5-pro')
        
        # Updated node styles with proper Mermaid syntax
        self.node_styles = {
            'root': '[',  # Root node
            'main_topic': '([',  # Main topics
            'subtopic': '[[',  # Subtopics
            'detail': '{{',  # Details
            'key_point': '((',  # Key points
            'example': '>',  # Examples
            'conclusion': '}}'  # Conclusions
        }
        
        # Closing brackets for each style
        self.node_closings = {
            '[': ']',
            '([': '])',
            '[[': ']]',
            '{{': '}}',
            '((': '))',
            '>': ']',
            '}}': '}}'
        }

    def _escape_special_chars(self, text: str) -> str:
        """Escape special characters for Mermaid compatibility"""
        special_chars = ['&', '<', '>', '"', "'"]
        escaped_text = text
        for char in special_chars:
            escaped_text = escaped_text.replace(char, f'&#{ord(char)};')
        return escaped_text

    def _validate_node_text(self, text: str) -> str:
        """Validate and clean node text for Mermaid compatibility"""
        if not text:
            return text
        
        # Remove invalid characters but keep Japanese text
        text = self._escape_special_chars(text)
        text = re.sub(r'[^\w\s\u3000-\u9fff\u4e00-\u9faf\.,\-_()[\]{}><&;#]', '', text)
        return text.strip()

    def _format_node(self, text: str, style: str) -> str:
        """Format a node with proper Mermaid syntax"""
        text = self._validate_node_text(text)
        closing = self.node_closings.get(style, ']')
        return f"{style}{text}{closing}"

    def _format_mindmap_syntax(self, syntax: str) -> str:
        """Format and validate mindmap syntax with proper Mermaid styling"""
        if not syntax or not isinstance(syntax, str):
            return self._generate_fallback_mindmap()
        
        try:
            lines = ['mindmap']
            current_level = 0
            
            for line in syntax.strip().split('\n')[1:]:
                if line.strip():
                    # Calculate indentation level
                    indent = len(line) - len(line.lstrip())
                    indent_level = indent // 2
                    clean_line = line.strip()
                    
                    # Determine node style based on level and content
                    if indent_level == 0 and 'root' in clean_line.lower():
                        node_style = self.node_styles['root']
                    elif indent_level == 1:
                        node_style = self.node_styles['main_topic']
                    elif indent_level == 2:
                        node_style = self.node_styles['subtopic']
                    elif indent_level == 3:
                        node_style = self.node_styles['detail']
                    else:
                        node_style = self.node_styles['example']
                    
                    # Extract text content
                    if '(' in clean_line and ')' in clean_line:
                        text = re.search(r'\((.*?)\)', clean_line)
                        if text:
                            content = text.group(1)
                        else:
                            content = clean_line
                    else:
                        content = clean_line
                    
                    # Format node with proper syntax
                    formatted_node = self._format_node(content, node_style)
                    formatted_line = '  ' * indent_level + formatted_node
                    lines.append(formatted_line)
            
            return '\n'.join(lines)
            
        except Exception as e:
            logger.error(f"Mindmap formatting error: {str(e)}")
            return self._generate_fallback_mindmap()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, Exception))
    )
    def _generate_mindmap_internal(self, text: str) -> str:
        """Generate mindmap with retry mechanism and enhanced error handling"""
        prompt = f'''
以下のテキストから階層的なMermaid形式のマインドマップを生成してください。

入力テキスト：
{text}

必須規則：
1. 最初の行は「mindmap」のみ
2. インデントは半角スペース2個を使用
3. ルートノードは「root(概要)」の形式
4. 以下の階層構造を厳密に守る：
   - レベル0: ルートノード
   - レベル1: メインテーマ (3-4個)
   - レベル2: サブトピック (各メインテーマに2-3個)
   - レベル3: 詳細 (必要な場合のみ)
5. 各ノードは簡潔で明確な表現を使用

出力例：
mindmap
  root(概要)
    メインテーマ1
      サブトピック1.1
      サブトピック1.2
    メインテーマ2
      サブトピック2.1
      サブトピック2.2
'''

        try:
            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.3,
                    top_p=0.8,
                    top_k=40,
                    max_output_tokens=8192,
                )
            )
            
            if not response.text:
                raise ValueError("Empty response from API")
            
            return response.text.strip()
            
        except Exception as e:
            logger.error(f"Mindmap generation error: {str(e)}")
            raise Exception(f"マインドマップの生成に失敗しました: {str(e)}")

    def _generate_fallback_mindmap(self) -> str:
        """Generate a fallback mindmap with proper Mermaid syntax"""
        return '''mindmap
  root(コンテンツ概要)
    ((メインポイント))
      [[重要なトピック1]]
      [[重要なトピック2]]
    ((キーポイント))
      {{詳細1}}
      {{詳細2}}'''

    def generate_mindmap(self, text: str) -> str:
        """Generate mindmap with enhanced error handling and validation"""
        if not text:
            return self._generate_fallback_mindmap()
            
        try:
            # Generate initial mindmap
            mermaid_syntax = self._generate_mindmap_internal(text)
            
            # Validate basics
            if not mermaid_syntax.startswith('mindmap'):
                mermaid_syntax = 'mindmap\n' + mermaid_syntax
            
            # Format with proper syntax
            formatted_syntax = self._format_mindmap_syntax(mermaid_syntax)
            
            # Validate structure
            if len(formatted_syntax.split('\n')) < 3:
                logger.warning("Generated mindmap is too short, using fallback")
                return self._generate_fallback_mindmap()
            
            return formatted_syntax
            
        except Exception as e:
            logger.error(f"Mindmap generation failed: {str(e)}")
            return self._generate_fallback_mindmap()
