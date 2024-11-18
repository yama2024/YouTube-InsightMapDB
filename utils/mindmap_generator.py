import google.generativeai as genai
import os
import logging
import re

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
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
        
        # Remove special characters except basic punctuation
        cleaned_text = re.sub(r'[^\w\s\u3000-\u9fff\u4e00-\u9faf\.,\-_]', '', text)
        return cleaned_text.strip()

    def _format_mindmap_syntax(self, syntax):
        """Format and validate mindmap syntax"""
        try:
            # Basic validation
            if not syntax or not isinstance(syntax, str):
                logger.error("Invalid syntax input")
                return self._generate_fallback_mindmap()

            # Split and clean lines
            lines = [line.rstrip() for line in syntax.strip().split('\n') if line.strip()]
            formatted_lines = []

            # Ensure mindmap starts correctly
            if not lines or lines[0].strip() != 'mindmap':
                formatted_lines.append('mindmap')
            else:
                formatted_lines.append('mindmap')
                lines = lines[1:]

            # Process each line
            current_indent = 0
            for line in lines:
                # Calculate proper indentation
                indent_match = re.match(r'^(\s*)', line)
                if indent_match:
                    current_indent = len(indent_match.group(1)) // 2
                    if current_indent > 3:  # Limit to 3 levels
                        current_indent = 3
                clean_line = line.lstrip()

                # Validate node text
                clean_line = self._validate_node_text(clean_line)
                
                # Format the line with proper indentation
                formatted_line = '  ' * current_indent + clean_line
                formatted_lines.append(formatted_line)

            # Join and validate final syntax
            result = '\n'.join(formatted_lines)
            
            # Validate structure
            if len(formatted_lines) < 2:
                logger.warning("Mindmap has too few nodes")
                return self._generate_fallback_mindmap()

            return result

        except Exception as e:
            logger.error(f"Syntax formatting error: {str(e)}")
            return self._generate_fallback_mindmap()

    def _generate_mindmap_internal(self, text):
        """Internal method for mindmap generation"""
        prompt = f"""
以下のテキストから簡潔なMermaid形式のマインドマップを生成してください。

入力テキスト:
{text}

必須フォーマット:
mindmap
  root((メインテーマ))
    トピック1
      サブトピック1
      サブトピック2
    トピック2
      サブトピック3

ルール:
1. 最初の行は必ず 'mindmap'
2. インデントは厳密に2スペース
3. 日本語テキストは括弧内でシンプルに表現
4. アイコンや特殊文字は使用しない
5. 最大3階層まで
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
        """Generate a simple fallback mindmap"""
        return """mindmap
  root((コンテンツ概要))
    トピック1
      サブトピック1
      サブトピック2
    トピック2
      サブトピック3"""

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
