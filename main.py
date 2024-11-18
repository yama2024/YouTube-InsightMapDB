from utils.youtube_helper import YouTubeHelper
from utils.text_processor import TextProcessor
from utils.mindmap_generator import MindMapGenerator
from utils.pdf_generator import PDFGenerator
import streamlit as st
import os
import time
import logging
from streamlit_mermaid import st_mermaid

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

try:
    # Page configuration
    st.set_page_config(
        page_title="YouTube InsightMap",
        page_icon="🎯",
        layout="wide",
        initial_sidebar_state="collapsed"
    )

    # Load CSS
    def load_css():
        try:
            css_path = os.path.join(
                os.path.dirname(__file__), 'styles', 'custom.css'
            )
            if os.path.exists(css_path):
                with open(css_path) as f:
                    st.markdown(
                        f'<style>{f.read()}</style>',
                        unsafe_allow_html=True
                    )
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

    def check_features_completed():
        """Check if all required features are completed before PDF export"""
        required_features = {
            'video_info': '動画情報',
            'transcript': '文字起こし',
            'summary': '要約',
            'mindmap': 'マインドマップ'
        }
        
        # Check if enhancement was attempted and is complete
        if st.session_state.get('enhanced_text') is not None:
            required_features['proofread'] = 'テキスト整形'
        
        completion_status = {
            feature: st.session_state.steps_completed.get(feature, False)
            for feature in required_features.keys()
        }
        
        return completion_status, required_features

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
                help="分析したいYouTube動画のURLを入力してください"
            )

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
                    "📝 Transcript", "📊 Summary", "🔄 Mind Map", "✨ Enhancement", "📄 Export PDF"
                ])

                with tabs[0]:
                    st.markdown("### Original Transcript")
                    copy_text_block(st.session_state.transcript)

                with tabs[1]:
                    if 'summary' not in st.session_state or not st.session_state.summary:
                        with st.spinner("AI要約を生成中..."):
                            try:
                                text_processor = TextProcessor()
                                summary = text_processor.generate_summary(
                                    st.session_state.transcript)
                                st.session_state.summary = summary
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

                with tabs[2]:
                    st.markdown("### Mind Map Visualization")

                    if 'mindmap' not in st.session_state or not st.session_state.mindmap:
                        with st.spinner("マインドマップを生成中..."):
                            try:
                                mindmap_gen = MindMapGenerator()
                                mermaid_syntax = mindmap_gen.generate_mindmap(
                                    st.session_state.transcript)
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
                            st_mermaid(st.session_state.mindmap,
                                       height="400px")

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
                                    st.markdown(
                                        '<div class="progress-container">',
                                        unsafe_allow_html=True)
                                    progress_bar = st.progress(0)
                                    status_text = st.empty()
                                    # Add stats columns
                                    stats_cols = st.columns(2)

                                    def update_enhancement_progress(
                                            progress: float, message: str):
                                        """Update enhancement progress in session state and UI"""
                                        st.session_state.enhancement_progress = {
                                            'progress': progress,
                                            'message': message
                                        }
                                        progress_bar.progress(progress)
                                        status_text.markdown(
                                            f'<div class="progress-message">{message}</div>',
                                            unsafe_allow_html=True)

                                        # Update stats and completion status
                                        if progress == 1.0 and message.startswith("✨"):
                                            with stats_cols[0]:
                                                st.metric(
                                                    "処理済み文字数",
                                                    f"{len(st.session_state.transcript):,}字"
                                                )
                                            with stats_cols[1]:
                                                st.metric(
                                                    "改善率",
                                                    "100%"
                                                )
                                            # Mark proofread as completed
                                            update_step_progress('proofread', True)

                                    text_processor = TextProcessor()
                                    
                                    # Initial progress update
                                    update_enhancement_progress(0.2,
                                                            "⚙️ テキストを解析中...")
                                    time.sleep(0.5)

                                    # Process the text
                                    update_enhancement_progress(0.4,
                                                            "🔄 テキストを整形中...")
                                    enhanced_text = text_processor.proofread_text(
                                        st.session_state.transcript,
                                        progress_callback=update_enhancement_progress)

                                    if enhanced_text:
                                        st.session_state.enhanced_text = enhanced_text
                                        update_enhancement_progress(
                                            1.0, "✨ テキスト整形が完了しました！")

                                        # Display the enhanced text
                                        st.markdown('<div class="glass-container">',
                                                  unsafe_allow_html=True)
                                        st.markdown("#### 整形後のテキスト")
                                        st.markdown(enhanced_text.replace('\n', '  \n'))
                                        st.markdown('</div>', unsafe_allow_html=True)

                            except Exception as e:
                                st.error(f"テキスト整形中にエラーが発生しました: {str(e)}")
                                logger.error(f"Error in text enhancement: {str(e)}")

                with tabs[4]:
                    st.markdown("### PDF Export")
                    
                    # Check completion status
                    completion_status, required_features = check_features_completed()
                    
                    # If any required feature is not completed, show warning
                    missing_features = [
                        name for feature, name in required_features.items()
                        if not completion_status[feature]
                    ]
                    
                    if missing_features:
                        st.warning(
                            f"PDFエクスポートの前に以下の機能を完了してください: {', '.join(missing_features)}"
                        )
                    else:
                        if st.button("📄 PDFレポートを生成",
                                   help="全ての分析結果をPDFレポートとして出力します"):
                            try:
                                with st.spinner("PDFレポートを生成中..."):
                                    # Progress placeholder
                                    progress_placeholder = st.empty()
                                    status_text = st.empty()
                                    
                                    def update_pdf_progress(stage, message):
                                        """Update PDF generation progress"""
                                        progress = {
                                            'init': 0.2,
                                            'content': 0.4,
                                            'layout': 0.6,
                                            'build': 0.8,
                                            'complete': 1.0
                                        }
                                        with progress_placeholder:
                                            st.progress(progress.get(stage, 0))
                                        status_text.info(message)

                                    # Initialize PDF generator with progress callback
                                    update_pdf_progress('init', '📑 PDFジェネレーターを初期化中...')
                                    pdf_generator = PDFGenerator()
                                    
                                    update_pdf_progress('content', '📝 コンテンツを準備中...')
                                    pdf_data = pdf_generator.create_pdf(
                                        video_info=st.session_state.video_info,
                                        transcript=st.session_state.transcript,
                                        summary=st.session_state.summary,
                                        proofread_text=st.session_state.get('enhanced_text', '')
                                    )
                                    
                                    if pdf_data:
                                        update_pdf_progress('complete', '✨ PDFの生成が完了しました！')
                                        # Clear progress indicators
                                        progress_placeholder.empty()
                                        status_text.empty()
                                        
                                        # Show download button
                                        st.download_button(
                                            "📥 PDFレポートをダウンロード",
                                            data=pdf_data,
                                            file_name="youtube_analysis.pdf",
                                            mime="application/pdf"
                                        )
                                        
                                        # Update completion status
                                        update_step_progress('pdf', True)
                                        st.success("PDFレポートが正常に生成されました！")
                                    
                            except TimeoutError:
                                progress_placeholder.empty()
                                status_text.empty()
                                st.error("PDFの生成がタイムアウトしました。もう一度お試しください。")
                                logger.error("PDF generation timeout")
                            except Exception as e:
                                progress_placeholder.empty()
                                status_text.empty()
                                st.error(f"PDFの生成に失敗しました: {str(e)}")
                                logger.error(f"PDF generation error: {str(e)}")
                            finally:
                                # Ensure progress indicators are cleared
                                try:
                                    progress_placeholder.empty()
                                    status_text.empty()
                                except:
                                    pass

    except Exception as e:
        st.error(f"アプリケーションエラー: {str(e)}")
        logger.error(f"Application error: {str(e)}")

except Exception as e:
    st.error(f"アプリケーション初期化エラー: {str(e)}")
    logger.error(f"Initialization error: {str(e)}")