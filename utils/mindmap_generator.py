import google.generativeai as genai
import os
import logging
import re
from typing import Dict, List

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
        
        # Node style definitions
        self.node_styles = {
            'root': '::',  # Root node style
            'main_topic': '[💡]',  # Main topics with light bulb
            'subtopic': '[📌]',  # Subtopics with pin
            'detail': '[ℹ️]',  # Details with info symbol
            'key_point': '[🔑]',  # Key points with key symbol
            'example': '[📝]',  # Examples with note symbol
            'conclusion': '[🎯]'  # Conclusions with target symbol
        }

    def _validate_node_text(self, text: str) -> str:
        """Validate and clean node text for Mermaid compatibility"""
        if not text:
            return text
        
        # Remove special characters but keep emojis and Japanese characters
        cleaned_text = re.sub(r'[^\w\s\u3000-\u9fff\u4e00-\u9faf\.,\-_()[\]💡📌ℹ️🔑📝🎯]', '', text)
        return cleaned_text.strip()

    def _format_mindmap_syntax(self, syntax: str) -> str:
        """Format and validate mindmap syntax with improved styling"""
        if not syntax or not isinstance(syntax, str):
            return self._generate_fallback_mindmap()
        
        lines = ['mindmap']
        current_level = 0
        
        for line in syntax.strip().split('\n')[1:]:
            if line.strip():
                # Calculate indentation level
                indent = len(line) - len(line.lstrip())
                indent_level = indent // 2
                clean_line = line.strip()
                
                # Add appropriate styling based on level
                if indent_level == 0 and 'root' in clean_line.lower():
                    style = self.node_styles['root']
                elif indent_level == 1:
                    style = self.node_styles['main_topic']
                elif indent_level == 2:
                    style = self.node_styles['subtopic']
                elif indent_level == 3:
                    style = self.node_styles['detail']
                else:
                    style = ''
                
                # Apply styling if not already present
                if not any(key in clean_line for key in self.node_styles.values()):
                    clean_line = f"{style} {clean_line}"
                
                formatted_line = '  ' * indent_level + clean_line
                lines.append(formatted_line)
                current_level = max(current_level, indent_level)
        
        return '\n'.join(lines)

    def _generate_mindmap_internal(self, text: str) -> str:
        prompt = f'''
以下のテキストから階層的で詳細なMermaid形式のマインドマップを生成してください。

入力テキスト：
{text}

必須規則：
1. 最初の行は「mindmap」のみ
2. インデントは半角スペース2個を使用
3. ルートノードは「root(コンテンツ概要)」の形式
4. 以下の階層構造を厳密に守る：
   - レベル1: メインテーマ（概要）
   - レベル2: 主要トピック（3-5個）
   - レベル3: サブトピックと詳細（各主要トピックに2-4個）
5. 各トピック間の関連性を明確に示す
6. トピックの分類と階層を論理的に整理する
7. キーポイントや重要な概念を強調する
8. 簡潔で明確な表現を使用する

出力例：
mindmap
  root(コンテンツ概要)
    主要トピック1
      サブトピック1.1
      サブトピック1.2
        詳細1.2.1
    主要トピック2
      キーポイント2.1
      サブトピック2.1
    主要トピック3
      結論3.1
      要点3.1
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
            
            if not response or not response.text:
                raise ValueError("Empty response from API")
            
            # Clean up the response
            mermaid_syntax = response.text.strip()
            
            # Remove code blocks if present
            if '```mermaid' in mermaid_syntax:
                mermaid_syntax = mermaid_syntax[mermaid_syntax.find('```mermaid')+10:]
            if '```' in mermaid_syntax:
                mermaid_syntax = mermaid_syntax[:mermaid_syntax.rfind('```')]
            
            return mermaid_syntax.strip()
            
        except Exception as e:
            logger.error(f"Error in mindmap generation: {str(e)}")
            raise Exception(f"Mindmap generation failed: {str(e)}")

    def _generate_fallback_mindmap(self) -> str:
        """Generate an enhanced fallback mindmap"""
        return '''mindmap
  root(コンテンツ概要)
    [💡] トピック1
      [📌] サブトピック1.1
      [ℹ️] 詳細1.1
    [💡] トピック2
      [📌] サブトピック2.1
      [🔑] キーポイント2.1'''

    def generate_mindmap(self, text: str) -> str:
        """Generate an enhanced mindmap with improved hierarchy and styling"""
        if not text:
            return self._generate_fallback_mindmap()
            
        try:
            # Generate base mindmap
            mermaid_syntax = self._generate_mindmap_internal(text)
            
            # Validate and format
            if not mermaid_syntax.startswith('mindmap'):
                mermaid_syntax = 'mindmap\n' + mermaid_syntax
                
            # Apply enhanced formatting
            formatted_syntax = self._format_mindmap_syntax(mermaid_syntax)
            
            # Final validation
            lines = formatted_syntax.split('\n')
            if len(lines) < 2 or not lines[1].strip().startswith('root('):
                return self._generate_fallback_mindmap()
                
            return formatted_syntax
            
        except Exception as e:
            logger.error(f"Mindmap generation error: {str(e)}")
            return self._generate_fallback_mindmap()
