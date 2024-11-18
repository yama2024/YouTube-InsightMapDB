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
        self.model = genai.GenerativeModel('gemini-pro')

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
            
            # Ensure mindmap starts correctly
            if not lines or not lines[0].strip() == 'mindmap':
                formatted_lines.append('mindmap')
            else:
                formatted_lines.append('mindmap')
                lines = lines[1:]
            
            # Process each line
            for line in lines:
                clean_line = line.lstrip()
                indent_level = (len(line) - len(clean_line)) // 2
                
                # Handle root node and other nodes with special formatting
                if '((' in clean_line and '))' in clean_line:
                    match = re.search(r'\(\((.*?)\)\)', clean_line)
                    if match:
                        inner_text = match.group(1)
                        # Preserve emojis in node text
                        emoji_pattern = re.compile(r'[\U0001F300-\U0001F9FF]')
                        emojis = emoji_pattern.findall(inner_text)
                        escaped_text = self._escape_special_characters(inner_text)
                        # Add back emojis
                        for emoji in emojis:
                            escaped_text = escaped_text.replace(f'\\{emoji}', emoji)
                        if clean_line.startswith('root'):
                            clean_line = f"root(({escaped_text}))"
                        else:
                            clean_line = f"(({escaped_text}))"
                else:
                    # Handle normal nodes with icons
                    clean_line = self._escape_special_characters(clean_line)
                
                formatted_line = '  ' * indent_level + clean_line
                formatted_lines.append(formatted_line)
            
            # Join and validate final syntax
            result = '\n'.join(formatted_lines)
            if not result.startswith('mindmap'):
                raise ValueError("Invalid mindmap syntax")
            
            # Additional validation for proper structure
            node_count = len([line for line in formatted_lines if line.strip()])
            if node_count < 2:
                logger.warning("Mindmap has too few nodes")
                return self._generate_fallback_mindmap()
            
            return result
            
        except Exception as e:
            logger.error(f"Syntax formatting error: {str(e)}")
            return self._generate_fallback_mindmap()

    def generate_mindmap(self, text):
        """Generate mindmap from text"""
        if not text:
            return self._generate_fallback_mindmap()
            
        try:
            mermaid_syntax = self._generate_mindmap_internal(text)
            formatted_syntax = self._format_mindmap_syntax(mermaid_syntax)
            
            # Validate the generated syntax
            if not formatted_syntax or not formatted_syntax.startswith('mindmap'):
                logger.error("Generated invalid mindmap syntax")
                return self._generate_fallback_mindmap()
                
            return formatted_syntax
        except Exception as e:
            logger.error(f"Mindmap generation error: {str(e)}")
            return self._generate_fallback_mindmap()

    def _generate_mindmap_internal(self, text):
        """Internal method for mindmap generation"""
        prompt = """
テキストコンテンツからMermaid形式のマインドマップを生成してください。

入力テキスト:
{text}

必須フォーマット規則:
1. 最初の行は必ず 'mindmap' から始める
2. インデントは2スペースを使用
3. ルートノードは必ず root((テキスト)) の形式
4. 各ノードには適切な絵文字アイコンを追加（::icon[絵文字]の形式）

アイコンガイド:
- 📝 : 説明・定義
- 💡 : アイデア・インサイト
- 🔍 : 分析・詳細
- 📊 : データ・統計
- 🎯 : 目標・ゴール
- ⚡ : 重要ポイント
- 🔄 : プロセス・手順

出力例:
mindmap
  root((🎯 メインテーマ))
    概要::icon[📝]
      要点1::icon[💡]
      要点2::icon[⚡]
    詳細::icon[🔍]
      分析1::icon[📊]
      分析2::icon[📊]
"""

        try:
            response = self.model.generate_content(
                prompt.format(text=text),
                generation_config=genai.types.GenerationConfig(
                    temperature=0.2,  # Lower temperature for more consistent output
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
    主要ポイント::icon[⚡]
      重要な情報::icon[📝]
      キーポイント::icon[💡]
    詳細情報::icon[🔍]
      補足事項::icon[📊]
      参考データ::icon[📝]"""

    def create_visualization(self, mermaid_syntax):
        """Return the Mermaid syntax for visualization"""
        return mermaid_syntax
