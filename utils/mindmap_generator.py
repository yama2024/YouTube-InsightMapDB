import google.generativeai as genai
import os
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
        self.model = genai.GenerativeModel('gemini-1.5-pro')

    def _validate_node_text(self, text):
        """Validate and clean node text for Mermaid compatibility"""
        if not text:
            return text
        
        # Remove special characters and emojis, keep basic punctuation and Japanese characters
        cleaned_text = re.sub(r'[^\w\s\u3000-\u9fff\u4e00-\u9faf\.,\-_()]', '', text)
        return cleaned_text.strip()

    def _format_mindmap_syntax(self, syntax):
        # 入力検証
        if not syntax or not isinstance(syntax, str):
            return self._generate_fallback_mindmap()
        
        lines = []
        lines.append('mindmap')
        
        for line in syntax.strip().split('\n')[1:]:
            if line.strip():
                indent = len(line) - len(line.lstrip())
                indent_level = indent // 2
                clean_line = line.strip()
                if clean_line:
                    formatted_line = '  ' * indent_level + clean_line
                    lines.append(formatted_line)
        
        return '\n'.join(lines)

    def _generate_mindmap_internal(self, text):
        prompt = f'''
以下のテキストから最小限のMermaid形式のマインドマップを生成してください：

入力テキスト：
{text}

必須規則：
1. 必ず最初の行は「mindmap」のみ
2. インデントは厳密に半角スペース2個
3. ルートノードは「root(メインテーマ)」の形式
4. 子ノードはプレーンテキストのみ
5. 装飾や特殊文字は使用禁止
6. 最大2階層まで

出力例：
mindmap
  root(メインテーマ)
    トピック1
    トピック2
      サブトピック1
      サブトピック2
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

    def _generate_fallback_mindmap(self):
        """Generate a simple fallback mindmap"""
        return '''mindmap
  root(コンテンツ概要)
    トピック1
      サブトピック1
    トピック2
      サブトピック2'''

    def generate_mindmap(self, text):
        if not text:
            return self._generate_fallback_mindmap()
            
        try:
            # マインドマップを生成
            mermaid_syntax = self._generate_mindmap_internal(text)
            
            # 基本的な検証
            if not mermaid_syntax.startswith('mindmap'):
                mermaid_syntax = 'mindmap\n' + mermaid_syntax
                
            # フォーマットを適用
            formatted_syntax = self._format_mindmap_syntax(mermaid_syntax)
            
            # 最終検証
            lines = formatted_syntax.split('\n')
            if len(lines) < 2 or not lines[1].strip().startswith('root('):
                return self._generate_fallback_mindmap()
                
            return formatted_syntax
        except Exception as e:
            logger.error(f"Mindmap generation error: {str(e)}")
            return self._generate_fallback_mindmap()
