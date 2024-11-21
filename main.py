import re
from utils.youtube_helper import YouTubeHelper
from utils.text_processor import TextProcessor
from utils.mindmap_generator import MindMapGenerator
from utils.pdf_generator import PDFGenerator
import streamlit as st
import os
import time
import logging
import json

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import streamlit_mermaid at the top level
from streamlit_mermaid import st_mermaid
# Text processing functions
def process_text_in_chunks(text: str, chunk_size: int = 2000, overlap: int = 100) -> list:
    """Process text in chunks with overlap"""
    if not text:
        return []
    text_length = len(text)
    chunks = []
    start = 0
    while start < text_length:
        end = min(start + chunk_size, text_length)
        if end < text_length:
            # Find next sentence boundary
            while end < text_length and text[end] not in '.。!！?？':
                end += 1
            end += 1  # Include the punctuation mark
        else:
            end = text_length
        
        # Extract chunk and add to list
        chunk = text[start:end]
        chunks.append(chunk)
        
        # Move start position for next chunk
        start = end - overlap
        # Find next sentence boundary
        while start < text_length and text[start] not in '.。!！?？':
            start += 1
        start += 1  # Start after the punctuation mark
    
    return chunks

def validate_processed_text(original_text, processed_text):
    """Validate the processed text length and content"""
    original_length = len(original_text)
    processed_length = len(processed_text)
    
    length_difference = abs(original_length - processed_length)
    max_allowed_difference = original_length * 0.1
    
    if length_difference > max_allowed_difference:
        raise ValueError(f"""校正に失敗しました:
- 期待される文字数: {original_length}
- 実際の文字数: {processed_length}
- 不足文字数: {abs(original_length - processed_length)}""")
    
    return True

try:
    # Page configuration
    st.set_page_config(page_title="YouTube InsightMap",
                       page_icon="🎯",
                       layout="wide",
                       initial_sidebar_state="collapsed")

    # Load CSS
    def load_css():
        try:
            css_path = os.path.join(os.path.dirname(__file__), 'styles',
                                    'custom.css')
            if os.path.exists(css_path):
                with open(css_path) as f:
                    st.markdown(f'<style>{f.read()}</style>',
                               unsafe_allow_html=True)
            else:
                logger.error("CSS file not found!")
        except Exception as e:
            logger.error(f"Error loading CSS: {str(e)}")

    load_css()

    def copy_text_block(text, label=""):
        try:
            if label:
                st.markdown(f"#### {label}")
            st.markdown(text, unsafe_allow_html=False)
        except Exception as e:
            logger.error(f"Error in copy_text_block: {str(e)}")

    # Initialize session state with error handling
    if 'current_step' not in st.session_state:
        st.session_state.current_step = 1
    if 'steps_completed' not in st.session_state:
        st.session_state.steps_completed = {
            'video_info': False,
            'transcript': False,
            'summary': False,
            'mindmap': False,
            'proofread': False,
            'pdf': False
        }
    if 'video_info' not in st.session_state:
        st.session_state.video_info = None
    if 'transcript' not in st.session_state:
        st.session_state.transcript = None
    if 'summary' not in st.session_state:
        st.session_state.summary = None
    if 'quality_scores' not in st.session_state:
        st.session_state.quality_scores = None
    if 'mindmap' not in st.session_state:
        st.session_state.mindmap = None
    if 'mindmap_svg' not in st.session_state:
        st.session_state.mindmap_svg = None
    if 'pdf_data' not in st.session_state:
        st.session_state.pdf_data = None
    if 'enhanced_text' not in st.session_state:
        st.session_state.enhanced_text = None
    if 'enhancement_progress' not in st.session_state:
        st.session_state.enhancement_progress = {
            'progress': 0.0,
            'message': ''
        }
    if 'current_summary_style' not in st.session_state:
        st.session_state.current_summary_style = "overview"  # Default to overview

    def update_step_progress(step_name: str, completed: bool = True):
        """Update the completion status of a processing step"""
        try:
            st.session_state.steps_completed[step_name] = completed
        except Exception as e:
            logger.error(f"Error updating step progress: {str(e)}")

    # Application Header
    st.markdown('''
    <div class="app-header">
        <div class="app-title">YouTube InsightMap</div>
        <div class="app-subtitle">Content Knowledge Visualization</div>
    </div>
    ''',
                unsafe_allow_html=True)

    def get_step_status(step_number):
        try:
            if st.session_state.current_step > step_number:
                return "completed"
            elif st.session_state.current_step == step_number:
                return "active"
            return ""
        except Exception as e:
            logger.error(f"Error getting step status: {str(e)}")
            return ""

    def render_step_header(step_number, title, emoji, description=""):
        try:
            status = get_step_status(step_number)
            st.markdown(f'''
            <div class="step-header {status}">
                <div class="step-content">
                    <div class="step-title">{emoji} {title}</div>
                    {f'<div class="step-description">{description}</div>' if description else ''}
                </div>
            </div>
            ''',
                        unsafe_allow_html=True)
        except Exception as e:
            logger.error(f"Error rendering step header: {str(e)}")

    def get_score_indicator(score: float) -> tuple:
        """Get visual indicator and color class based on score"""
        if score >= 7:
            return "✅", "high"
        elif score >= 5:
            return "⚠️", "medium"
        return "❌", "low"

    def render_quality_score(score: float, label: str, description: str):
        """品質スコアを視覚的に表示"""
        indicator, score_class = get_score_indicator(score)
        
        st.markdown(f"""
        <div class="score-item">
            <div class="score-header">
                <div class="score-title">
                    {indicator} {label}
                    <div class="score-range score-{score_class}">
                        {score:.1f}/10
                    </div>
                </div>
            </div>
            <div class="score-description">{description}</div>
            <div class="score-bar">
                <div class="score-fill {score_class}" style="width: {score*10}%;"></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    def display_summary(summary_text: str):
        """Display formatted summary with importance indicators"""
        try:
            # Ensure the summary is valid JSON
            if not summary_text or not summary_text.strip():
                raise ValueError("要約テキストが空です")
                
            summary_data = json.loads(summary_text.strip())
            
            # Always display overview
            st.markdown("## 📑 動画の概要")
            st.markdown(summary_data.get("動画の概要", ""))
            
            if st.session_state.current_summary_style == "detailed":
                # Display points with proper type conversion
                st.markdown("## 🎯 主要ポイント")
                for point in summary_data.get("ポイント", []):
                    try:
                        importance = int(point.get("重要度", 3))
                    except (ValueError, TypeError):
                        importance = 3
                    
                    emoji = "🔥" if importance >= 4 else "⭐" if importance >= 2 else "ℹ️"
                    
                    st.markdown(f'''
                        <div class="summary-card">
                            <div class="importance-{'high' if importance >= 4 else 'medium' if importance >= 2 else 'low'}">
                                {emoji} <strong>ポイント{point.get("番号", "")}: {point.get("タイトル", "")}</strong>
                            </div>
                            <p>{point.get("内容", "")}</p>
                            {f'<p class="supplementary-info">{point.get("補足情報", "")}</p>' if "補足情報" in point else ""}
                        </div>
                    ''', unsafe_allow_html=True)
                
                st.markdown("## 🔑 重要なキーワード")
                for keyword in summary_data.get("キーワード", []):
                    st.markdown(f'''
                        <div class="keyword-card">
                            <strong>{keyword.get("用語", "")}</strong>: {keyword.get("説明", "")}
                            {f'<div class="related-terms">関連用語: {", ".join(keyword.get("関連用語", []))}</div>' if "関連用語" in keyword else ""}
                        </div>
                    ''', unsafe_allow_html=True)
                
                # Display quality scores only in detailed mode
                quality_scores = st.session_state.quality_scores
                if quality_scores:
                    st.markdown('''
                    <div class="quality-score-section">
                        <h3>要約品質スコア</h3>
                        <div class="quality-score-container">
                    ''', unsafe_allow_html=True)
                    
                    render_quality_score(
                        quality_scores["構造の完全性"],
                        "構造の完全性",
                        "要約の構造がどれだけ整っているか"
                    )
                    render_quality_score(
                        quality_scores["情報量"],
                        "情報量",
                        "重要な情報をどれだけ含んでいるか"
                    )
                    render_quality_score(
                        quality_scores["簡潔性"],
                        "簡潔性",
                        "簡潔に要点を示せているか"
                    )
                    render_quality_score(
                        quality_scores["総合スコア"],
                        "総合スコア",
                        "全体的な要約の質"
                    )
                    
                    st.markdown('</div></div>', unsafe_allow_html=True)
            
            # Always display conclusion
            st.markdown("## 💡 結論")
            st.markdown(summary_data.get("結論", ""))
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error: {str(e)}")
            st.error("要約データの形式が正しくありません。再試行してください。")
        except Exception as e:
            logger.error(f"Summary display error: {str(e)}")
            st.error("要約の表示中にエラーが発生しました")

    # Feature Introduction
    st.markdown('''
    <div class="glass-container feature-container">
        <h4 class="section-header" style="margin-top: 0;">🎯 Advanced Content Analysis</h4>
        <div class="feature-grid">
            <div class="feature-card">
                <div class="feature-icon">📝</div>
                <h5 class="feature-title">文字起こし</h5>
            </div>
            <div class="feature-card">
                <div class="feature-icon">🤖</div>
                <h5 class="feature-title">要約</h5>
            </div>
            <div class="feature-card">
                <div class="feature-icon">🔄</div>
                <h5 class="feature-title">マップ化</h5>
            </div>
        </div>
    </div>
    ''',
                unsafe_allow_html=True)

    # Main application logic
    try:
        # Step 1: Video Input
        with st.expander("Step 1: Video Input",
                         expanded=st.session_state.current_step == 1):
            render_step_header(1, "Video Input", "🎥",
                               "分析したいYouTube動画のURLを入力してください")

            youtube_url = st.text_input(
                "YouTube URL",
                placeholder="https://www.youtube.com/watch?v=...",
                help="分析したいYouTube動画のURLを入力してください")

            if youtube_url:
                try:
                    yt_helper = YouTubeHelper()
                    video_info = yt_helper.get_video_info(youtube_url)
                    st.session_state.video_info = video_info
                    st.session_state.current_step = 2
                    update_step_progress('video_info')
                    time.sleep(0.5)
                except Exception as e:
                    st.error(f"動画情報の取得に失敗しました: {str(e)}")
                    logger.error(f"Error in video info retrieval: {str(e)}")
                    st.stop()

        # Step 2: Content Overview
        with st.expander("Step 2: Content Overview",
                         expanded=st.session_state.current_step == 2):
            render_step_header(2, "Content Overview", "📊",
                               "動画の基本情報と文字起こしを表示します")
            if st.session_state.video_info:
                video_info = st.session_state.video_info

                st.markdown(f'''
                <div class="glass-container video-info">
                    <div class="video-grid">
                        <div class="video-thumbnail">
                            <img src="{video_info['thumbnail_url']}" alt="Video thumbnail" style="width: 100%; border-radius: 8px;">
                        </div>
                        <div class="video-details">
                            <h2 class="video-title">{video_info['title']}</h2>
                            <div class="video-stats">
                                <span class="stat-badge">👤 {video_info['channel_title']}</span>
                                <span class="stat-badge">⏱️ {video_info['duration']}</span>
                                <span class="stat-badge">👁️ {video_info['view_count']}回視聴</span>
                            </div>
                            <p class="video-date">📅 投稿日: {video_info['published_at']}</p>
                        </div>
                    </div>
                </div>
                ''',
                            unsafe_allow_html=True)

                if 'transcript' not in st.session_state or not st.session_state.transcript:
                    st.markdown('''
                    <div class="process-step">
                        <div class="step-content">文字起こしを生成します</div>
                    </div>
                    ''',
                                unsafe_allow_html=True)

                    try:
                        text_processor = TextProcessor()
                        transcript = text_processor.get_transcript(youtube_url)
                        st.session_state.transcript = transcript
                        st.session_state.current_step = 3
                        update_step_progress('transcript')
                        time.sleep(0.5)
                    except Exception as e:
                        st.error(f"文字起こしの生成に失敗しました: {str(e)}")
                        logger.error(
                            f"Error in transcript generation: {str(e)}")
                        st.stop()

        # Step 3: Content Analysis
        with st.expander("Step 3: Content Analysis",
                          expanded=st.session_state.current_step == 3):
            render_step_header(3, "Content Analysis", "🔍",
                               "文字起こし、要約、マインドマップを生成します")
            
            if st.session_state.transcript:
                # Content Analysis Tabs
                tabs = st.tabs(["📝 Transcript", "📊 Summary", "🔄 Mind Map", "✨ Proofreading"])
                
                with tabs[0]:  # Transcript Tab
                    st.markdown("#### 📝 文字起こし")
                    st.text_area("Generated Transcript", st.session_state.transcript, height=300)
                
                with tabs[1]:  # Summary Tab
                    st.markdown("#### 📊 要約")
                    if st.session_state.summary:
                        summary_style = st.radio(
                            "要約スタイル",
                            ["概要", "詳細"],
                            horizontal=True,
                            key="summary_style"
                        )
                        st.session_state.current_summary_style = "detailed" if summary_style == "詳細" else "overview"
                        display_summary(st.session_state.summary)
                
                with tabs[2]:  # Mind Map Tab
                    st.markdown("#### 🔄 マインドマップ")
                    if st.session_state.mindmap:
                        st_mermaid(st.session_state.mindmap)
                
                with tabs[3]:  # Proofreading Tab
                    st.markdown("#### ✨ Proofreading")
                    if st.button("文章を校正する"):
                        try:
                            text_processor = TextProcessor()
                            original_text = st.session_state.transcript
                            
                            # Process text in chunks
                            chunks = process_text_in_chunks(original_text)
                            total_chunks = len(chunks)
                            processed_chunks = []
                            
                            progress_bar = st.progress(0)
                            status_text = st.empty()
                            
                            for i, chunk in enumerate(chunks, 1):
                                status_text.text(f"チャンク {i}/{total_chunks} を処理中...")
                                processed_chunk = text_processor.process_chunk(chunk)
                                processed_chunks.append(processed_chunk)
                                progress_bar.progress(i/total_chunks)
                            
                            # Combine processed chunks
                            processed_text = "".join(processed_chunks)
                            
                            # Validate the processed text
                            validate_processed_text(original_text, processed_text)
                            
                            st.session_state.enhanced_text = processed_text
                            st.success("テキストの校正が完了しました！")
                            
                        except Exception as e:
                            st.error(f"テキストの校正中にエラーが発生しました: {str(e)}")

                    # Display enhanced text if available
                    if st.session_state.enhanced_text:
                        st.markdown("#### 校正済みテキスト")
                        st.text_area("校正結果", st.session_state.enhanced_text, height=300)
                # Add style selection with proper label
                summary_style = st.radio(
                    "要約スタイル",
                    options=["detailed", "overview"],
                    format_func=lambda x: {
                        "detailed": "詳細 (より詳しい分析と説明)",
                        "overview": "概要 (簡潔なポイントのみ)"
                    }[x],
                    help="要約の詳細度を選択してください"
                )

                # Initialize text processor outside tabs to ensure proper scope
                if 'text_processor' not in st.session_state:
                    st.session_state.text_processor = TextProcessor()
                
                # Initialize tabs
                tabs = st.tabs([
                    "📝 Transcript", "📊 Summary", "🔄 Mind Map", "✨ Proofreading"
                ])

                def process_text_in_chunks(text, chunk_size=2000, overlap=200):
                    """Process text in chunks with overlap"""
                    chunks = []
                    start = 0
                    text_length = len(text)
                    
                    while start < text_length:
                        end = start + chunk_size
                        # If this is not the last chunk, find a good breaking point
                        if end < text_length:
                            # Try to find sentence end
                            while end < text_length and text[end] not in '.。!！?？':
                                end += 1
                            end += 1  # Include the punctuation mark
                        else:
                            end = text_length
                            
                        chunk = text[start:end]
                        chunks.append(chunk)
                        
                        # Move start position for next chunk, accounting for overlap
                        start = end - overlap
                        # Ensure we find a good starting point
                        while start < text_length and text[start] not in '.。!！?？':
                            start += 1
                        start += 1  # Start after the punctuation mark
                    
                    return chunks

                def validate_processed_text(original_text, processed_text):
                    """Validate the processed text length and content"""
                    original_length = len(original_text)
                    processed_length = len(processed_text)
                    
                    # Allow for small variations (within 10% difference)
                    length_difference = abs(original_length - processed_length)
                    max_allowed_difference = original_length * 0.1
                    
                    if length_difference > max_allowed_difference:
                        raise ValueError(f"""チャンク 1 の校正に失敗しました:
- 期待される文字数: {original_length}
- 実際の文字数: {processed_length}
- 不足文字数: {abs(original_length - processed_length)}""")
                    
                    return True

                # Process tabs content
                with tabs[0]:
                    st.markdown("### Original Transcript")
                    copy_text_block(st.session_state.transcript)

                with tabs[1]:
                    if ('summary' not in st.session_state or 
                        not st.session_state.summary or
                        st.session_state.current_summary_style != summary_style):
                        try:
                            summary, quality_scores = st.session_state.text_processor.generate_summary(
                                st.session_state.transcript, summary_style)
                            st.session_state.summary = summary
                            st.session_state.quality_scores = quality_scores
                            st.session_state.current_summary_style = summary_style
                            update_step_progress('summary')
                        except Exception as e:
                            st.error(f"要約の生成に失敗しました: {str(e)}")
                            logger.error(f"Error in summary generation: {str(e)}")
                    
                    if st.session_state.summary:
                        display_summary(st.session_state.summary)

                with tabs[2]:
                    st.markdown("### 🔄 Mind Map")
                    if not st.session_state.summary:
                        st.info("マインドマップを生成するには、まず要約を生成してください。")
                    else:
                        try:
                            logger.info("Starting mindmap generation process")
                            mindmap_generator = MindMapGenerator()
                            mindmap_content, success = mindmap_generator.generate_mindmap(st.session_state.summary)
                            if success:
                                st.session_state.mindmap = mindmap_content
                                logger.info("マインドマップを生成し、セッションに保存しました")
                                update_step_progress('mindmap')
                            else:
                                st.error("マインドマップの生成に失敗しました")
                        except Exception as e:
                            st.error(f"マインドマップの生成中にエラーが発生しました: {str(e)}")
                            logger.error(f"Error in mindmap generation: {str(e)}")

                        if st.session_state.mindmap:
                            try:
                                st_mermaid(st.session_state.mindmap)
                            except Exception as e:
                                st.error(f"マインドマップの表示中にエラーが発生しました: {str(e)}")
                                logger.error(f"Error displaying mindmap: {str(e)}")

                with tabs[3]:
                    st.markdown("#### ✨ テキストの校正")
                    if st.session_state.transcript:
                        try:
                            # Process text in chunks
                            chunks = process_text_in_chunks(st.session_state.transcript)
                            total_chunks = len(chunks)
                            proofread_chunks = []

                            progress_bar = st.progress(0)
                            status_text = st.empty()

                            for i, chunk in enumerate(chunks):
                                status_text.text(f"チャンク {i+1}/{total_chunks} を処理中...")
                                try:
                                    # Validate and process the chunk
                                    validate_processed_text(chunk, chunk)
                                    proofread_chunks.append(chunk)
                                    progress_bar.progress((i + 1) / total_chunks)
                                except ValueError as e:
                                    st.error(str(e))
                                    logger.error(f"Error in text proofreading: {str(e)}")
                                    break

                            if len(proofread_chunks) == total_chunks:
                                proofread_text = "".join(proofread_chunks)
                                st.session_state.proofread_text = proofread_text
                                st.markdown("### 校正済みテキスト")
                                st.markdown(proofread_text)
                                update_step_progress('proofread')

                        except Exception as e:
                            st.error(f"テキストの校正中にエラーが発生しました: {str(e)}")
                            logger.error(f"Error in text proofreading: {str(e)}")

                st.session_state.current_step = 4

    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
        logger.error(f"Application error: {str(e)}", exc_info=True)

except Exception as e:
    st.error(f"Fatal error: {str(e)}")
    logger.error(f"Fatal application error: {str(e)}", exc_info=True)
                        if end < text_length:
                            # Try to find sentence end
                            while end < text_length and text[end] not in '.。!！?？':
                                end += 1
                            end += 1  # Include the punctuation mark
                        else:
                            end = text_length
                            
                        chunk = text[start:end]
                        chunks.append(chunk)
                        
                        # Move start position for next chunk, accounting for overlap
                        start = end - overlap
                        # Ensure we find a good starting point
                        while start < text_length and text[start] not in '.。!！?？':
                            start += 1
                        start += 1  # Start after the punctuation mark
                    
                    return chunks

                def validate_processed_text(original_text, processed_text):
                    """Validate the processed text length and content"""
                    original_length = len(original_text)
                    processed_length = len(processed_text)
                    
                    # Allow for small variations (within 10% difference)
                    length_difference = abs(original_length - processed_length)
                    max_allowed_difference = original_length * 0.1
                    
                    if length_difference > max_allowed_difference:
                        raise ValueError(f"""チャンク 1 の校正に失敗しました:
- 期待される文字数: {original_length}
- 実際の文字数: {processed_length}
- 不足文字数: {abs(original_length - processed_length)}""")
                    
                    return True

                with tabs[0]:
                    st.markdown("### Original Transcript")
                    copy_text_block(st.session_state.transcript)

                with tabs[1]:
                    if ('summary' not in st.session_state or 
                        not st.session_state.summary or
                        st.session_state.current_summary_style != summary_style):
                        try:
                            summary, quality_scores = st.session_state.text_processor.generate_summary(
                                st.session_state.transcript, summary_style)
                            st.session_state.summary = summary
                            st.session_state.quality_scores = quality_scores
                            st.session_state.current_summary_style = summary_style
                            update_step_progress('summary')
                        except Exception as e:
                            st.error(f"要約の生成に失敗しました: {str(e)}")
                            logger.error(f"Error in summary generation: {str(e)}")
                    
                    if st.session_state.summary:
                        display_summary(st.session_state.summary)

                with tabs[2]:
                    st.markdown("### 🔄 Mind Map")
                    if not st.session_state.summary:
                        st.info("マインドマップを生成するには、まず要約を生成してください。")
                    else:
                        generate_mindmap = st.button("マインドマップ生成")
                        if generate_mindmap:
                            st.markdown("### マインドマップを生成中...")
                            try:
                                logger.info("Starting mindmap generation process")
                                mindmap_generator = MindMapGenerator()
                                mindmap_content, success = mindmap_generator.generate_mindmap(st.session_state.summary)
                                if success:
                                    st.session_state.mindmap = mindmap_content
                                    logger.info("マインドマップを生成し、セッションに保存しました")
                                    update_step_progress('mindmap')
                                else:
                                    st.error("マインドマップの生成に失敗しました")
                            except Exception as e:
                                st.error(f"マインドマップの生成中にエラーが発生しました: {str(e)}")
                                logger.error(f"Error in mindmap generation: {str(e)}")

                        if st.session_state.mindmap:
                            try:
                                st_mermaid(st.session_state.mindmap)
                            except Exception as e:
                                st.error(f"マインドマップの表示中にエラーが発生しました: {str(e)}")
                                logger.error(f"Error displaying mindmap: {str(e)}")

                with tabs[3]:
                    st.markdown("#### ✨ テキストの校正")
                    if st.session_state.transcript:
                        try:
                            # Process text in chunks
                            chunks = process_text_in_chunks(st.session_state.transcript)
                            total_chunks = len(chunks)
                            proofread_chunks = []

                            progress_bar = st.progress(0)
                            status_text = st.empty()

                            for i, chunk in enumerate(chunks):
                                status_text.text(f"チャンク {i+1}/{total_chunks} を処理中...")
                                try:
                                    # Here we would typically call the proofreading API
                                    validate_processed_text(chunk, chunk)
                                    proofread_chunks.append(chunk)
                                    progress_bar.progress((i + 1) / total_chunks)
                                except ValueError as e:
                                    st.error(str(e))
                                    logger.error(f"Error in text proofreading: {str(e)}")
                                    break

                            if len(proofread_chunks) == total_chunks:
                                proofread_text = "".join(proofread_chunks)
                                st.session_state.proofread_text = proofread_text
                                st.markdown("### 校正済みテキスト")
                                st.markdown(proofread_text)
                                update_step_progress('proofread')
                                    
                                    for chunk_idx, chunk in enumerate(text_chunks, 1):
                                        st.markdown(f"チャンク {chunk_idx}/{total_chunks} を処理中...")
                                        
                                        proofread_prompt = f"""
                                        以下のテキストを校正し、より読みやすく、正確な日本語に修正してください。

                                        最重要要件（必須）:
                                        1. テキスト文字数の厳密な維持:
                                           - 入力文字数: {len(chunk)}文字
                                           - 必要出力文字数: {len(chunk)}文字以上
                                           - 許容範囲: 入力文字数の80-120%
                                        
                                        2. 内容の完全性:
                                           - すべての情報を完全に保持
                                           - 省略・要約は厳禁
                                           - 文脈と意味の維持を保証
                                        
                                        3. 文章品質の向上:
                                           - 句読点の最適化
                                           - 漢字/かなの適切な使用
                                           - 文の構造改善
                                           - 表現の一貫性維持
                                        
                                        処理情報:
                                        - チャンク番号: {chunk_idx}/{total_chunks}
                                        - 要求される最小文字数: {int(len(chunk) * 0.8)}
                                        - 推奨文字数範囲: {int(len(chunk) * 0.8)}-{int(len(chunk) * 1.2)}
                                        
                                        元のテキスト:
                                        {chunk}
                                        
                                        応答要件:
                                        1. 校正済みテキストのみを返信
                                        2. 完全性の明示的な確認
                                        3. 文字数要件の厳守
                                        """
                                        
                                        response = st.session_state.text_processor.model.generate_content(proofread_prompt)
                                        proofread_chunk = response.text.strip()
                                        
                                        # Validate chunk integrity with retry mechanism
                                        max_retries = 3
                                        retry_count = 0
                                        
                                        while len(proofread_chunk) < len(chunk) * 0.8 and retry_count < max_retries:
                                            st.markdown(f"チャンク {chunk_idx} を再処理中... (試行 {retry_count + 1}/{max_retries})")
                                            response = st.session_state.text_processor.model.generate_content(proofread_prompt)
                                            proofread_chunk = response.text.strip()
                                            retry_count += 1
                                        
                                        if len(proofread_chunk) < len(chunk) * 0.8:
                                            actual_length = len(proofread_chunk)
                                            expected_length = len(chunk)
                                            raise ValueError(
                                                f"チャンク {chunk_idx} の校正に失敗しました:\n"
                                                f"- 期待される文字数: {expected_length}\n"
                                                f"- 実際の文字数: {actual_length}\n"
                                                f"- 不足文字数: {expected_length - actual_length}"
                                            )
                                        
                                        # Validate key content preservation
                                        original_keywords = set(re.findall(r'[一-龯]{2,}', chunk))
                                        proofread_keywords = set(re.findall(r'[一-龯]{2,}', proofread_chunk))
                                        if len(original_keywords - proofread_keywords) > len(original_keywords) * 0.2:
                                            raise ValueError(f"チャンク {chunk_idx} で重要な内容が失われています")
                                        
                                        processed_chunks.append(proofread_chunk)
                                    
                                    # Combine processed chunks
                                    proofread_text = "\n".join(processed_chunks)
                                    
                                    # Final validation
                                    if len(proofread_text) < len(st.session_state.transcript) * 0.9:
                                        raise ValueError("校正後の全体テキストが元のテキストより著しく短くなっています")
                                    
                                    st.session_state.enhanced_text = proofread_text
                                    st.session_state.enhanced_text_length = len(proofread_text)
                                    update_step_progress('proofread')
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"テキストの校正中にエラーが発生しました: {str(e)}")
                                    logger.error(f"Error in text proofreading: {str(e)}")

                        if st.session_state.enhanced_text:
                            st.markdown("### ✨ テキスト校正が完了しました！")
                            st.markdown(f"校正前の文字数: {len(st.session_state.transcript)}文字")
                            st.markdown(f"校正後の文字数: {st.session_state.enhanced_text_length}文字")
                            
                            # Chunk text for better display
                            chunk_size = 1000
                            text_chunks = [st.session_state.enhanced_text[i:i+chunk_size] 
                                         for i in range(0, len(st.session_state.enhanced_text), chunk_size)]
                            
                            for i, chunk in enumerate(text_chunks, 1):
                                with st.expander(f"校正済みテキスト - パート{i}/{len(text_chunks)}"):
                                    st.markdown(chunk)
                            
                            st.success("校正が完了しました。上記が校正済みのテキストです。")

    except Exception as e:
        st.error(f"アプリケーションエラー: {str(e)}")
        logger.error(f"Application error: {str(e)}")

except Exception as e:
    st.error(f"初期化エラー: {str(e)}")
    logger.error(f"Initialization error: {str(e)}")