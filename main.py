import streamlit as st
from utils.youtube_helper import YouTubeHelper
from utils.text_processor import TextProcessor
from utils.mindmap_generator import MindMapGenerator
from utils.pdf_generator import PDFGenerator
import os

# ページ設定
st.set_page_config(
    page_title="YouTube InsightMap",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# カスタムCSSの読み込み
css_path = 'styles/custom.css'
if os.path.exists(css_path):
    with open(css_path) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

# アプリヘッダー
st.markdown('''
<div class="app-title">YouTube InsightMap</div>
<div class="app-subtitle">Content Knowledge Visualization</div>
''', unsafe_allow_html=True)

# 機能紹介セクション
st.markdown('''
<div class="glass-container feature-container">
    <h4 class="section-header" style="margin-top: 0;">🎯 Deep Content Understanding</h4>
    <p class="feature-description">
        Analyze video content and structure knowledge using AI technology.
    </p>
    <div class="feature-grid">
        <div class="feature-card">
            <h5 class="feature-title">📝 Transcription</h5>
            <p class="feature-text">
                Automatic speech-to-text with high accuracy
            </p>
        </div>
        <div class="feature-card">
            <h5 class="feature-title">🤖 AI Summary</h5>
            <p class="feature-text">
                Extract key points automatically
            </p>
        </div>
        <div class="feature-card">
            <h5 class="feature-title">🔄 Mind Map</h5>
            <p class="feature-text">
                Visualize content structure
            </p>
        </div>
    </div>
</div>
''', unsafe_allow_html=True)

# セッション状態の初期化
if 'pdf_data' not in st.session_state:
    st.session_state.pdf_data = None
if 'video_info' not in st.session_state:
    st.session_state.video_info = None

# URL入力セクション
st.markdown('<h3 class="section-header">🎥 Analyze Video</h3>', unsafe_allow_html=True)

youtube_url = st.text_input(
    "Enter YouTube URL",
    placeholder="https://www.youtube.com/watch?v=...",
    help="Input the URL of the YouTube video you want to analyze"
)

if youtube_url:
    try:
        # YouTube情報の取得
        yt_helper = YouTubeHelper()
        video_info = yt_helper.get_video_info(youtube_url)
        st.session_state.video_info = video_info
        
        # 動画情報セクション
        st.markdown('<h3 class="section-header">📺 Video Information</h3>', unsafe_allow_html=True)
        
        col1, col2 = st.columns([1, 2])
        with col1:
            st.image(video_info['thumbnail_url'], use_column_width=True)
        
        with col2:
            st.markdown(f'''
            <div class="glass-container video-info">
                <h2 class="video-title">{video_info['title']}</h2>
                <div class="video-stats">
                    <span class="stat-badge">👤 {video_info['channel_title']}</span>
                    <span class="stat-badge">⏱️ {video_info['duration']}</span>
                    <span class="stat-badge">👁️ {video_info['view_count']} Views</span>
                </div>
                <p class="video-date">
                    📅 Published: {video_info['published_at']}
                </p>
            </div>
            ''', unsafe_allow_html=True)

        # テキスト処理
        text_processor = TextProcessor()
        with st.spinner("Generating transcript..."):
            transcript = text_processor.get_transcript(youtube_url)
            st.markdown('<h3 class="section-header">📝 Transcript</h3>', unsafe_allow_html=True)

            if st.button("✨ Proofread & Format", use_container_width=True, key="proofread_button"):
                try:
                    with st.spinner("Proofreading text..."):
                        proofread_transcript = text_processor.proofread_text(transcript)
                        st.session_state.proofread_transcript = proofread_transcript
                except Exception as e:
                    st.error(f"Error during proofreading: {str(e)}")

            # Original transcript display
            st.markdown('<h5 class="subsection-header">Original Transcript</h5>', unsafe_allow_html=True)
            col1, col2 = st.columns([4, 1])
            with col1:
                st.text_area("Original transcript text", transcript, height=200, label_visibility="collapsed")
            with col2:
                st.button("📋 Copy", key="copy_original", use_container_width=True)

            # Proofread text display
            if 'proofread_transcript' in st.session_state:
                st.markdown('<h5 class="subsection-header">Proofread Text</h5>', unsafe_allow_html=True)
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.text_area("Proofread text", st.session_state.proofread_transcript, height=200, label_visibility="collapsed")
                with col2:
                    st.button("📋 Copy", key="copy_proofread", use_container_width=True)

            # AI Summary section
            st.markdown('<h3 class="section-header">📊 AI Summary</h3>', unsafe_allow_html=True)
            summary = text_processor.generate_summary(transcript)
            
            col1, col2 = st.columns([4, 1])
            with col1:
                st.markdown(f'''
                <div class="glass-container summary-container">
                    <div class="summary-text">
                        {summary}
                    </div>
                </div>
                ''', unsafe_allow_html=True)
            with col2:
                st.button("📋 Copy", key="copy_summary", use_container_width=True)

        # Mind Map generation
        mindmap_gen = MindMapGenerator()
        with st.spinner("Generating mind map..."):
            mindmap_data = mindmap_gen.generate_mindmap(transcript)
            st.markdown('<h3 class="section-header">🔄 Mind Map</h3>', unsafe_allow_html=True)
            
            fig = mindmap_gen.create_visualization(mindmap_data)
            fig.update_layout(
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                font=dict(color='white'),
            )
            st.plotly_chart(fig, use_container_width=True)
            mindmap_svg = fig.to_image(format="svg")

        # PDF Report generation
        st.markdown('<h3 class="section-header">📑 Analysis Report</h3>', unsafe_allow_html=True)
        
        with st.spinner("Generating PDF report..."):
            try:
                pdf_gen = PDFGenerator()
                pdf_data = pdf_gen.create_pdf(
                    video_info=video_info,
                    transcript=transcript,
                    summary=summary,
                    mindmap_image=mindmap_svg
                )
                st.session_state.pdf_data = pdf_data
                
                st.download_button(
                    label="📥 Download PDF Report",
                    data=pdf_data,
                    file_name=f"{video_info['title']}_analysis_report.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
                
            except Exception as e:
                st.error(f"Error generating PDF report: {str(e)}")

    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
