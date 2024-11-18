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
    st.markdown(f'''
    <div class="text-display-container">
        <div class="text-area-header">
            {label if label else ""}
        </div>
        <div class="text-content">
            {text}
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
        loading_spinner = show_loading_spinner("動画情報を取得中...", key="video_info")
        try:
            yt_helper = YouTubeHelper()
            video_info = yt_helper.get_video_info(youtube_url)
            st.session_state.video_info = video_info
            st.session_state.current_step = 2
            update_progress('video_info')
            time.sleep(0.5)
            loading_spinner.empty()
            show_success_message("動画情報の取得が完了しました", key="video_info_success")
        except Exception as e:
            loading_spinner.empty()
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
            
            loading_dots = show_loading_dots("文字起こしを生成中...", key="transcript")
            try:
                text_processor = TextProcessor()
                transcript = text_processor.get_transcript(youtube_url)
                st.session_state.transcript = transcript
                st.session_state.current_step = 3
                update_progress('transcript')
                time.sleep(0.5)
                loading_dots.empty()
                show_success_message("文字起こしの生成が完了しました", key="transcript_success")
            except Exception as e:
                loading_dots.empty()
                st.error(f"文字起こしの生成に失敗しました: {str(e)}")
                st.stop()

# Step 3: Content Analysis
with st.expander("Step 3: Content Analysis", expanded=st.session_state.current_step == 3):
    render_step_header(3, "Content Analysis", "🔍", "文字起こし、要約、マインドマップを生成します")
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
                mindmap_loading = show_loading_spinner("マインドマップを生成中...", key="mindmap")
                try:
                    mermaid_syntax = mindmap_gen.generate_mindmap(st.session_state.transcript)
                    st.session_state.mindmap = mermaid_syntax
                    st.session_state.current_step = 4
                    update_progress('mindmap')
                    time.sleep(0.5)
                    mindmap_loading.empty()
                    show_success_message("マインドマップの生成が完了しました", key="mindmap_success")
                except Exception as e:
                    mindmap_loading.empty()
                    st.error(f"マインドマップの生成に失敗しました: {str(e)}")
                    st.stop()
            
            if st.session_state.mindmap:
                st.markdown("## Mind Map Visualization")
                
                # Display debug information in an expander
                with st.expander("Debug Information", expanded=False):
                    st.markdown("### Generated Mermaid Syntax")
                    st.code(st.session_state.mindmap, language="mermaid")
                
                # Add error handling for mindmap rendering
                try:
                    # Validate mindmap syntax
                    if not st.session_state.mindmap.startswith('mindmap'):
                        raise ValueError("Invalid mindmap syntax: Must start with 'mindmap'")
                    
                    # Render mindmap with enhanced error handling
                    st.markdown("### Interactive Mind Map")
                    st_mermaid(
                        st.session_state.mindmap,
                        height="600px",
                        width="100%"
                    )
                    
                    # Add download button for the mindmap syntax
                    st.download_button(
                        label="Download Mermaid Syntax",
                        data=st.session_state.mindmap,
                        file_name="mindmap.mmd",
                        mime="text/plain"
                    )
                    
                except Exception as render_error:
                    st.error(f"マインドマップのレンダリングに失敗しました: {str(render_error)}")
                    st.info("マインドマップの構文を確認して、もう一度生成してください。")
                    
                    # Show retry button
                    if st.button("🔄 マインドマップを再生成", use_container_width=True):
                        st.session_state.mindmap = None
                        st.experimental_rerun()

# Step 4: Enhancement
with st.expander("Step 4: Enhancement", expanded=st.session_state.current_step == 4):
    render_step_header(4, "Enhancement", "✨", "AIによる文章の校閲・整形を行います")
    if st.session_state.transcript and st.session_state.summary:
        st.markdown('''
        <div class="glass-container">
            <h4 class="section-header">Text Enhancement Results</h4>
            <p class="section-description">AIによる文章の校閲・整形を行います</p>
        </div>
        ''', unsafe_allow_html=True)

        # Display text sections with enhanced styling
        st.markdown('''
        <div class="glass-container">
            <div class="text-enhancement-results">
        ''', unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        original_length = len(st.session_state.transcript)
        
        with col1:
            st.markdown("### Original Text")
            st.markdown(f"Character count: {original_length}")
            st.markdown('''
            <div class="scrollable-text-container original">
                <div class="text-content">
            ''', unsafe_allow_html=True)
            st.markdown(st.session_state.transcript)
            st.markdown('</div></div>', unsafe_allow_html=True)
        
        with col2:
            st.markdown("### Enhanced Text")
            if 'proofread_transcript' in st.session_state:
                enhanced_length = len(st.session_state.proofread_transcript)
                length_change = ((enhanced_length - original_length) / original_length * 100)
                st.markdown(f"Character count: {enhanced_length} ({length_change:.1f}% change)")
                st.markdown('''
                <div class="scrollable-text-container enhanced">
                    <div class="text-content">
                ''', unsafe_allow_html=True)
                st.markdown(st.session_state.proofread_transcript)
                st.markdown('</div></div>', unsafe_allow_html=True)
            else:
                st.markdown("Processing not started")
                st.markdown('''
                <div class="scrollable-text-container enhanced" style="opacity: 0.5;">
                    <div class="text-content">
                        テキストの校閲を開始するには、「テキストを校閲」ボタンをクリックしてください。
                    </div>
                </div>
                ''', unsafe_allow_html=True)
        
        st.markdown('</div></div>', unsafe_allow_html=True)
        
        # Add proofread/re-proofread button with proper spacing
        st.markdown('<div style="margin: 1.5rem 0;">', unsafe_allow_html=True)
        if 'proofread_transcript' not in st.session_state:
            if st.button("🔄 テキストを校閲", use_container_width=True, key="proofread_button",
                        help="AIによって文章を校閲・整形します"):
                progress_bar = show_progress_bar("テキストを校閲中...")
                try:
                    text_processor = TextProcessor()
                    proofread_transcript = text_processor.proofread_text(st.session_state.transcript)
                    
                    # Validate the enhanced text
                    enhanced_length = len(proofread_transcript)
                    if enhanced_length < (original_length * 0.5):
                        raise ValueError("校閲後のテキストが極端に短くなっています。処理を中断します。")
                    
                    st.session_state.proofread_transcript = proofread_transcript
                    st.session_state.current_step = 5
                    update_progress('proofread')
                    progress_bar.empty()
                    show_success_message("テキストの校閲が完了しました")
                    st.rerun()
                except Exception as e:
                    progress_bar.empty()
                    st.error(f"テキストの校閲に失敗しました: {str(e)}")

        else:
            if st.button("🔄 校閲をやり直す", use_container_width=True, key="reproofread_button",
                        help="テキストの校閲をもう一度実行します"):
                del st.session_state.proofread_transcript
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

        # Remove redundant code
        st.markdown('</div>', unsafe_allow_html=True)
        
        # Display existing enhanced text if available
        # if 'proofread_transcript' in st.session_state:
        #     st.markdown('''
        #     <div class="glass-container">
        #         <div class="text-enhancement-results">
        #     ''', unsafe_allow_html=True)
            
        #     col1, col2 = st.columns(2)
        #     original_length = len(st.session_state.transcript)
        #     enhanced_length = len(st.session_state.proofread_transcript)
        #     length_change = ((enhanced_length - original_length) / original_length * 100)
            
        #     with col1:
        #         st.markdown("### Original Text")
        #         st.markdown(f"Character count: {original_length}")
        #         st.markdown('''
        #         <div class="scrollable-text-container original">
        #             <div class="text-content">
        #         ''', unsafe_allow_html=True)
        #         st.markdown(st.session_state.transcript)
        #         st.markdown('</div></div>', unsafe_allow_html=True)
            
        #     with col2:
        #         st.markdown("### Enhanced Text")
        #         st.markdown(f"Character count: {enhanced_length}")
        #         st.markdown('''
        #         <div class="scrollable-text-container enhanced">
        #             <div class="text-content">
        #         ''', unsafe_allow_html=True)
        #         st.markdown(st.session_state.proofread_transcript)
        #         st.markdown('</div></div>', unsafe_allow_html=True)
            
        #     # Add comparison stats
        #     st.markdown(f'''
        #     <div class="comparison-stats">
        #         <div class="stat-item">
        #             <span class="stat-label">Length Change:</span>
        #             <span class="stat-value">{length_change:.1f}%</span>
        #         </div>
        #     </div>
        #     ''', unsafe_allow_html=True)
            
        #     st.markdown('</div></div>', unsafe_allow_html=True)
            
        #     # Add re-proofread button
        #     st.markdown('<div style="margin: 1.5rem 0;">', unsafe_allow_html=True)
        #     if st.button("🔄 校閲をやり直す", use_container_width=True, key="reproofread_button",
        #                 help="テキストの校閲をもう一度実行します"):
        #         del st.session_state.proofread_transcript
        #         st.rerun() 
        #     st.markdown('</div>', unsafe_allow_html=True)

# Step 5: Export
with st.expander("Step 5: Export", expanded=st.session_state.current_step == 5):
    render_step_header(5, "Export", "📑", "分析結果をPDFレポートとして出力します")
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