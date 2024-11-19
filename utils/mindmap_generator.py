import google.generativeai as genai
import os
import logging
import re
import json
import time
from typing import Tuple, Optional, Dict
from cachetools import TTLCache
import jaconv

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
        
        # Initialize cache
        self.mindmap_cache = TTLCache(maxsize=100, ttl=3600)  # 1-hour cache
        self.failed_attempts = 0
        self.max_retries = 3
        self.rate_limit_wait_time = 60  # Base wait time for rate limits
        
        # Topic coverage requirements
        self.min_topics_per_level = {
            1: 3,  # At least 3 main topics
            2: 3   # At least 3 subtopics per main topic
        }
        self.max_topics_per_level = {
            1: 5,  # Maximum 5 main topics
            2: 5   # Maximum 5 subtopics per main topic
        }

    def _calculate_backoff_time(self, attempt: int) -> float:
        """Calculate progressive backoff time with exponential increase"""
        base_backoff = min(300, (2 ** attempt) * 30)  # Max 5 minutes
        jitter = random.uniform(0.8, 1.2)  # Add randomness to prevent thundering herd
        return base_backoff * jitter

    def _validate_input_text(self, text: str) -> Tuple[bool, str]:
        """Validate input text with enhanced Japanese support"""
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
        
        # Enhanced Japanese text validation
        jp_pattern = r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]'
        jp_content = re.findall(jp_pattern, text)
        if not jp_content:
            logger.warning("日本語のコンテンツが見つかりません")
        elif len(jp_content) < len(cleaned_text) * 0.3:
            logger.warning("日本語のコンテンツが少なめです")
        
        return True, ""

    def _normalize_japanese_text(self, text: str) -> str:
        """Enhanced Japanese text normalization"""
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
            
            # Normalize Japanese quotation marks
            text = text.replace('『', '「').replace('』', '」')
            text = text.replace('【', '「').replace('】', '」')
            
            return text.strip()
        except Exception as e:
            logger.error(f"Japanese text normalization error: {str(e)}")
            return text

    def _validate_node_text(self, text: str) -> Optional[str]:
        """Validate and clean node text"""
        if not text:
            return None
            
        try:
            # Normalize Japanese text
            text = self._normalize_japanese_text(text)
            
            # Remove Mermaid syntax characters
            text = re.sub(r'[[\](){}「」『』（）｛｝［］]', '', text)
            
            # Clean spaces
            text = text.strip()
            text = re.sub(r'\s+', ' ', text)
            
            # Truncate long text
            if len(text) > 50:
                text = text[:47] + '...'
            
            return text
            
        except Exception as e:
            logger.error(f"Node text validation error: {str(e)}")
            return None

    def _format_mindmap_syntax(self, syntax: str) -> str:
        """Format and validate Mermaid mindmap syntax"""
        try:
            # Basic validation
            if not syntax or not isinstance(syntax, str):
                logger.warning("Invalid mindmap syntax received")
                return self._generate_fallback_mindmap()
            
            # Process lines
            lines = ['mindmap']
            current_indent = 0
            node_count = {0: 0, 1: 0, 2: 0}  # Track nodes at each level
            
            for line in syntax.strip().split('\n')[1:]:  # Skip first 'mindmap' line
                if not line.strip():
                    continue
                
                # Calculate indentation
                indent = len(line) - len(line.lstrip())
                indent_level = min(indent // 2, 2)  # Maximum 3 levels (0, 1, 2)
                
                # Validate indentation
                if indent_level > current_indent + 1:
                    logger.warning(f"Invalid indentation level: {indent_level}")
                    indent_level = current_indent + 1
                
                # Check node count limits
                if node_count[indent_level] >= self.max_topics_per_level.get(indent_level, 5):
                    continue
                
                # Clean and validate node text
                clean_line = self._validate_node_text(line.strip())
                if clean_line:
                    # Format root node
                    if indent_level == 0 and not clean_line.startswith('root('):
                        clean_line = f'root({clean_line})'
                    
                    # Format line with proper indentation
                    formatted_line = '  ' * indent_level + clean_line
                    lines.append(formatted_line)
                    node_count[indent_level] += 1
                    current_indent = indent_level
            
            # Validate minimum requirements
            if node_count[1] < self.min_topics_per_level[1]:
                logger.warning("Insufficient main topics")
                return self._generate_fallback_mindmap()
            
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
以下のテキストからマインドマップを生成してください。

入力テキスト：
{text}

必須規則：
1. 基本構造
   - 「mindmap」で開始
   - インデントは半角スペース2個を使用
   - 最大3階層まで（root→main topics→subtopics）
   - 各トピックは3-5個のサブトピックを持つ

2. コンテンツ要件
   - メインテーマは内容を端的に表現
   - トピック間の関連性を明確に
   - 重要なキーワードや概念を強調
   - 技術的な詳細は簡潔に説明

3. 表現形式
   - シンプルで分かりやすい日本語
   - 専門用語は説明付きで記載
   - 最大文字数は各ノード50文字まで

出力例：
mindmap
  root(メインテーマ)
    トピック1
      サブトピック1-1
      サブトピック1-2
      サブトピック1-3
    トピック2
      サブトピック2-1
      サブトピック2-2
      サブトピック2-3
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
                    wait_time = self._calculate_backoff_time(retry_count)
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
                
                # Format and validate
                formatted_syntax = self._format_mindmap_syntax(mermaid_syntax)
                
                # Cache successful response
                self.mindmap_cache[cache_key] = formatted_syntax
                self.failed_attempts = 0
                
                logger.info("Successfully generated mindmap")
                return formatted_syntax

            except Exception as e:
                self.failed_attempts += 1
                last_error = str(e)
                retry_count += 1
                
                if "429" in last_error:
                    logger.error(f"Rate limit reached (attempt {retry_count})")
                elif "timeout" in last_error.lower():
                    logger.error(f"Request timeout (attempt {retry_count})")
                else:
                    logger.error(f"Mindmap generation error: {last_error}")

        logger.error(f"All retry attempts failed. Last error: {last_error}")
        return self._generate_fallback_mindmap()

    def _generate_fallback_mindmap(self) -> str:
        """Generate an improved fallback mindmap"""
        current_time = time.strftime("%Y-%m-%d %H:%M:%S")
        return f'''mindmap
  root(コンテンツ解析エラー)
    エラー情報
      生成時刻: {current_time}
      再試行回数: {self.failed_attempts}
      エラー状態: 一時的な問題
    代替アクション
      データの確認
        入力テキストの確認
        API状態の確認
      再試行オプション
        数分後に再試行
        手動での生成
    トラブルシューティング
      ログの確認
      設定の見直し
      サポートへの連絡'''

    def generate_mindmap(self, text: str) -> str:
        """Main method to generate mindmap with enhanced error handling"""
        try:
            # Input validation
            is_valid, error_msg = self._validate_input_text(text)
            if not is_valid:
                logger.error(f"Input validation failed: {error_msg}")
                return self._generate_fallback_mindmap()
            
            # Generate mindmap
            mindmap = self._generate_mindmap_internal(text)
            
            # Final validation
            if not mindmap or len(mindmap.split('\n')) < 3:
                logger.warning("Generated mindmap is too short or invalid")
                return self._generate_fallback_mindmap()
            
            return mindmap
            
        except Exception as e:
            logger.error(f"Mindmap generation failed: {str(e)}")
            return self._generate_fallback_mindmap()
