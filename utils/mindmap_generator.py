import google.generativeai as genai
import os
import logging
import re
import json
import random
from typing import Tuple, Optional
from cachetools import TTLCache
import time
import jaconv  # For Japanese text normalization

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
        self.rate_limit_wait_time = 60  # Base wait time for rate limits

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
        
        # Validate Japanese text content
        jp_pattern = r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]'
        if not re.search(jp_pattern, text):
            logger.warning("日本語のコンテンツが見つかりません")
        
        return True, ""

    def _normalize_japanese_text(self, text: str) -> str:
        """Normalize Japanese text for better processing"""
        try:
            # Convert all forms of Japanese characters to their standard form
            text = jaconv.normalize(text)
            
            # Convert full-width to half-width where appropriate
            text = jaconv.z2h(text, ascii=True, digit=True)
            
            # Normalize whitespace
            text = re.sub(r'[\u3000\s]+', ' ', text)
            
            # Remove repetitive punctuation
            text = re.sub(r'[！]{2,}', '！', text)
            text = re.sub(r'[？]{2,}', '？', text)
            text = re.sub(r'[。]{2,}', '。', text)
            
            return text.strip()
        except Exception as e:
            logger.error(f"Japanese text normalization error: {str(e)}")
            return text

    def _validate_node_text(self, text: str) -> Optional[str]:
        """Validate and clean node text with enhanced Japanese support"""
        if not text:
            return None
        
        try:
            # Normalize Japanese text
            text = self._normalize_japanese_text(text)
            
            # Remove Mermaid syntax characters and other special characters
            text = re.sub(r'[[\](){}「」『』（）｛｝［］]', '', text)
            
            # Clean and normalize spacing
            text = text.strip()
            text = re.sub(r'\s+', ' ', text)
            
            # Ensure proper length (considering Japanese characters)
            text_length = sum(2 if '\u4e00' <= c <= '\u9fff' else 1 for c in text)
            if text_length > 50:
                # Truncate while preserving meaning
                current_length = 0
                truncated_text = ''
                for char in text:
                    char_length = 2 if '\u4e00' <= char <= '\u9fff' else 1
                    if current_length + char_length > 47:
                        truncated_text += '...'
                        break
                    truncated_text += char
                    current_length += char_length
                text = truncated_text
            
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
                    # Format root node
                    if indent_level == 0 and not clean_line.startswith('root('):
                        clean_line = f'root({clean_line})'
                    
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

    def _generate_mindmap_internal(self, text: str) -> str:
        """Generate mindmap with enhanced prompt and error handling"""
        prompt = f'''
        以下のテキストから詳細なマインドマップを生成してください。

        入力テキスト：
        {text}

        必須規則：
        1. 最初の行は必ず「mindmap」で開始
        2. インデントは半角スペース2個を使用
        3. ルートノードは「root(メインテーマ)」形式
        4. 階層構造：
           - 最大3階層まで
           - 各階層最大5項目
           - 論理的な階層関係を維持
        5. ノードテキスト：
           - 簡潔で意味のある表現
           - 50文字以内
           - 特殊文字は使用しない
        6. コンテンツ要件：
           - メインテーマは内容を端的に表現
           - トピック間の関連性を明確に
           - 重要なキーワードや概念を強調

        出力例：
        mindmap
          root(コンテンツの核心)
            重要な概念
              具体例1
              具体例2
            主要な論点
              詳細な説明
              重要な示唆
        '''

        # Check cache
        cache_key = hash(text)
        if cache_key in self.mindmap_cache:
            logger.info("Using cached mindmap")
            return self.mindmap_cache[cache_key]

        retry_count = 0
        last_error = None

        while retry_count < self.max_retries:
            try:
                # Exponential backoff with rate limit handling
                if retry_count > 0:
                    wait_time = min(300, self.rate_limit_wait_time * (2 ** (retry_count - 1)))
                    logger.info(f"Retrying in {wait_time} seconds (attempt {retry_count + 1}/{self.max_retries})")
                    time.sleep(wait_time)

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
                    raise ValueError("AIモデルからの応答が空です")

                mermaid_syntax = response.text.strip()
                
                # Clean up the response
                if '```mermaid' in mermaid_syntax:
                    mermaid_syntax = mermaid_syntax[mermaid_syntax.find('```mermaid')+10:]
                if '```' in mermaid_syntax:
                    mermaid_syntax = mermaid_syntax[:mermaid_syntax.rfind('```')]
                
                # Validate and format
                if not mermaid_syntax.startswith('mindmap'):
                    mermaid_syntax = 'mindmap\n' + mermaid_syntax

                # Cache successful response
                self.mindmap_cache[cache_key] = mermaid_syntax
                self.failed_attempts = 0
                
                logger.info(f"マインドマップの生成に成功しました (試行回数: {retry_count + 1})")
                return mermaid_syntax

            except Exception as e:
                self.failed_attempts += 1
                last_error = str(e)
                retry_count += 1

                if "429" in last_error:
                    logger.error(f"APIレート制限に達しました (試行回数: {retry_count})")
                    self.rate_limit_wait_time = min(300, self.rate_limit_wait_time * 2)
                elif "timeout" in last_error.lower():
                    logger.error(f"リクエストがタイムアウトしました (試行回数: {retry_count})")
                else:
                    logger.error(f"マインドマップ生成エラー: {last_error}")

        logger.error(f"全ての試行が失敗しました。最後のエラー: {last_error}")
        return self._generate_fallback_mindmap()

    def _generate_fallback_mindmap(self) -> str:
        """Generate an improved fallback mindmap"""
        current_time = time.strftime("%Y-%m-%d %H:%M:%S")
        return f'''mindmap
  root(コンテンツ解析結果)
    エラー情報
      生成時刻: {current_time}
      再試行回数: {self.failed_attempts}
    代替表示
      主要ポイント
      重要キーワード
    アクション
      内容を確認
      再生成を試行'''

    def generate_mindmap(self, text: str) -> str:
        """Main method to generate mindmap with enhanced error handling"""
        try:
            # Input validation
            is_valid, error_msg = self._validate_input_text(text)
            if not is_valid:
                logger.error(f"入力検証に失敗しました: {error_msg}")
                return self._generate_fallback_mindmap()
            
            # Generate mindmap
            mermaid_syntax = self._generate_mindmap_internal(text)
            
            # Format and validate syntax
            formatted_syntax = self._format_mindmap_syntax(mermaid_syntax)
            
            # Final validation
            if not formatted_syntax or len(formatted_syntax.split('\n')) < 3:
                logger.warning("生成されたマインドマップが短すぎるか無効です")
                return self._generate_fallback_mindmap()
            
            return formatted_syntax
            
        except Exception as e:
            logger.error(f"マインドマップ生成エラー: {str(e)}")
            return self._generate_fallback_mindmap()
