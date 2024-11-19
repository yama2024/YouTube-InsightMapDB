import google.generativeai as genai
import os
import logging
import re
import json
import random
from typing import Tuple, Optional
from cachetools import TTLCache
import time

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
        
        # Initialize cache for responses
        self.mindmap_cache = TTLCache(maxsize=100, ttl=3600)  # 1-hour cache
        self.failed_attempts = 0
        self.max_retries = 3

    def _validate_input_text(self, text: str) -> Tuple[bool, str]:
        """Validate input text with enhanced checks"""
        if not text:
            return False, "入力テキストが空です"
        
        if len(text) < 10:
            return False, "テキストが短すぎます (最小10文字)"
        
        if len(text) > 50000:
            return False, "テキストが長すぎます (最大50000文字)"
        
        # Check for meaningful content
        cleaned_text = re.sub(r'\s+', '', text)
        if not cleaned_text:
            return False, "有効なテキストコンテンツがありません"
        
        # Validate character encoding
        try:
            text.encode('utf-8').decode('utf-8')
        except UnicodeError:
            return False, "テキストエンコーディングが無効です"
        
        return True, ""

    def _validate_node_text(self, text: str) -> Optional[str]:
        """Validate and clean node text for Mermaid syntax"""
        if not text:
            return None
        
        try:
            # Remove any existing Mermaid syntax characters
            text = re.sub(r'[[\](){}]', '', text)
            
            # Clean and normalize text
            text = text.strip()
            text = re.sub(r'\s+', ' ', text)
            
            # Ensure proper node format
            if len(text) > 50:  # Shorter maximum length for better visualization
                text = text[:47] + '...'
            
            # Add proper node syntax for root and regular nodes
            if text.lower().startswith('root'):
                return f'root({text[4:].strip()})'
            
            return text
            
        except Exception as e:
            logger.error(f"Node text validation error: {str(e)}")
            return None

    def _format_mindmap_syntax(self, syntax: str) -> str:
        """Format and validate Mermaid mindmap syntax"""
        try:
            if not syntax or not isinstance(syntax, str):
                logger.warning("Invalid mindmap syntax received")
                return self._generate_fallback_mindmap()
            
            lines = ['mindmap']
            current_indent = 0
            node_count = {0: 0, 1: 0, 2: 0}  # Track nodes at each level
            
            # Split and process each line
            for line in syntax.strip().split('\n')[1:]:
                if not line.strip():
                    continue
                
                # Calculate indentation level
                indent = len(line) - len(line.lstrip())
                indent_level = min(indent // 2, 2)  # Maximum 3 levels (0, 1, 2)
                
                # Validate indentation
                if indent_level > current_indent + 1:
                    logger.warning(f"Invalid indentation level: {indent_level}")
                    indent_level = current_indent + 1
                
                # Check node count at this level
                if node_count[indent_level] >= 5:  # Maximum 5 items per level
                    continue
                
                # Clean and validate node text
                clean_line = self._validate_node_text(line.strip())
                if clean_line:
                    # Ensure exactly 2 spaces per indent level
                    formatted_line = '  ' * indent_level + clean_line
                    lines.append(formatted_line)
                    node_count[indent_level] += 1
                    current_indent = indent_level
            
            # Validate minimum structure
            result = '\n'.join(lines)
            if len(lines) < 3:  # Ensure at least root and one child node
                logger.warning("Generated mindmap too short")
                return self._generate_fallback_mindmap()
            
            return result
            
        except Exception as e:
            logger.error(f"Mindmap formatting error: {str(e)}")
            return self._generate_fallback_mindmap()

    def _calculate_backoff_time(self, attempt: int) -> float:
        """Calculate exponential backoff time"""
        base_delay = min(60, (2 ** attempt) * 5)
        jitter = random.uniform(0, 0.1 * base_delay)
        return base_delay + jitter

    def _generate_mindmap_internal(self, text: str) -> str:
        """Generate mindmap with enhanced error handling and retries"""
        prompt = f'''
        以下のテキストから構造化されたマインドマップを生成してください：

        入力テキスト：
        {text}

        必須規則：
        1. 最初の行は必ず「mindmap」のみ
        2. インデントは半角スペース2個を厳密に使用
        3. ルートノードは「root(テーマ)」形式で記述
        4. 子ノードはシンプルなテキストで記述
        5. 特殊文字は使用しない
        6. 各ノードは50文字以内
        7. 最大3階層まで
        8. 各階層最大5項目まで

        出力例：
        mindmap
          root(メインテーマ)
            トピック1
              サブトピック1
              サブトピック2
            トピック2
              サブトピック3
        '''

        # Check cache first
        cache_key = hash(text)
        if cache_key in self.mindmap_cache:
            logger.info("Using cached mindmap")
            return self.mindmap_cache[cache_key]

        for attempt in range(self.max_retries):
            try:
                generation_config = genai.types.GenerationConfig(
                    temperature=0.3,
                    top_p=0.8,
                    top_k=40,
                    max_output_tokens=8192
                )

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
                
                # Cache successful response
                self.mindmap_cache[cache_key] = mermaid_syntax
                self.failed_attempts = 0
                
                logger.info(f"Successfully generated mindmap on attempt {attempt + 1}")
                return mermaid_syntax

            except Exception as e:
                self.failed_attempts += 1
                error_msg = str(e)
                
                if "429" in error_msg:
                    logger.error(f"Rate limit reached on attempt {attempt + 1}")
                    if attempt < self.max_retries - 1:
                        wait_time = self._calculate_backoff_time(attempt)
                        logger.info(f"Waiting {wait_time} seconds before retry")
                        time.sleep(wait_time)
                    else:
                        raise ValueError("Rate limit exceeded. Please try again later.")
                
                elif "timeout" in error_msg.lower():
                    logger.error(f"Request timeout on attempt {attempt + 1}")
                    if attempt < self.max_retries - 1:
                        wait_time = 5 * (attempt + 1)
                        logger.info(f"Waiting {wait_time} seconds before retry")
                        time.sleep(wait_time)
                    else:
                        raise ValueError("Request timeout. Please try again.")
                
                else:
                    logger.error(f"Error generating mindmap: {error_msg}")
                    if attempt == self.max_retries - 1:
                        return self._generate_fallback_mindmap()
                    time.sleep(3 * (attempt + 1))

        return self._generate_fallback_mindmap()

    def _generate_fallback_mindmap(self) -> str:
        """Generate a simple fallback mindmap"""
        return '''mindmap
  root(コンテンツ概要)
    主要トピック
      重要ポイント1
      重要ポイント2
    サブトピック
      詳細1
      詳細2'''

    def generate_mindmap(self, text: str) -> str:
        """Main method to generate mindmap with validation"""
        try:
            # Validate input
            is_valid, error_msg = self._validate_input_text(text)
            if not is_valid:
                logger.error(f"Input validation failed: {error_msg}")
                return self._generate_fallback_mindmap()
            
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
