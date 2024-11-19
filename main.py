import streamlit as st
import os
import time
import logging
from utils.youtube_helper import YouTubeHelper
from utils.text_processor import TextProcessor
from utils.mindmap_generator import MindMapGenerator
from utils.pdf_generator import PDFGenerator
from streamlit_mermaid import st_mermaid
from typing import Optional
import json

# Set up logging with enhanced format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s')
logger = logging.getLogger(__name__)

# Initialize session state with enhanced error handling
if 'initialized' not in st.session_state:
    st.session_state.initialized = False
    st.session_state.connection_status = {
        'last_error': None,
        'retry_count': 0,
        'last_retry': time.time(),
        'connected': False
    }

def handle_connection_error(error: Optional[str] = None):
    """Enhanced connection error handling with status tracking"""
    current_time = time.time()
    
    # Update connection status
    if error:
        st.session_state.connection_status['last_error'] = error
    
    # Reset retry count if enough time has passed
    if current_time - st.session_state.connection_status['last_retry'] > 60:
        st.session_state.connection_status['retry_count'] = 0
    
    # Implement exponential backoff
    if st.session_state.connection_status['retry_count'] < 5:
        st.session_state.connection_status['retry_count'] += 1
        backoff = min(30, 2 ** st.session_state.connection_status['retry_count'])
        st.session_state.connection_status['last_retry'] = current_time
        time.sleep(backoff)
        st.rerun()  # Using st.rerun() instead of experimental_rerun
    else:
        st.error("接続エラーが発生しています。ページを更新してください。")
        logger.error(f"Connection error: {error}")

def initialize_session_state():
    """Initialize or reset session state with proper error handling"""
    try:
        if not st.session_state.initialized:
            st.session_state.video_info = None
            st.session_state.transcript = None
            st.session_state.summary = None
            st.session_state.mindmap = None
            st.session_state.pdf_data = None
            st.session_state.processing_status = {
                'video_info': False,
                'transcript': False,
                'summary': False,
                'mindmap': False
            }
            st.session_state.initialized = True
            logger.info("Session state initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing session state: {str(e)}")
        handle_connection_error(str(e))

def load_css():
    """Load custom CSS with enhanced error handling"""
    try:
        css_path = os.path.join(os.path.dirname(__file__), 'styles', 'custom.css')
        if os.path.exists(css_path):
            with open(css_path) as f:
                st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
                logger.info("CSS loaded successfully")
        else:
            logger.warning("CSS file not found")
            st.warning("スタイルシートの読み込みに失敗しました")
    except Exception as e:
        logger.error(f"Error loading CSS: {str(e)}")
        st.warning("スタイルの適用中にエラーが発生しました")

try:
    # Initialize session state
    initialize_session_state()
    
    # Load CSS
    load_css()

    # Application Header
    st.markdown('''
    <div class="app-header">
        <div class="app-title">YouTube InsightMap</div>
        <div class="app-subtitle">Content Knowledge Visualization</div>
    </div>
    ''', unsafe_allow_html=True)

    # Video URL input with validation
    youtube_url = st.text_input(
        "YouTube URL",
        placeholder="https://www.youtube.com/watch?v=...",
        help="分析したいYouTube動画のURLを入力してください"
    )

    if youtube_url:
        try:
            # Process video information
            if not st.session_state.video_info:
                with st.spinner("動画情報を取得中..."):
                    yt_helper = YouTubeHelper()
                    video_info = yt_helper.get_video_info(youtube_url)
                    st.session_state.video_info = video_info
                    st.session_state.processing_status['video_info'] = True

            # Display video information
            if st.session_state.video_info:
                video_info = st.session_state.video_info
                st.markdown(f'''
                <div class="glass-container">
                    <div class="video-grid">
                        <img src="{video_info['thumbnail_url']}" alt="サムネイル" class="video-thumbnail">
                        <div class="video-details">
                            <div class="video-title">{video_info['title']}</div>
                            <div class="video-stats">
                                <span class="stat-badge">👤 {video_info['channel_title']}</span>
                                <span class="stat-badge">⏱️ {video_info['duration']}</span>
                                <span class="stat-badge">👁️ {video_info['view_count']}</span>
                            </div>
                        </div>
                    </div>
                </div>
                ''', unsafe_allow_html=True)

                # Analysis button with progress tracking
                if st.button("コンテンツを分析", type="primary"):
                    text_processor = TextProcessor()
                    
                    # Process transcript
                    if not st.session_state.transcript:
                        try:
                            with st.spinner("文字起こしを生成中..."):
                                transcript = text_processor.get_transcript(youtube_url)
                                st.session_state.transcript = transcript
                                st.session_state.processing_status['transcript'] = True
                        except Exception as e:
                            logger.error(f"Transcript generation error: {str(e)}")
                            st.error(f"文字起こしの生成に失敗しました: {str(e)}")
                    
                    # Process summary with progress tracking
                    if st.session_state.transcript and not st.session_state.summary:
                        try:
                            progress_bar = st.progress(0)
                            with st.spinner("AI要約を生成中..."):
                                summary = text_processor.generate_summary(
                                    st.session_state.transcript,
                                    lambda p, m: progress_bar.progress(p)
                                )
                                st.session_state.summary = summary
                                st.session_state.processing_status['summary'] = True
                                progress_bar.progress(1.0)
                        except Exception as e:
                            logger.error(f"Summary generation error: {str(e)}")
                            st.error(f"要約の生成に失敗しました: {str(e)}")
                    
                    # Generate mindmap with error handling
                    if st.session_state.summary and not st.session_state.mindmap:
                        try:
                            with st.spinner("マインドマップを生成中..."):
                                mindmap_gen = MindMapGenerator()
                                mindmap = mindmap_gen.generate_mindmap(st.session_state.summary)
                                st.session_state.mindmap = mindmap
                                st.session_state.processing_status['mindmap'] = True
                        except Exception as e:
                            logger.error(f"Mindmap generation error: {str(e)}")
                            st.error(f"マインドマップの生成に失敗しました: {str(e)}")

                # Display results in tabs with error handling
                if any([st.session_state.transcript, st.session_state.summary, st.session_state.mindmap]):
                    try:
                        tabs = st.tabs(["📝 文字起こし", "📊 要約", "🔄 マインドマップ"])
                        
                        with tabs[0]:
                            if st.session_state.transcript:
                                st.text_area("文字起こし", value=st.session_state.transcript, height=300)
                        
                        with tabs[1]:
                            if st.session_state.summary:
                                st.markdown(st.session_state.summary)
                        
                        with tabs[2]:
                            if st.session_state.mindmap:
                                st_mermaid(st.session_state.mindmap, height="400px")

                        # Show processing status in sidebar
                        st.sidebar.markdown("### 処理状況")
                        for step, status in st.session_state.processing_status.items():
                            icon = "✅" if status else "⏳"
                            st.sidebar.markdown(f"{icon} {step}")
                    except Exception as e:
                        logger.error(f"Error displaying results: {str(e)}")
                        st.error("結果の表示中にエラーが発生しました。ページを更新してください。")

        except Exception as e:
            logger.error(f"Application error: {str(e)}")
            handle_connection_error(str(e))

except Exception as e:
    logger.error(f"Critical application error: {str(e)}")
    st.error(f"アプリケーションエラーが発生しました: {str(e)}")
