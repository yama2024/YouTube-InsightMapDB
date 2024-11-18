import google.generativeai as genai
import os
import json
import time
import logging
import re

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MindMapGenerator:
    def __init__(self):
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("Gemini API key is not set in environment variables")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-pro')

    def generate_mindmap(self, text, max_retries=3):
        """Generate mindmap data from text using Gemini API with retry mechanism"""
        for attempt in range(max_retries):
            try:
                logger.info(f"マインドマップ生成を試行中... (試行: {attempt + 1}/{max_retries})")
                mermaid_syntax = self._generate_mindmap_internal(text)
                
                # Validate and format the syntax
                formatted_syntax = self._format_mindmap_syntax(mermaid_syntax)
                return formatted_syntax
                
            except Exception as e:
                error_str = str(e)
                if "429" in error_str and attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.info(f"API制限に達しました。{wait_time}秒後に再試行します...")
                    time.sleep(wait_time)
                    continue
                logger.error(f"マインドマップの生成に失敗しました (試行: {attempt + 1}/{max_retries}): {error_str}")
                if attempt == max_retries - 1:
                    # Fallback to a simple mindmap structure
                    return self._generate_fallback_mindmap(text)
                raise Exception(f"マインドマップの生成中にエラーが発生しました。しばらく待ってから再度お試しください。: {error_str}")

    def _escape_japanese_parentheses(self, text):
        """Escape parentheses in Japanese text for Mermaid syntax"""
        return text.replace('(', '\\(').replace(')', '\\)')

    def _format_mindmap_syntax(self, syntax):
        """Format and validate the mindmap syntax"""
        lines = syntax.strip().split('\n')
        formatted_lines = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            if line.startswith('mindmap'):
                formatted_lines.append('mindmap')
                continue
                
            # Count leading spaces to determine level
            spaces = len(line) - len(line.lstrip())
            level = spaces // 2
            
            # Remove existing spaces
            line = line.strip()
            
            # Add proper indentation
            if '((' in line and '))' in line:
                # Root node or any node with double parentheses
                try:
                    match = re.search(r'\(\((.*?)\)\)', line)
                    if match:
                        text = match.group(1)
                        escaped_text = self._escape_japanese_parentheses(text)
                        if line.startswith('root'):
                            line = f"root(({escaped_text}))"
                        else:
                            line = f"(({escaped_text}))"
                except Exception as e:
                    logger.warning(f"正規表現のマッチングに失敗しました: {str(e)}")
                    # Keep the line as is if regex fails
            
            # Add proper indentation
            formatted_lines.append('  ' * level + line)
        
        # Ensure proper mindmap format
        result = '\n'.join(formatted_lines)
        if not result.startswith('mindmap'):
            result = 'mindmap\n' + result
            
        return result

    def _generate_fallback_mindmap(self, text):
        """Generate a simple fallback mindmap when the main generation fails"""
        return """mindmap
  root((コンテンツ概要))
    主要ポイント
      ポイント1
      ポイント2
    詳細情報
      詳細1
      詳細2"""

    def _generate_mindmap_internal(self, text):
        """Internal method for mindmap generation in Mermaid mindmap format"""
        prompt = """
        以下のテキストから階層的なマインドマップをMermaid形式で生成してください。
        以下の形式で出力してください：

        ```mermaid
        mindmap
          root((中心テーマ))
            トピック1
              サブトピック1
              サブトピック2
            トピック2
              サブトピック3
              サブトピック4
        ```

        注意点:
        1. 必ずmindmapで開始すること
        2. 必ず2スペースでインデントすること
        3. 日本語のテキストを(())で囲む場合は\\(\\)でエスケープすること
        4. 最大3階層までとすること
        5. 階層は必ず2スペースずつ増やすこと
        6. 日本語で出力すること

        テキスト:
        {text}
        """
        
        try:
            response = self.model.generate_content(prompt.format(text=text))
            if not response.text:
                raise ValueError("APIレスポンスが空です")

            # Extract Mermaid syntax from the response
            mermaid_syntax = response.text.strip()
            if '```mermaid' in mermaid_syntax:
                mermaid_syntax = mermaid_syntax[mermaid_syntax.find('```mermaid')+10:]
            if '```' in mermaid_syntax:
                mermaid_syntax = mermaid_syntax[:mermaid_syntax.rfind('```')]
            
            mermaid_syntax = mermaid_syntax.strip()
            
            # Validate the Mermaid syntax
            if not mermaid_syntax.startswith('mindmap'):
                mermaid_syntax = 'mindmap\n' + mermaid_syntax
            
            # Debug output
            logger.info("生成されたMermaid構文:")
            logger.info(mermaid_syntax)
            
            return mermaid_syntax
                
        except Exception as e:
            error_msg = f"マインドマップの生成中にエラーが発生しました: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)

    def create_visualization(self, mermaid_syntax):
        """Return the Mermaid syntax directly for visualization"""
        return mermaid_syntax
