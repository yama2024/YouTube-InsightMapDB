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

    def _validate_node_text(self, text: str, level: int) -> Optional[str]:
        """Validate and clean node text with enhanced Mermaid syntax compliance"""
        if not text:
            return None
        try:
            # Remove problematic characters
            text = re.sub(r'[<>{}()[\]`]', '', text)
            
            # Clean spaces and normalize
            text = text.strip()
            text = re.sub(r'\s+', ' ', text)
            
            # Format based on level
            if level == 0:  # Root node
                text = text.replace('root(', '').replace(')', '')
                return f'root({text})'
            else:
                # Additional safety checks for other levels
                text = re.sub(r'[:"\'\\]', '', text)  # Remove characters that might break Mermaid
                return text
                
        except Exception as e:
            logger.error(f"Node text validation error: {str(e)}")
            return None

    def _validate_hierarchy(self, lines: list) -> bool:
        """Validate the mindmap hierarchy structure with enhanced checks"""
        try:
            if not lines or lines[0] != 'mindmap':
                logger.warning("Missing or invalid mindmap declaration")
                return False

            level_counts = {0: 0, 1: 0, 2: 0}
            current_level1 = None
            level1_subtopics = {}
            last_indent = -1
            
            for i, line in enumerate(lines[1:], 1):  # Skip 'mindmap' line
                if not line.strip():
                    continue
                
                # Check indentation consistency
                indent = len(line) - len(line.lstrip())
                if indent % 2 != 0:
                    logger.warning(f"Invalid indentation at line {i}: {indent}")
                    return False
                
                level = indent // 2
                if level > 2:
                    logger.warning(f"Invalid nesting level at line {i}: {level}")
                    return False
                
                # Check for proper level progression
                if level > last_indent + 1:
                    logger.warning(f"Invalid level jump at line {i}")
                    return False
                last_indent = level
                
                # Process node based on level
                clean_line = line.strip()
                if level == 0:
                    if not clean_line.startswith('root(') or not clean_line.endswith(')'):
                        logger.warning(f"Invalid root node format at line {i}")
                        return False
                    if level_counts[0] > 0:
                        logger.warning("Multiple root nodes detected")
                        return False
                    level_counts[0] += 1
                elif level == 1:
                    current_level1 = clean_line
                    level_counts[1] += 1
                    level1_subtopics[current_level1] = 0
                elif level == 2 and current_level1:
                    level_counts[2] += 1
                    level1_subtopics[current_level1] += 1
            
            # Validate structure requirements
            if level_counts[0] != 1:
                logger.warning("Invalid root node count")
                return False
            
            if not (self.min_topics_per_level[1] <= level_counts[1] <= self.max_topics_per_level[1]):
                logger.warning(f"Invalid main topic count: {level_counts[1]}")
                return False
            
            # Validate subtopic distribution
            for topic, count in level1_subtopics.items():
                if not (self.min_topics_per_level[2] <= count <= self.max_topics_per_level[2]):
                    logger.warning(f"Invalid subtopic count for {topic}: {count}")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Hierarchy validation error: {str(e)}")
            return False

    def _format_mindmap_syntax(self, syntax: str) -> str:
        """Format and validate Mermaid mindmap syntax with strict compliance checks"""
        try:
            # Basic validation
            if not syntax or not isinstance(syntax, str):
                logger.warning("Invalid mindmap syntax received")
                return self._generate_fallback_mindmap()
            
            # Process lines with strict formatting
            lines = ['mindmap']
            current_indent = 0
            node_count = {0: 0, 1: 0, 2: 0}
            current_level1_topic = None
            level1_subtopics = {}
            
            # Split and clean lines
            syntax_lines = [line.rstrip() for line in syntax.strip().split('\n')]
            
            for line in syntax_lines:
                if not line.strip() or line.strip() == 'mindmap':
                    continue
                
                # Calculate and validate indentation
                indent = len(line) - len(line.lstrip())
                if indent % 2 != 0:
                    logger.warning(f"Invalid indentation: {indent}")
                    continue
                
                indent_level = min(indent // 2, 2)
                
                # Validate level progression
                if indent_level > current_indent + 1:
                    logger.warning(f"Invalid level progression: {indent_level}")
                    continue
                
                # Process node text
                clean_line = self._validate_node_text(line.strip(), indent_level)
                if clean_line:
                    # Format line with proper indentation and track node counts
                    if indent_level == 0:
                        if node_count[0] > 0:
                            continue  # Skip additional root nodes
                        node_count[0] += 1
                    elif indent_level == 1:
                        if node_count[1] >= self.max_topics_per_level[1]:
                            continue
                        current_level1_topic = clean_line
                        level1_subtopics[clean_line] = 0
                        node_count[1] += 1
                    elif indent_level == 2 and current_level1_topic:
                        if level1_subtopics[current_level1_topic] >= self.max_topics_per_level[2]:
                            continue
                        level1_subtopics[current_level1_topic] += 1
                        node_count[2] += 1
                    
                    # Add formatted line with proper indentation
                    formatted_line = '  ' * indent_level + clean_line
                    lines.append(formatted_line)
                    current_indent = indent_level
            
            # Validate final structure
            if not self._validate_hierarchy(lines):
                logger.warning("Invalid mindmap hierarchy")
                return self._generate_fallback_mindmap()
            
            # Join lines with proper line endings
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
