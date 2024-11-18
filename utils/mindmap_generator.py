import google.generativeai as genai
import os
import json
import time
import logging

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
                return self._generate_mindmap_internal(text)
            except Exception as e:
                error_str = str(e)
                if "429" in error_str and attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.info(f"API制限に達しました。{wait_time}秒後に再試行します...")
                    time.sleep(wait_time)
                    continue
                logger.error(f"マインドマップの生成に失敗しました (試行: {attempt + 1}/{max_retries}): {error_str}")
                raise Exception(f"マインドマップの生成中にエラーが発生しました。しばらく待ってから再度お試しください。: {error_str}")

    def _generate_mindmap_internal(self, text):
        """Internal method for mindmap generation in Mermaid mindmap format"""
        prompt = f"""
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
        - mindmap形式を使用すること
        - 中心テーマは((テーマ名))の形式で記述
        - インデントは2スペースで階層を表現
        - 最大3階層まで
        - 日本語で出力すること

        テキスト:
        {text}
        """
        
        try:
            response = self.model.generate_content(prompt)
            if not response.text:
                raise ValueError("APIレスポンスが空です")

            # Extract Mermaid syntax from the response
            mermaid_syntax = response.text.strip()
            if mermaid_syntax.startswith('```mermaid'):
                mermaid_syntax = mermaid_syntax[10:]
            if mermaid_syntax.endswith('```'):
                mermaid_syntax = mermaid_syntax[:-3]
            
            mermaid_syntax = mermaid_syntax.strip()
            
            # Validate the Mermaid syntax
            if not mermaid_syntax.startswith('mindmap'):
                raise ValueError("生成されたMermaid構文が不正です")
            
            # Debug output
            logger.info("Generated Mermaid syntax:")
            logger.info(mermaid_syntax)
            
            return mermaid_syntax
                
        except Exception as e:
            error_msg = f"マインドマップの生成中にエラーが発生しました: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)

    def create_visualization(self, mermaid_syntax):
        """Return the Mermaid syntax directly for visualization"""
        return mermaid_syntax
