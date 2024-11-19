import google.generativeai as genai
import os
import logging
import re
import json
import time
import random
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
            2: 2   # At least 2 subtopics per main topic
        }
        self.max_topics_per_level = {
            1: 5,  # Maximum 5 main topics
            2: 4   # Maximum 4 subtopics per main topic
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

    def _validate_node_text(self, text: str, level: int) -> Optional[str]:
        """Validate and clean node text with level-specific handling"""
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
            
            # Level-specific processing
            if level == 0:  # Root node
                max_length = 30
            elif level == 1:  # Main topics
                max_length = 40
            else:  # Subtopics and details
                max_length = 50
            
            # Truncate long text
            if len(text) > max_length:
                text = text[:max_length-3] + '...'
            
            return text
            
        except Exception as e:
            logger.error(f"Node text validation error: {str(e)}")
            return None

    def _validate_hierarchy(self, lines: list) -> bool:
        """Validate the mindmap hierarchy structure"""
        try:
            level_counts = {0: 0, 1: 0, 2: 0}
            current_level1 = None
            level1_subtopics = {}
            
            for line in lines:
                if not line.strip():
                    continue
                    
                indent = len(line) - len(line.lstrip())
                level = indent // 2
                
                if level > 2:  # Max 3 levels allowed
                    return False
                
                if level == 0:  # Root node
                    if level_counts[0] > 0:  # Only one root allowed
                        return False
                    level_counts[0] += 1
                elif level == 1:  # Main topics
                    current_level1 = line.strip()
                    level_counts[1] += 1
                    level1_subtopics[current_level1] = 0
                elif level == 2 and current_level1:  # Subtopics
                    level_counts[2] += 1
                    level1_subtopics[current_level1] += 1
            
            # Validate counts
            if level_counts[0] != 1:
                logger.warning("Invalid root node count")
                return False
                
            if not (self.min_topics_per_level[1] <= level_counts[1] <= self.max_topics_per_level[1]):
                logger.warning(f"Invalid main topic count: {level_counts[1]}")
                return False
                
            # Check subtopics distribution
            for topic, count in level1_subtopics.items():
                if not (self.min_topics_per_level[2] <= count <= self.max_topics_per_level[2]):
                    logger.warning(f"Invalid subtopic count for {topic}: {count}")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Hierarchy validation error: {str(e)}")
            return False

    def _format_mindmap_syntax(self, syntax: str) -> str:
        """Format and validate Mermaid mindmap syntax with enhanced structure validation"""
        try:
            # Basic validation
            if not syntax or not isinstance(syntax, str):
                logger.warning("Invalid mindmap syntax received")
                return self._generate_fallback_mindmap()
            
            # Process lines
            lines = ['mindmap']
            current_indent = 0
            node_count = {0: 0, 1: 0, 2: 0}  # Track nodes at each level
            current_level1_topic = None
            level1_subtopics = {}
            
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
                clean_line = self._validate_node_text(line.strip(), indent_level)
                if clean_line:
                    # Format root node
                    if indent_level == 0:
                        if not clean_line.startswith('root('):
                            clean_line = f'root({clean_line})'
                        node_count[0] += 1
                    elif indent_level == 1:
                        current_level1_topic = clean_line
                        level1_subtopics[clean_line] = 0
                        node_count[1] += 1
                    elif indent_level == 2 and current_level1_topic:
                        level1_subtopics[current_level1_topic] += 1
                        node_count[2] += 1
                    
                    # Format line with proper indentation
                    formatted_line = '  ' * indent_level + clean_line
                    lines.append(formatted_line)
                    current_indent = indent_level
            
            # Validate hierarchy
            if not self._validate_hierarchy(lines):
                logger.warning("Invalid mindmap hierarchy")
                return self._generate_fallback_mindmap()
            
            result = '\n'.join(lines)
            return result
            
        except Exception as e:
            logger.error(f"Mindmap formatting error: {str(e)}")
            return self._generate_fallback_mindmap()

    def _generate_mindmap_internal(self, text: str) -> str:
        """Generate mindmap with enhanced prompt and error handling"""
        prompt = f'''
GeminiのAPIを利用してYouTube動画のトランススクリプトを元に、高品質な要約を行い、それを視覚的に整理したマインドマップを生成してください。

# 入力テキスト
{text}

# 手順
1. トランススクリプト解析
   - 主要テーマ: 動画全体を通しての主要なメッセージや目的を抽出
   - サブテーマ: 主要テーマを補足する具体的なサブトピックを列挙
   - キーポイント: 各サブテーマに関連する重要なポイントやデータを抽出
   - アクション項目: 視聴者に行動を促す提案や具体例があればそれを明記

2. マインドマップ構造
   - 中心: 主要テーマ
   - 第1レベル: サブテーマ（3-5個）
   - 第2レベル: キーポイント（各サブテーマに2-4個）
   - 第3レベル: 詳細・具体例（必要に応じて）

3. 出力要件
   - インデントは半角スペース2個を使用
   - 各ノードは50文字以内の簡潔な表現
   - 日本語での表記を優先
   - 専門用語には簡単な説明を付記

# 出力形式
## マインドマップ（Mermaid形式）
mindmap
  root(メインテーマ)
    サブテーマ1
      キーポイント1-1
      キーポイント1-2
    サブテーマ2
      キーポイント2-1
      キーポイント2-2
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
