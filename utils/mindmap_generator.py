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

    def _validate_text(self, text: str) -> Tuple[bool, str]:
        """Validate input text"""
        if not text:
            return False, "入力テキストが空です"
        if len(text) < 10:
            return False, "テキストが短すぎます"
        if len(text) > 50000:
            return False, "テキストが長すぎます"
        return True, ""

    def _clean_japanese_text(self, text: str) -> str:
        """Clean and normalize Japanese text"""
        try:
            # Convert to half-width when appropriate
            text = jaconv.z2h(text, ascii=True, digit=True)
            # Normalize Japanese characters
            text = jaconv.normalize(text)
            # Remove repetitive punctuation
            text = re.sub(r'[！]{2,}', '！', text)
            text = re.sub(r'[？]{2,}', '？', text)
            text = re.sub(r'[。]{2,}', '。', text)
            # Clean spaces
            text = re.sub(r'[\u3000\s]+', ' ', text)
            return text.strip()
        except Exception as e:
            logger.error(f"Japanese text cleaning error: {str(e)}")
            return text

    def _validate_node_text(self, text: str, level: int) -> Optional[str]:
        """Validate and clean node text with enhanced Mermaid syntax compliance"""
        if not text:
            return None
        try:
            # Clean Japanese text
            text = self._clean_japanese_text(text)
            
            # Remove problematic characters
            text = re.sub(r'[<>{}()\[\]`"\'\\]', '', text)
            text = re.sub(r'[:_]', ' ', text)
            
            # Clean spaces
            text = text.strip()
            text = re.sub(r'\s+', ' ', text)
            
            # Level-specific processing
            if level == 0:  # Root node
                text = text.replace('root(', '').replace(')', '')
                if len(text) > 30:  # Shorter limit for root
                    text = text[:27] + '...'
                return f'root({text})'
            else:
                # Length limits for other levels
                max_length = 40 if level == 1 else 50
                if len(text) > max_length:
                    text = text[:max_length-3] + '...'
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
以下の要件に従ってマインドマップを生成してください：

入力テキスト：
{text}

出力規則：
1. 最初の行は必ず「mindmap」
2. インデントは半角スペース2個を使用
3. ルートノードは「root(テーマ)」形式で記述
4. 子ノードは単純なテキストで記述
5. 特殊文字は使用しない
6. 階層は最大3レベルまで

出力例：
mindmap
  root(メインテーマ)
    トピック1
      サブトピック1
      サブトピック2
    トピック2
      サブトピック3
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
        """Generate a fallback mindmap when the main generation fails"""
        current_time = time.strftime("%Y-%m-%d %H:%M:%S")
        return f'''mindmap
  root(コンテンツ解析エラー)
    エラー情報
      生成時刻: {current_time}
      再試行回数: {self.failed_attempts}
    対応方法
      データ確認
      再度実行
      サポート連絡'''

    def generate_mindmap(self, text: str) -> str:
        """Main method to generate mindmap with enhanced error handling"""
        try:
            # Input validation
            is_valid, error_msg = self._validate_text(text)
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
