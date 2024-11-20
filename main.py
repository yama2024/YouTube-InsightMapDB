from utils.youtube_helper import YouTubeHelper
from utils.text_processor import TextProcessor
from utils.mindmap_generator import MindMapGenerator
from utils.pdf_generator import PDFGenerator
import streamlit as st
import os
import time
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    from streamlit_mermaid import st_mermaid
except Exception as e:
    logger.error(f"Failed to import streamlit_mermaid: {str(e)}")
    st.error("マインドマップコンポーネントの読み込みに失敗しました")

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

    def render_quality_score(score: float, label: str):
        """品質スコアを視覚的に表示"""
        color = "red" if score < 5 else "orange" if score < 7 else "green"
        st.markdown(f"""
        <div style="margin-bottom: 10px;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span>{label}</span>
                <span style="color: {color}; font-weight: bold;">{score:.1f}</span>
            </div>
            <div style="background: rgba(255,255,255,0.1); border-radius: 10px; height: 10px; width: 100%; overflow: hidden;">
                <div style="background: {color}; width: {score*10}%; height: 100%; transition: width 0.5s ease;"></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

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
                tabs = st.tabs([
                    "📝 Transcript", "📊 Summary", "🔄 Mind Map", "✨ Enhancement"
                ])

                with tabs[0]:
                    st.markdown("### Original Transcript")
                    copy_text_block(st.session_state.transcript)

                with tabs[1]:
                    if 'summary' not in st.session_state or not st.session_state.summary:
                        with st.spinner("AI要約を生成中..."):
                            try:
                                text_processor = TextProcessor()
                                summary, quality_scores = text_processor.generate_summary(
                                    st.session_state.transcript)
                                st.session_state.summary = summary
                                st.session_state.quality_scores = quality_scores
                                update_step_progress('summary')
                                time.sleep(0.5)
                            except Exception as e:
                                st.error(f"AI要約の生成に失敗しました: {str(e)}")
                                logger.error(
                                    f"Error in summary generation: {str(e)}")
                                st.stop()

                    if st.session_state.summary:
                        st.markdown("### AI Summary")
                        st.markdown(st.session_state.summary)
                        
                        # Display quality scores
                        st.markdown("### 要約品質スコア")
                        quality_scores = st.session_state.quality_scores
                        
                        with st.container():
                            st.markdown("""
                            <div style="background: rgba(255,255,255,0.1); border-radius: 15px; padding: 20px; margin: 10px 0;">
                                <h4 style="margin-bottom: 15px;">品質評価指標</h4>
                            """, unsafe_allow_html=True)
                            
                            render_quality_score(quality_scores["構造の完全性"], "構造の完全性")
                            render_quality_score(quality_scores["情報量"], "情報量")
                            render_quality_score(quality_scores["簡潔性"], "簡潔性")
                            st.markdown("<hr style='margin: 15px 0;'>", unsafe_allow_html=True)
                            render_quality_score(quality_scores["総合スコア"], "総合スコア")
                            
                            st.markdown("</div>", unsafe_allow_html=True)

                with tabs[2]:
                    st.markdown("### Mind Map Visualization")

                    if 'mindmap' not in st.session_state or not st.session_state.mindmap:
                        with st.spinner("マインドマップを生成中..."):
                            try:
                                mindmap_gen = MindMapGenerator()
                                mermaid_syntax = mindmap_gen.generate_mindmap(
                                    st.session_state.summary)
                                st.session_state.mindmap = mermaid_syntax
                                st.session_state.current_step = 4
                                update_step_progress('mindmap')
                                time.sleep(0.5)
                            except Exception as e:
                                st.error(f"マインドマップの生成に失敗しました: {str(e)}")
                                logger.error(
                                    f"Error in mindmap generation: {str(e)}")
                                st.stop()

                    if st.session_state.mindmap:
                        col1, col2 = st.columns([2, 1])

                        with col1:
                            st.markdown("### Mind Map")
                            try:
                                st_mermaid(st.session_state.mindmap, height="400px")
                            except Exception as e:
                                st.error("マインドマップの表示に失敗しました。別の形式で表示します。")
                                st.code(st.session_state.mindmap, language="mermaid")

                        with col2:
                            st.markdown("### Mermaid Syntax")
                            st.text_area("",
                                         value=st.session_state.mindmap,
                                         height=200)

                            st.download_button("📥 Download Mermaid Syntax",
                                               data=st.session_state.mindmap,
                                               file_name="mindmap.mmd",
                                               mime="text/plain")

                            if st.button("🔄 マインドマップを再生成"):
                                st.session_state.mindmap = None
                                st.rerun()

                with tabs[3]:
                    st.markdown("### テキスト整形")
                    if st.session_state.mindmap:  # Only show enhancement after mindmap is generated
                        st.markdown('<div class="glass-container">',
                                    unsafe_allow_html=True)
                        st.markdown("#### 元のテキスト")
                        st.markdown(
                            st.session_state.transcript.replace('\n', '  \n'))
                        st.markdown('</div>', unsafe_allow_html=True)

                        if st.button("✨ テキストを整形",
                                     help="AIを使用して文章を校正し、読みやすく整形します"):
                            try:
                                # Create a container for progress tracking
                                progress_container = st.container()
                                with progress_container:
                                    progress_bar = st.progress(0)
                                    status_text = st.empty()
                                
                                text_processor = TextProcessor()
                                enhanced_text = text_processor.enhance_text(st.session_state.transcript)
                                st.session_state.enhanced_text = enhanced_text
                                
                                # Show completion message
                                progress_bar.progress(100)
                                status_text.success("✨ テキストの整形が完了しました！")
                                st.markdown("#### 整形後のテキスト")
                                st.markdown(enhanced_text.replace('\n', '  \n'))
                                
                            except Exception as e:
                                st.error(f"テキストの整形中にエラーが発生しました: {str(e)}")
                                logger.error(f"Error in text enhancement: {str(e)}")

    except Exception as e:
        st.error(f"アプリケーションエラー: {str(e)}")
        logger.error(f"Application error: {str(e)}")

except Exception as e:
    st.error(f"初期化エラー: {str(e)}")
    logger.error(f"Initialization error: {str(e)}")