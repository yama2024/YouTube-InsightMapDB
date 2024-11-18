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
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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
                st.warning("スタイルシートの読み込みに失敗しました。デフォルトのスタイルを使用します。")
        except Exception as e:
            logger.error(f"Error loading CSS: {str(e)}")
            st.error("スタイルの適用中にエラーが発生しました。")

    load_css()

    def show_error_guidance(error_type: str, message: str):
        """Display error message with recovery guidance"""
        error_guidances = {
            'video_info': {
                'title': '動画情報の取得に失敗しました',
                'guidance': [
                    '• URLが正しく入力されているか確認してください',
                    '• 動画が非公開になっていないか確認してください',
                    '• インターネット接続を確認してください'
                ]
            },
            'transcript': {
                'title': '文字起こしの取得に失敗しました',
                'guidance': [
                    '• 動画に字幕が設定されているか確認してください',
                    '• 別の動画を試してみてください',
                    '• しばらく待ってから再度お試しください'
                ]
            },
            'api': {
                'title': 'API処理中にエラーが発生しました',
                'guidance': [
                    '• しばらく待ってから再度お試しください',
                    '• 入力内容が適切か確認してください',
                    '• 管理者に連絡してください'
                ]
            }
        }

        guidance = error_guidances.get(error_type, {
            'title': 'エラーが発生しました',
            'guidance': ['• しばらく待ってから再度お試しください']
        })

        st.error(f"""### {guidance['title']}
**エラー詳細:** {message}

#### 解決方法:
{chr(10).join(guidance['guidance'])}""")

    def copy_text_block(text, label=""):
        try:
            if label:
                st.markdown(f"#### {label}")
            st.markdown(text, unsafe_allow_html=False)
            st.markdown("""
            <div class="copy-text-button">
                <button onclick="navigator.clipboard.writeText(document.querySelector('.copy-text-content').innerText)">
                    📋 Copy Text
                </button>
            </div>
            """, unsafe_allow_html=True)
        except Exception as e:
            logger.error(f"Error in copy_text_block: {str(e)}")
            st.warning("テキストの表示中にエラーが発生しました。")

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
    if 'error_count' not in st.session_state:
        st.session_state.error_count = 0

    def update_step_progress(step_name: str, completed: bool = True):
        """Update the completion status of a processing step"""
        try:
            st.session_state.steps_completed[step_name] = completed
            if completed:
                st.success(f"✅ {step_name.replace('_', ' ').title()}の処理が完了しました")
        except Exception as e:
            logger.error(f"Error updating step progress: {str(e)}")
            st.warning("進捗状況の更新中にエラーが発生しました")

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
            st.warning("ステップヘッダーの表示中にエラーが発生しました")

    # Progress tracking container
    progress_container = st.container()
    with progress_container:
        if st.session_state.error_count > 0:
            st.warning(f"⚠️ 処理中に{st.session_state.error_count}件のエラーが発生しています")
        
        progress = sum(st.session_state.steps_completed.values()) / len(st.session_state.steps_completed)
        st.progress(progress)
        st.markdown(f"### 現在の進捗: {progress * 100:.0f}%")

    # Main application logic with enhanced error handling
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
                    with st.spinner("動画情報を取得中..."):
                        yt_helper = YouTubeHelper()
                        video_info = yt_helper.get_video_info(youtube_url)
                        st.session_state.video_info = video_info
                        st.session_state.current_step = 2
                        update_step_progress('video_info')
                        time.sleep(0.5)
                except Exception as e:
                    logger.error(f"Error in video info retrieval: {str(e)}")
                    show_error_guidance('video_info', str(e))
                    st.session_state.error_count += 1
                    st.stop()

        # Step 2: Content Overview
        with st.expander("Step 2: Content Overview",
                         expanded=st.session_state.current_step == 2):
            render_step_header(2, "Content Overview", "📊",
                               "動画の基本情報と文字起こしを表示します")
            if st.session_state.video_info:
                try:
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
                            with st.spinner("文字起こしを生成中..."):
                                text_processor = TextProcessor()
                                transcript = text_processor.get_transcript(youtube_url)
                                if not transcript:
                                    raise ValueError("文字起こしの生成に失敗しました")
                                st.session_state.transcript = transcript
                                st.session_state.current_step = 3
                                update_step_progress('transcript')
                                time.sleep(0.5)
                        except Exception as e:
                            logger.error(f"Error in transcript generation: {str(e)}")
                            show_error_guidance('transcript', str(e))
                            st.session_state.error_count += 1
                            st.stop()
                except Exception as e:
                    logger.error(f"Error in content overview: {str(e)}")
                    show_error_guidance('api', str(e))
                    st.session_state.error_count += 1
                    st.stop()

        # Step 3: Content Analysis
        with st.expander("Step 3: Content Analysis",
                         expanded=st.session_state.current_step == 3):
            render_step_header(3, "Content Analysis", "🔍",
                               "文字起こし、要約、マインドマップを生成します")
            if st.session_state.transcript:
                try:
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
                                    summary = text_processor.generate_summary(
                                        st.session_state.transcript)
                                    if not summary:
                                        raise ValueError("要約の生成に失敗しました")
                                    st.session_state.summary = summary
                                    update_step_progress('summary')
                                    time.sleep(0.5)
                                except Exception as e:
                                    logger.error(f"Error in summary generation: {str(e)}")
                                    show_error_guidance('api', str(e))
                                    st.session_state.error_count += 1
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
                                    if not mermaid_syntax:
                                        raise ValueError("マインドマップの生成に失敗しました")
                                    st.session_state.mindmap = mermaid_syntax
                                    st.session_state.current_step = 4
                                    update_step_progress('mindmap')
                                    time.sleep(0.5)
                                except Exception as e:
                                    logger.error(f"Error in mindmap generation: {str(e)}")
                                    show_error_guidance('api', str(e))
                                    st.session_state.error_count += 1
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
                        if st.session_state.mindmap:
                            st.markdown('<div class="glass-container">',
                                        unsafe_allow_html=True)
                            st.markdown("#### 元のテキスト")
                            st.markdown(
                                st.session_state.transcript.replace('\n', '  \n'))
                            st.markdown('</div>', unsafe_allow_html=True)

                            if st.button("✨ テキストを整形",
                                         help="AIを使用して文章を校正し、読みやすく整形します"):
                                try:
                                    progress_container = st.container()
                                    with progress_container:
                                        st.markdown(
                                            '<div class="progress-container">',
                                            unsafe_allow_html=True)
                                        progress_bar = st.progress(0)
                                        status_text = st.empty()
                                        stats_cols = st.columns(2)

                                        def update_enhancement_progress(
                                                progress: float, message: str):
                                            st.session_state.enhancement_progress = {
                                                'progress': progress,
                                                'message': message
                                            }
                                            progress_bar.progress(progress)
                                            status_text.markdown(
                                                f'<div class="progress-message">{message}</div>',
                                                unsafe_allow_html=True)

                                            if progress == 1.0 and message.startswith(
                                                    "✨"):
                                                with stats_cols[0]:
                                                    st.metric(
                                                        "処理済み文字数",
                                                        f"{len(st.session_state.transcript):,}字"
                                                    )
                                                with stats_cols[1]:
                                                    st.metric(
                                                        "処理時間",
                                                        f"{(time.time() - start_time):.1f}秒"
                                                    )

                                        start_time = time.time()
                                        text_processor = TextProcessor()
                                        enhanced_text = text_processor.proofread_text(
                                            st.session_state.transcript,
                                            progress_callback=update_enhancement_progress)

                                        if enhanced_text:
                                            st.session_state.enhanced_text = enhanced_text
                                            update_step_progress('proofread')
                                            st.markdown("#### 整形後のテキスト")
                                            st.markdown(enhanced_text.replace('\n', '  \n'))
                                            st.download_button(
                                                "📥 整形済みテキストをダウンロード",
                                                enhanced_text,
                                                file_name="enhanced_text.txt",
                                                mime="text/plain")
                                except Exception as e:
                                    logger.error(f"Error in text enhancement: {str(e)}")
                                    show_error_guidance('api', str(e))
                                    st.session_state.error_count += 1
                except Exception as e:
                    logger.error(f"Error in content analysis: {str(e)}")
                    show_error_guidance('api', str(e))
                    st.session_state.error_count += 1

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        st.error(f"""
        ### 予期せぬエラーが発生しました
        **エラー詳細:** {str(e)}
        
        アプリケーションを再読み込みしてください。問題が解決しない場合は、管理者にお問い合わせください。
        """)
        st.session_state.error_count += 1

except Exception as e:
    st.error(f"アプリケーションの初期化中にエラーが発生しました: {str(e)}")