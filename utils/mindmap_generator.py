import google.generativeai as genai
import os
import logging
import re
import json

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
        # Replace newlines and multiple spaces
        cleaned_text = re.sub(r'\s+', ' ', cleaned_text)
        # Trim whitespace
        return cleaned_text.strip()

    def _format_mindmap_syntax(self, syntax):
        """Format and validate Mermaid mindmap syntax"""
        try:
            if not syntax or not isinstance(syntax, str):
                logger.warning("Invalid mindmap syntax received")
                return self._generate_fallback_mindmap()
            
            lines = ['mindmap']
            current_indent = 0
            
            # Process each line after 'mindmap'
            for line in syntax.strip().split('\n')[1:]:
                if line.strip():
                    # Calculate indentation level
                    indent = len(line) - len(line.lstrip())
                    indent_level = indent // 2
                    
                    # Validate indentation
                    if indent_level > current_indent + 1:
                        logger.warning(f"Invalid indentation level: {indent_level}")
                        indent_level = current_indent + 1
                    
                    # Clean and validate node text
                    clean_line = self._validate_node_text(line.strip())
                    if clean_line:
                        formatted_line = '  ' * indent_level + clean_line
                        lines.append(formatted_line)
                        current_indent = indent_level
            
            result = '\n'.join(lines)
            logger.debug(f"Formatted mindmap:\n{result}")
            return result
            
        except Exception as e:
            logger.error(f"Error in mindmap formatting: {str(e)}")
            return self._generate_fallback_mindmap()

    def _generate_mindmap_internal(self, text):
        """Generate mindmap from text with enhanced error handling and validation"""
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
            # Set specific generation parameters for better control
            generation_config = genai.types.GenerationConfig(
                temperature=0.3,
                top_p=0.8,
                top_k=40,
                max_output_tokens=8192,
                stop_sequences=["\n\n", "```"]
            )
            
            # Generate content with retry mechanism
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = self.model.generate_content(
                        prompt,
                        generation_config=generation_config
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
                    
                    # Validate basic structure
                    if not mermaid_syntax.startswith('mindmap'):
                        mermaid_syntax = 'mindmap\n' + mermaid_syntax
                    
                    # Validate root node
                    lines = mermaid_syntax.split('\n')
                    if len(lines) < 2 or not any(line.strip().startswith('root(') for line in lines[1:]):
                        raise ValueError("Missing root node in generated mindmap")
                    
                    logger.info(f"Successfully generated mindmap on attempt {attempt + 1}")
                    return mermaid_syntax.strip()
                    
                except Exception as e:
                    logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")
                    if attempt == max_retries - 1:
                        raise
                    continue
            
        except Exception as e:
            logger.error(f"Error in mindmap generation: {str(e)}")
            return self._generate_fallback_mindmap()

    def _generate_fallback_mindmap(self):
        """Generate a simple fallback mindmap"""
        return '''mindmap
  root(コンテンツ概要)
    トピック1
      サブトピック1
    トピック2
      サブトピック2'''

    def generate_mindmap(self, text):
        """Main method to generate mindmap with validation"""
        if not text:
            logger.warning("Empty input text received")
            return self._generate_fallback_mindmap()
            
        try:
            # Generate mindmap
            mermaid_syntax = self._generate_mindmap_internal(text)
            
            # Format and validate syntax
            formatted_syntax = self._format_mindmap_syntax(mermaid_syntax)
            
            # Final validation
            if not formatted_syntax or len(formatted_syntax.split('\n')) < 3:
                logger.warning("Generated mindmap is too short or invalid")
                return self._generate_fallback_mindmap()
            
            return formatted_syntax
            
        except Exception as e:
            logger.error(f"Mindmap generation error: {str(e)}")
            return self._generate_fallback_mindmap()
