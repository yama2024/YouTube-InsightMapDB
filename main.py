import streamlit as st
from utils.youtube_helper import YouTubeHelper
from utils.text_processor import TextProcessor
from utils.mindmap_generator import MindMapGenerator
from utils.pdf_generator import PDFGenerator
import os
import time
from streamlit_mermaid import st_mermaid

# Page configuration
st.set_page_config(
    page_title="YouTube InsightMap",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Load CSS
def load_css():
    css_path = os.path.join(os.path.dirname(__file__), 'styles', 'custom.css')
    if os.path.exists(css_path):
        with open(css_path) as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    else:
        st.error("CSS file not found!")

load_css()

def copy_text_block(text, label=""):
    if label:
        st.markdown(f"#### {label}")
    st.markdown(text, unsafe_allow_html=False)

# Initialize session state
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

def update_progress(step_name):
    st.session_state.steps_completed[step_name] = True

# Application Header
st.markdown('''
<div class="app-header">
    <div class="app-title">YouTube InsightMap</div>
    <div class="app-subtitle">Content Knowledge Visualization</div>
</div>
''', unsafe_allow_html=True)

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
''', unsafe_allow_html=True)

def get_step_status(step_number):
    if st.session_state.current_step > step_number:
        return "completed"
    elif st.session_state.current_step == step_number:
        return "active"
    return ""

def render_step_header(step_number, title, emoji, description=""):
    """Render an enhanced step header with improved typography and visibility"""
    status = get_step_status(step_number)
    
    st.markdown(f'''
    <div class="step-header {status}">
        <div class="step-content">
            <div class="step-title">{emoji} {title}</div>
            {f'<div class="step-description">{description}</div>' if description else ''}
        </div>
    </div>
    ''', unsafe_allow_html=True)

# Step 1: Video Input
with st.expander("Step 1: Video Input", expanded=st.session_state.current_step == 1):
    render_step_header(1, "Video Input", "🎥", "分析したいYouTube動画のURLを入力してください")
    
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
            update_progress('video_info')
            time.sleep(0.5)
        except Exception as e:
            st.error(f"動画情報の取得に失敗しました: {str(e)}")
            st.stop()

# Step 2: Content Overview
with st.expander("Step 2: Content Overview", expanded=st.session_state.current_step == 2):
    render_step_header(2, "Content Overview", "📊", "動画の基本情報と文字起こしを表示します")
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
        ''', unsafe_allow_html=True)

        if 'transcript' not in st.session_state or not st.session_state.transcript:
            st.markdown('''
            <div class="process-step">
                <div class="step-number">1</div>
                <div class="step-content">文字起こしを生成します</div>
            </div>
            ''', unsafe_allow_html=True)
            
            try:
                text_processor = TextProcessor()
                transcript = text_processor.get_transcript(youtube_url)
                st.session_state.transcript = transcript
                st.session_state.current_step = 3
                update_progress('transcript')
                time.sleep(0.5)
            except Exception as e:
                st.error(f"文字起こしの生成に失敗しました: {str(e)}")
                st.stop()

# Step 3: Content Analysis
with st.expander("Step 3: Content Analysis", expanded=st.session_state.current_step == 3):
    render_step_header(3, "Content Analysis", "🔍", "文字起こし、要約、マインドマップを生成します")
    if st.session_state.transcript:
        tabs = st.tabs(["📝 Transcript", "📊 Summary", "🔄 Mind Map"])
        
        with tabs[0]:
            st.markdown("### Original Transcript")
            copy_text_block(st.session_state.transcript)
        
        with tabs[1]:
            if 'summary' not in st.session_state or not st.session_state.summary:
                with st.spinner("AI要約を生成中..."):
                    try:
                        text_processor = TextProcessor()
                        summary = text_processor.generate_summary(st.session_state.transcript)
                        st.session_state.summary = summary
                        update_progress('summary')
                        time.sleep(0.5)
                    except Exception as e:
                        st.error(f"AI要約の生成に失敗しました: {str(e)}")
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
                        mermaid_syntax = mindmap_gen.generate_mindmap(st.session_state.transcript)
                        st.session_state.mindmap = mermaid_syntax
                        st.session_state.current_step = 4
                        update_progress('mindmap')
                        time.sleep(0.5)
                    except Exception as e:
                        st.error(f"マインドマップの生成に失敗しました: {str(e)}")
                        st.stop()
            
            if st.session_state.mindmap:
                # Main content area
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    st.markdown("### Mind Map")
                    st_mermaid(st.session_state.mindmap, height="400px")
                
                with col2:
                    st.markdown("### Mermaid Syntax")
                    st.text_area(
                        "",
                        value=st.session_state.mindmap,
                        height=200
                    )
                    
                    # Download option
                    st.download_button(
                        "📥 Download Mermaid Syntax",
                        data=st.session_state.mindmap,
                        file_name="mindmap.mmd",
                        mime="text/plain"
                    )
                    
                    # Regenerate button
                    if st.button("🔄 マインドマップを再生成"):
                        st.session_state.mindmap = None
                        st.rerun()

# Progress Indicator
progress_percentage = (st.session_state.current_step / 4) * 100
step_names = {
    'video_info': 'Video Information',
    'transcript': 'Transcript Generation',
    'summary': 'Summary Creation',
    'mindmap': 'Mind Map Generation'
}

st.markdown(f'''
<div class="progress-section">
    <h4 class="progress-header">Overall Progress</h4>
    <div class="progress-bar-main">
        <div class="progress-fill" style="width: {progress_percentage}%"></div>
    </div>
    <p class="progress-text">Step {st.session_state.current_step} of 4</p>
</div>
''', unsafe_allow_html=True)

# Detailed Progress Indicators
st.markdown('<div class="detailed-progress">', unsafe_allow_html=True)
for step_key, step_name in step_names.items():
    status = "completed" if st.session_state.steps_completed[step_key] else "pending"
    icon = "✓" if status == "completed" else "○"
    st.markdown(f'''
    <div class="progress-item {status}">
        <span class="progress-icon">{icon}</span>
        <span class="progress-label">{step_name}</span>
    </div>
    ''', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)