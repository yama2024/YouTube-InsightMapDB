import google.generativeai as genai
import os
import logging
import re

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class MindMapGenerator:
    def __init__(self):
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("Gemini API key is not set in environment variables")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-1.5-pro')

    def _validate_node_text(self, text):
        """Validate and clean node text for Mermaid compatibility"""
        if not text:
            return text
        
        # Remove special characters and emojis, keep basic punctuation and Japanese characters
        cleaned_text = re.sub(r'[^\w\s\u3000-\u9fff\u4e00-\u9faf\.,\-_()]', '', text)
        # Break long text into multiple lines for better readability
        if len(cleaned_text) > 30:
            words = cleaned_text.split()
            lines = []
            current_line = []
            current_length = 0
            
            for word in words:
                if current_length + len(word) > 30:
                    lines.append(' '.join(current_line))
                    current_line = [word]
                    current_length = len(word)
                else:
                    current_line.append(word)
                    current_length += len(word) + 1
                    
            if current_line:
                lines.append(' '.join(current_line))
            cleaned_text = '<br/>' + '<br/>'.join(lines)
        
        return cleaned_text.strip()

    def _format_mindmap_syntax(self, syntax):
        """Format and validate mindmap syntax with enhanced visualization"""
        try:
            if not syntax or not isinstance(syntax, str):
                logger.error("Invalid syntax input")
                return self._generate_fallback_mindmap()

            # Split and clean lines
            lines = [line.rstrip() for line in syntax.strip().split('\n') if line.strip()]
            formatted_lines = []

            # Add mindmap and style definitions
            formatted_lines.extend([
                'mindmap',
                '  %% Node styles',
                '  classDef root fill:#ff9,stroke:#333,stroke-width:2px',
                '  classDef topic fill:#fef,stroke:#333,stroke-width:1px',
                '  classDef subtopic fill:#eff,stroke:#333,stroke-width:1px'
            ])

            # Process each line
            current_indent = 0
            for line in lines[1:]:  # Skip 'mindmap' line
                # Calculate indentation
                indent_match = re.match(r'^(\s*)', line)
                current_indent = len(indent_match.group(1)) // 2 if indent_match else 0
                clean_line = line.lstrip()

                # Validate and format node text
                clean_line = self._validate_node_text(clean_line)
                
                # Add style classes based on level
                if current_indent == 0:
                    if not clean_line.endswith(':::root'):
                        clean_line = f"{clean_line}:::root"
                elif current_indent == 1:
                    if not clean_line.endswith(':::topic'):
                        clean_line = f"{clean_line}:::topic"
                else:
                    if not clean_line.endswith(':::subtopic'):
                        clean_line = f"{clean_line}:::subtopic"
                
                # Format line with proper indentation
                formatted_line = '  ' * current_indent + clean_line
                formatted_lines.append(formatted_line)

            return '\n'.join(formatted_lines)

        except Exception as e:
            logger.error(f"Syntax formatting error: {str(e)}")
            return self._generate_fallback_mindmap()

    def _generate_mindmap_internal(self, text):
        """Internal method for mindmap generation with improved structure"""
        prompt = f"""
以下のテキストから構造化されたMermaid形式のマインドマップを生成してください：

入力テキスト:
{text}

要件:
1. 階層構造を明確に表現
2. メインテーマは太字で強調
3. 関連するトピックをグループ化
4. サブトピックは簡潔に記述

フォーマット:
mindmap
  root(("メインテーマ")):::root
    トピック1:::topic
      サブトピック1:::subtopic
      サブトピック2:::subtopic
    トピック2:::topic
      サブトピック3:::subtopic

ルール:
1. 最初の行は必ず 'mindmap'
2. インデントは2スペース
3. 階層は最大3レベルまで
4. 長いテキストは<br/>で改行
5. スタイルクラスを適切に使用
"""

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

    def _generate_fallback_mindmap(self):
        """Generate a simple fallback mindmap with styling"""
        return """mindmap
  %% Node styles
  classDef root fill:#ff9,stroke:#333,stroke-width:2px
  classDef topic fill:#fef,stroke:#333,stroke-width:1px
  classDef subtopic fill:#eff,stroke:#333,stroke-width:1px
  root(("コンテンツ概要")):::root
    トピック1:::topic
      サブトピック1:::subtopic
      サブトピック2:::subtopic
    トピック2:::topic
      サブトピック3:::subtopic"""

    def generate_mindmap(self, text):
        """Generate mindmap from text"""
        if not text:
            return self._generate_fallback_mindmap()
            
        try:
            mermaid_syntax = self._generate_mindmap_internal(text)
            formatted_syntax = self._format_mindmap_syntax(mermaid_syntax)
            
            # Final validation
            if not formatted_syntax or not formatted_syntax.startswith('mindmap'):
                logger.error("Generated invalid mindmap syntax")
                return self._generate_fallback_mindmap()
                
            return formatted_syntax
        except Exception as e:
            logger.error(f"Mindmap generation error: {str(e)}")
            return self._generate_fallback_mindmap()

    def create_visualization(self, mermaid_syntax):
        """Return the Mermaid syntax for visualization"""
        return mermaid_syntax
