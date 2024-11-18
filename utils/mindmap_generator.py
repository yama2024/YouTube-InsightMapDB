import google.generativeai as genai
import os
import json
import time
import logging
import re

# Set up logging with more detailed format
logging.basicConfig(
    level=logging.DEBUG,  # Changed to DEBUG for more detailed logs
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
        """Escape special characters in text for Mermaid syntax"""
        # Enhanced special characters list
        special_chars = ['\\', '(', ')', '[', ']', ':', '-', '_', '/', '、', '。', '「', '」']
        escaped_text = text
        for char in special_chars:
            escaped_text = escaped_text.replace(char, f'\\{char}')
        
        # Log the escaping process
        if escaped_text != text:
            logger.debug(f"テキストをエスケープしました: '{text}' -> '{escaped_text}'")
        
        return escaped_text

    def _format_mindmap_syntax(self, syntax):
        """Format and validate the mindmap syntax with strict rules"""
        logger.info("マインドマップ構文のフォーマットを開始します")
        
        try:
            # Split and clean lines
            lines = [line.rstrip() for line in syntax.strip().split('\n') if line.strip()]
            formatted_lines = []
            
            # Ensure mindmap starts correctly
            if not lines or not lines[0].strip() == 'mindmap':
                logger.warning("mindmapキーワードが見つかりません。追加します。")
                formatted_lines.append('mindmap')
            else:
                formatted_lines.append('mindmap')
                lines = lines[1:]
            
            for line in lines:
                # Remove all existing indentation
                clean_line = line.lstrip()
                
                # Calculate proper indentation level
                indent_level = (len(line) - len(clean_line)) // 2
                
                # Process the line content
                if '((' in clean_line and '))' in clean_line:
                    try:
                        # Extract and escape text within double parentheses
                        match = re.search(r'\(\((.*?)\)\)', clean_line)
                        if match:
                            inner_text = match.group(1)
                            escaped_text = self._escape_special_characters(inner_text)
                            if clean_line.startswith('root'):
                                clean_line = f"root(({escaped_text}))"
                            else:
                                clean_line = f"(({escaped_text}))"
                            logger.debug(f"括弧内のテキストを処理しました: {inner_text} -> {escaped_text}")
                    except Exception as e:
                        logger.error(f"括弧内のテキスト処理中にエラーが発生: {str(e)}")
                        # Continue with original line if processing fails
                        logger.warning(f"オリジナルの行を使用します: {clean_line}")
                else:
                    # Escape special characters in regular text
                    clean_line = self._escape_special_characters(clean_line)
                
                # Add proper indentation
                formatted_line = '  ' * indent_level + clean_line
                formatted_lines.append(formatted_line)
                logger.debug(f"フォーマット済みの行: {formatted_line}")
            
            # Join lines and validate final syntax
            result = '\n'.join(formatted_lines)
            
            # Validate basic syntax
            if not result.startswith('mindmap'):
                raise ValueError("生成された構文が'mindmap'で始まっていません")
            
            logger.info("マインドマップ構文のフォーマットが完了しました")
            logger.debug("生成された最終的な構文:\n" + result)
            
            return result
            
        except Exception as e:
            error_msg = f"構文フォーマット中にエラーが発生しました: {str(e)}"
            logger.error(error_msg)
            logger.info("フォールバック構文を生成します")
            return self._generate_fallback_mindmap("")

    def generate_mindmap(self, text, max_retries=3):
        """Generate mindmap data from text using Gemini API with retry mechanism"""
        for attempt in range(max_retries):
            try:
                logger.info(f"マインドマップ生成を試行中... (試行: {attempt + 1}/{max_retries})")
                mermaid_syntax = self._generate_mindmap_internal(text)
                formatted_syntax = self._format_mindmap_syntax(mermaid_syntax)
                return formatted_syntax
            except Exception as e:
                error_str = str(e)
                logger.error(f"エラーの詳細: {error_str}")
                
                if "429" in error_str and attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.info(f"API制限に達しました。{wait_time}秒後に再試行します...")
                    time.sleep(wait_time)
                    continue
                
                logger.error(f"マインドマップの生成に失敗しました (試行: {attempt + 1}/{max_retries})")
                if attempt == max_retries - 1:
                    logger.info("フォールバックマインドマップを生成します")
                    return self._generate_fallback_mindmap(text)
                
        return self._generate_fallback_mindmap(text)

    def _generate_mindmap_internal(self, text):
        """Internal method for mindmap generation in Mermaid mindmap format"""
        prompt = """
以下の手順で{text}の内容を分析し、Mermaid形式のマインドマップを作成してください：

1. コンテンツの主要テーマを特定
2. 関連する概念やトピックを抽出
3. 論理的な階層構造を構築

出力形式:
mindmap
  root((メインテーマ))
    トピック1
      サブトピック1
      サブトピック2
    トピック2
      サブトピック3

注意事項:
- 必ず'mindmap'で開始
- インデントは2スペース
- rootノードは((テキスト))形式
- 特殊文字は必ずエスケープ
- 最大3階層まで
- 日本語テキストは適切にエスケープ
"""
        
        try:
            logger.info("Gemini APIにリクエストを送信中...")
            response = self.model.generate_content(prompt.format(text=text))
            
            if not response.text:
                raise ValueError("APIレスポンスが空です")

            # Extract and clean Mermaid syntax
            mermaid_syntax = response.text.strip()
            if '```mermaid' in mermaid_syntax:
                mermaid_syntax = mermaid_syntax[mermaid_syntax.find('```mermaid')+10:]
            if '```' in mermaid_syntax:
                mermaid_syntax = mermaid_syntax[:mermaid_syntax.rfind('```')]
            
            mermaid_syntax = mermaid_syntax.strip()
            logger.debug("生成された生のMermaid構文:\n" + mermaid_syntax)
            
            return mermaid_syntax
            
        except Exception as e:
            error_msg = f"マインドマップの生成中にエラーが発生しました: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)

    def _generate_fallback_mindmap(self, text):
        """Generate a simple fallback mindmap when the main generation fails"""
        logger.info("フォールバックマインドマップを生成します")
        return """mindmap
  root((コンテンツ概要))
    主要ポイント
      重要な情報
      キーポイント
    詳細情報
      補足事項
      参考データ"""

    def create_visualization(self, mermaid_syntax):
        """Return the Mermaid syntax directly for visualization"""
        return mermaid_syntax
