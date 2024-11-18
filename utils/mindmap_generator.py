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
        """Validate and clean node text"""
        if not text:
            return text

        # Define allowed special characters
        allowed_chars = set('()[]{}:,._-')
        emoji_pattern = re.compile(r'[\U0001F300-\U0001F9FF]')

        # Extract emojis
        emojis = emoji_pattern.findall(text)
        
        # Clean text
        cleaned_text = text
        for char in text:
            if not (char.isalnum() or char.isspace() or char in allowed_chars or emoji_pattern.match(char)):
                cleaned_text = cleaned_text.replace(char, '')

        return cleaned_text

    def _escape_special_characters(self, text):
        """Escape special characters in text while preserving icon syntax"""
        if not text:
            return text

        if '::icon[' in text:
            parts = text.split('::icon[')
            escaped_parts = []
            for i, part in enumerate(parts):
                if i == 0:
                    escaped_parts.append(self._escape_text_part(part))
                else:
                    icon_end = part.find(']')
                    if icon_end != -1:
                        icon = part[:icon_end]
                        remaining = part[icon_end + 1:]
                        escaped_parts.append(f"::icon[{icon}]{self._escape_text_part(remaining)}")
                    else:
                        escaped_parts.append(self._escape_text_part(part))
            return ''.join(escaped_parts)
        else:
            return self._escape_text_part(text)

    def _escape_text_part(self, text):
        """Escape special characters in text part"""
        if not text:
            return text
            
        special_chars = ['\\', '(', ')', '[', ']', ':', '-', '_', '/', '、', '。', '「', '」']
        escaped_text = text
        for char in special_chars:
            escaped_text = escaped_text.replace(char, f'\\{char}')
        return escaped_text

    def _format_mindmap_syntax(self, syntax):
        """Format and validate the mindmap syntax"""
        try:
            # Basic validation
            if not syntax or not isinstance(syntax, str):
                logger.error("Invalid syntax input")
                return self._generate_fallback_mindmap()

            # Split and clean lines
            lines = [line.rstrip() for line in syntax.strip().split('\n') if line.strip()]
            formatted_lines = []
            
            # Validate mindmap header
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
                clean_line = line.lstrip()

                # Validate node text
                clean_line = self._validate_node_text(clean_line)
                
                # Handle root node and other nodes
                if '((' in clean_line and '))' in clean_line:
                    match = re.search(r'\(\((.*?)\)\)', clean_line)
                    if match:
                        inner_text = match.group(1)
                        # Preserve emojis and handle Japanese text
                        emoji_pattern = re.compile(r'[\U0001F300-\U0001F9FF]')
                        emojis = emoji_pattern.findall(inner_text)
                        escaped_text = self._escape_special_characters(inner_text)
                        for emoji in emojis:
                            escaped_text = escaped_text.replace(f'\\{emoji}', emoji)
                        
                        # Format root node
                        if clean_line.startswith('root'):
                            clean_line = f"root((🎯 {escaped_text}))"
                        else:
                            clean_line = f"(({escaped_text}))"
                else:
                    # Handle normal nodes with icons
                    clean_line = self._escape_special_characters(clean_line)

                # Ensure proper indentation
                formatted_line = '  ' * current_indent + clean_line
                formatted_lines.append(formatted_line)

            # Validate final syntax
            result = '\n'.join(formatted_lines)
            
            # Additional validation
            if not result.startswith('mindmap'):
                raise ValueError("Invalid mindmap syntax: Must start with 'mindmap'")
            
            # Validate structure
            node_count = len([line for line in formatted_lines if line.strip()])
            if node_count < 2:
                logger.warning("Mindmap has too few nodes")
                return self._generate_fallback_mindmap()

            # Validate root node format
            root_line = None
            for line in formatted_lines[1:]:  # Skip 'mindmap' line
                if line.strip():
                    root_line = line
                    break
            
            if not root_line or not re.match(r'\s*root\(\(🎯.*?\)\)', root_line):
                logger.error("Invalid root node format")
                return self._generate_fallback_mindmap()

            return result

        except Exception as e:
            logger.error(f"Syntax formatting error: {str(e)}")
            return self._generate_fallback_mindmap()

    def _generate_mindmap_internal(self, text):
        """Internal method for mindmap generation"""
        prompt = f"""
以下のテキストからMermaid形式のマインドマップを生成してください。

入力テキスト:
{text}

必須フォーマット:
mindmap
  root((🎯 メインテーマ))
    トピック1::icon[📚]
      サブトピック1::icon[💡]
      サブトピック2::icon[📝]
    トピック2::icon[🔍]
      サブトピック3::icon[📊]

ルール:
1. 最初の行は必ず 'mindmap'
2. インデントは2スペース
3. ルートノードは root((🎯 テーマ)) の形式
4. 各ノードには必ずアイコンを付加 (::icon[絵文字])
5. 3-4階層の構造を維持
6. 日本語テキストは適切にエスケープ

使用可能なアイコン:
- 📚 概要・基本情報
- 💡 重要ポイント
- 🔍 詳細分析
- 📊 データ統計
- 📝 具体例
- ⚡ キーポイント
- 🔄 プロセス
- ✨ 特徴
- 🎯 テーマ

マインドマップの構造:
1. メインテーマを🎯で表現
2. 主要トピックを第2階層に配置
3. 詳細を第3階層以降に展開
4. 関連性の高い項目をグループ化
"""

        try:
            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.2,
                    top_p=0.9,
                    top_k=40,
                    max_output_tokens=8192,
                )
            )
            
            if not response or not response.text:
                raise ValueError("Empty response from API")
            
            # Clean up the response
            mermaid_syntax = response.text.strip()
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
  root((🎯 コンテンツ概要))
    トピック1::icon[📚]
      サブトピック1::icon[💡]
      サブトピック2::icon[📝]
    トピック2::icon[🔍]
      サブトピック3::icon[📊]"""

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
