import streamlit as st
from utils.youtube_helper import YouTubeHelper
from utils.text_processor import TextProcessor
from utils.mindmap_generator import MindMapGenerator
from utils.pdf_generator import PDFGenerator
import os
import time

# Page configuration
st.set_page_config(
    page_title="YouTube InsightMap",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Load CSS and helper functions
def load_css():
    css_path = os.path.join(os.path.dirname(__file__), 'styles', 'custom.css')
    if os.path.exists(css_path):
        with open(css_path) as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    else:
        st.error("CSS file not found!")

load_css()

# Loading animation helpers
def show_loading_spinner(message, key=None):
    placeholder = st.empty()
    placeholder.markdown(f'''
        <div class="loading-container">
            <div class="loading-spinner"></div>
            <p class="loading-text">{message}</p>
        </div>
    ''', unsafe_allow_html=True)
    return placeholder

def show_loading_dots(message, key=None):
    placeholder = st.empty()
    placeholder.markdown(f'''
        <div class="loading-container">
            <div class="loading-dots">
                <span></span>
                <span></span>
                <span></span>
            </div>
            <p class="loading-text">{message}</p>
        </div>
    ''', unsafe_allow_html=True)
    return placeholder

def show_progress_bar(message, progress_value=None, key=None):
    placeholder = st.empty()
    if progress_value is not None:
        progress_style = f'width: {progress_value * 100}%'
    else:
        progress_style = 'width: 100%; animation: progressBar 2s ease-in-out infinite;'
    
    placeholder.markdown(f'''
        <div class="loading-container">
            <div class="progress-bar">
                <div class="progress-bar-fill" style="{progress_style}"></div>
            </div>
            <p class="loading-text">{message}</p>
        </div>
    ''', unsafe_allow_html=True)
    return placeholder

def show_shimmer_loading(message, key=None):
    placeholder = st.empty()
    placeholder.markdown(f'''
        <div class="loading-container">
            <div class="shimmer-wrapper">
                <div class="shimmer-text">{message}</div>
            </div>
        </div>
    ''', unsafe_allow_html=True)
    return placeholder

def show_success_message(message, key=None):
    placeholder = st.empty()
    placeholder.markdown(f'''
        <div class="success-message">
            <div class="success-icon">✓</div>
            <p class="success-text">{message}</p>
        </div>
    ''', unsafe_allow_html=True)
    return placeholder

def copy_text_block(text, label=""):
    col1, col2 = st.columns([5, 1])
    with col1:
        st.text_area(
            label=label,
            value=text,
            height=300,
            disabled=True
        )
    with col2:
        st.code(text, language="text")
        st.markdown("↑ テキストを選択してコピー")

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
if 'pdf_data' not in st.session_state:
    st.session_state.pdf_data = None

def update_progress(step_name):
    st.session_state.steps_completed[step_name] = True

# Step 1: Video Input
with st.expander("Step 1: Video Input 🎥", expanded=st.session_state.current_step == 1):
    st.markdown('''
    <div class="section-description">分析したいYouTube動画のURLを入力してください</div>
    ''', unsafe_allow_html=True)
    
    youtube_url = st.text_input(
        "YouTube URL",
        placeholder="https://www.youtube.com/watch?v=...",
        help="分析したいYouTube動画のURLを入力してください"
    )

    if youtube_url:
        try:
            loading_spinner = show_loading_spinner("動画情報を取得中...", key="video_info")
            yt_helper = YouTubeHelper()
            video_info = yt_helper.get_video_info(youtube_url)
            st.session_state.video_info = video_info
            st.session_state.current_step = 2
            update_progress('video_info')
            time.sleep(0.5)
            loading_spinner.empty()
            show_success_message("動画情報の取得が完了しました", key="video_info_success")
        except Exception as e:
            if 'loading_spinner' in locals():
                loading_spinner.empty()
            st.error(f"動画情報の取得に失敗しました: {str(e)}")
            st.stop()

# Step 2: Content Overview
with st.expander("Step 2: Content Overview 📊", expanded=st.session_state.current_step == 2):
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
            
            text_processor = TextProcessor()
            loading_dots = show_loading_dots("文字起こしを生成中...", key="transcript")
            try:
                transcript = text_processor.get_transcript(youtube_url)
                st.session_state.transcript = transcript
                st.session_state.current_step = 3
                update_progress('transcript')
                time.sleep(0.5)
                loading_dots.empty()
                show_success_message("文字起こしの生成が完了しました", key="transcript_success")
            except Exception as e:
                if 'loading_dots' in locals():
                    loading_dots.empty()
                st.error(f"文字起こしの生成に失敗しました: {str(e)}")
                st.stop()

# Step 3: Content Analysis
with st.expander("Step 3: Content Analysis 🔍", expanded=st.session_state.current_step == 3):
    if st.session_state.transcript:
        tabs = st.tabs(["📝 Transcript", "📊 Summary", "🔄 Mind Map"])
        
        with tabs[0]:
            st.markdown('<h5 class="subsection-header">Original Transcript</h5>', unsafe_allow_html=True)
            copy_text_block(st.session_state.transcript, "文字起こしテキスト")
        
        with tabs[1]:
            if 'summary' not in st.session_state or not st.session_state.summary:
                shimmer_loading = show_shimmer_loading("AI要約を生成中...", key="summary")
                try:
                    text_processor = TextProcessor()
                    summary = text_processor.generate_summary(st.session_state.transcript)
                    st.session_state.summary = summary
                    update_progress('summary')
                    time.sleep(0.5)
                    shimmer_loading.empty()
                    show_success_message("AI要約の生成が完了しました", key="summary_success")
                except Exception as e:
                    if 'shimmer_loading' in locals():
                        shimmer_loading.empty()
                    st.error(f"AI要約の生成に失敗しました: {str(e)}")
                    st.stop()
            
            if st.session_state.summary:
                st.markdown('<h5 class="subsection-header">AI Summary</h5>', unsafe_allow_html=True)
                copy_text_block(st.session_state.summary, "AI要約")
        
        with tabs[2]:
            if 'mindmap' not in st.session_state or not st.session_state.mindmap:
                st.markdown('<h5 class="subsection-header">Mind Map Visualization</h5>', unsafe_allow_html=True)
                mindmap_gen = MindMapGenerator()
                loading_container = show_loading_spinner("マインドマップを生成中...", key="mindmap")
                try:
                    mindmap_data = mindmap_gen.generate_mindmap(st.session_state.transcript)
                    fig = mindmap_gen.create_visualization(mindmap_data)
                    fig.update_layout(
                        plot_bgcolor='rgba(0,0,0,0)',
                        paper_bgcolor='rgba(0,0,0,0)',
                        font=dict(color='white'),
                    )
                    st.session_state.mindmap = fig
                    st.session_state.current_step = 4
                    update_progress('mindmap')
                    time.sleep(0.5)
                    loading_container.empty()
                    show_success_message("マインドマップの生成が完了しました", key="mindmap_success")
                except Exception as e:
                    if 'loading_container' in locals():
                        loading_container.empty()
                    st.error(f"マインドマップの生成に失敗しました: {str(e)}")
                    st.stop()
            
            if st.session_state.mindmap:
                st.plotly_chart(st.session_state.mindmap, use_container_width=True)

# Step 4: Enhancement
with st.expander("Step 4: Enhancement ✨", expanded=st.session_state.current_step == 4):
    if st.session_state.transcript and st.session_state.summary:
        st.markdown('<h5 class="subsection-header">✨ Text Enhancement</h5>', unsafe_allow_html=True)
                
        if 'proofread_transcript' not in st.session_state:
            if st.button("校閲して整形する", use_container_width=True, key="proofread_button"):
                progress_bar = show_progress_bar("テキストを校閲中...", key="proofread")
                try:
                    text_processor = TextProcessor()
                    proofread_transcript = text_processor.proofread_text(st.session_state.transcript)
                    
                    st.markdown("### Text Enhancement Results")
                    st.markdown("校閲・整形された結果を表示します")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("**元のテキスト**")
                        copy_text_block(st.session_state.transcript)
                    
                    with col2:
                        st.markdown("**校閲後のテキスト**")
                        copy_text_block(proofread_transcript)
                    
                    st.session_state.proofread_transcript = proofread_transcript
                    st.session_state.current_step = 5
                    update_progress('proofread')
                    time.sleep(0.5)
                    progress_bar.empty()
                    show_success_message("テキストの校閲が完了しました", key="proofread_success")
                except Exception as e:
                    if 'progress_bar' in locals():
                        progress_bar.empty()
                    st.error(f"テキストの校閲に失敗しました: {str(e)}")
        else:
            st.markdown("### Text Enhancement Results")
            st.markdown("校閲・整形された結果を表示します")
            
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**元のテキスト**")
                copy_text_block(st.session_state.transcript)
            
            with col2:
                st.markdown("**校閲後のテキスト**")
                copy_text_block(st.session_state.proofread_transcript)
            
            if st.button("校閲をやり直す", use_container_width=True, key="reproofread_button"):
                del st.session_state.proofread_transcript
                st.rerun()

# Step 5: Export
with st.expander("Step 5: Export 📑", expanded=st.session_state.current_step == 5):
    if st.session_state.transcript and st.session_state.summary:
        st.markdown('<h5 class="subsection-header">📥 Export Report</h5>', unsafe_allow_html=True)
        if st.button("PDFレポートを生成", use_container_width=True, key="generate_pdf"):
            progress_container = show_loading_dots("PDFレポートを生成中...", key="pdf")
            try:
                pdf_gen = PDFGenerator()
                pdf_data = pdf_gen.create_pdf(
                    video_info=st.session_state.video_info,
                    transcript=st.session_state.transcript,
                    summary=st.session_state.summary,
                    proofread_text=st.session_state.get('proofread_transcript', '')
                )
                st.session_state.pdf_data = pdf_data
                update_progress('pdf')
                time.sleep(0.5)
                progress_container.empty()
                show_success_message("PDFレポートの生成が完了しました", key="pdf_success")
            except Exception as e:
                if 'progress_container' in locals():
                    progress_container.empty()
                st.error(f"PDFレポートの生成に失敗しました: {str(e)}")
        
        if st.session_state.pdf_data and st.session_state.video_info:
            st.download_button(
                label="📥 Download PDF Report",
                data=st.session_state.pdf_data,
                file_name=f"{st.session_state.video_info['title']}_分析レポート.pdf",
                mime="application/pdf",
                use_container_width=True
            )

# Progress Indicator
progress_percentage = (st.session_state.current_step / 5) * 100
step_names = {
    'video_info': 'Video Information',
    'transcript': 'Transcript Generation',
    'summary': 'Summary Creation',
    'mindmap': 'Mind Map Generation',
    'proofread': 'Text Enhancement',
    'pdf': 'PDF Export'
}

st.markdown('''
<div class="progress-section">
    <h4 class="progress-header">Overall Progress</h4>
    <div class="progress-bar-main">
        <div class="progress-fill" style="width: {}%"></div>
    </div>
    <p class="progress-text">Step {} of 5</p>
</div>
'''.format(progress_percentage, st.session_state.current_step), unsafe_allow_html=True)

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