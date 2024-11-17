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
def load_css():
    css_path = os.path.join(os.path.dirname(__file__), 'styles', 'custom.css')
    if os.path.exists(css_path):
        with open(css_path) as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    else:
        st.error("CSS file not found!")

load_css()

# アプリヘッダー
st.markdown('''
<div class="app-header">
    <div class="app-title">YouTube InsightMap</div>
    <div class="app-subtitle">Content Knowledge Visualization</div>
</div>
''', unsafe_allow_html=True)

# 機能紹介セクション
st.markdown('''
<div class="glass-container feature-container">
    <h4 class="section-header" style="margin-top: 0;">🎯 Advanced Content Analysis</h4>
    <p class="feature-description">
        AIテクノロジーを活用して動画コンテンツを分析し、知識を構造化します
    </p>
    <div class="feature-grid">
        <div class="feature-card">
            <div class="feature-icon">📝</div>
            <h5 class="feature-title">高精度文字起こし</h5>
            <p class="feature-text">
                AIによる高精度な音声認識と文字起こし
            </p>
            <div class="feature-glow"></div>
        </div>
        <div class="feature-card">
            <div class="feature-icon">🤖</div>
            <h5 class="feature-title">インテリジェント要約</h5>
            <p class="feature-text">
                重要ポイントを自動で抽出・整理
            </p>
            <div class="feature-glow"></div>
        </div>
        <div class="feature-card">
            <div class="feature-icon">🔄</div>
            <h5 class="feature-title">ダイナミックマップ</h5>
            <p class="feature-text">
                コンテンツ構造をビジュアライズ
            </p>
            <div class="feature-glow"></div>
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
st.markdown('<h3 class="section-header">🎥 Analyze Your Video</h3>', unsafe_allow_html=True)

youtube_url = st.text_input(
    "YouTube URLを入力",
    placeholder="https://www.youtube.com/watch?v=...",
    help="分析したいYouTube動画のURLを入力してください"
)

if youtube_url:
    try:
        # YouTube情報の取得
        with st.spinner("動画情報を取得中..."):
            st.markdown('''
            <div class="loading-container">
                <div class="loading-dots">
                    <span></span><span></span><span></span>
                </div>
                <p class="loading-text">動画情報を取得しています</p>
                <div class="progress-bar"></div>
            </div>
            ''', unsafe_allow_html=True)
            yt_helper = YouTubeHelper()
            video_info = yt_helper.get_video_info(youtube_url)
            st.session_state.video_info = video_info
        
        # 動画情報セクション
        st.markdown('<h3 class="section-header">📺 Video Information</h3>', unsafe_allow_html=True)
        
        col1, col2 = st.columns([1, 2])
        with col1:
            st.image(video_info['thumbnail_url'], use_container_width=True)
        
        with col2:
            st.markdown(f'''
            <div class="glass-container video-info">
                <h2 class="video-title">{video_info['title']}</h2>
                <div class="video-stats">
                    <span class="stat-badge">👤 {video_info['channel_title']}</span>
                    <span class="stat-badge">⏱️ {video_info['duration']}</span>
                    <span class="stat-badge">👁️ {video_info['view_count']}回視聴</span>
                </div>
                <p class="video-date">
                    📅 投稿日: {video_info['published_at']}
                </p>
            </div>
            ''', unsafe_allow_html=True)

        # テキスト処理
        text_processor = TextProcessor()
        with st.spinner("文字起こしを生成中..."):
            st.markdown('''
            <div class="loading-container">
                <div class="loading-spinner"></div>
                <p class="loading-text">文字起こしを生成しています</p>
                <div class="progress-bar"></div>
            </div>
            ''', unsafe_allow_html=True)
            transcript = text_processor.get_transcript(youtube_url)
            st.markdown('<h3 class="section-header">📝 Transcript</h3>', unsafe_allow_html=True)

            # Original transcript display
            st.markdown('<h5 class="subsection-header">元の文字起こし</h5>', unsafe_allow_html=True)
            col1, col2 = st.columns([4, 1])
            with col1:
                st.text_area("文字起こしテキスト", transcript, height=200, label_visibility="collapsed")
            with col2:
                st.button("📋 コピー", key="copy_original", use_container_width=True)

            # AI要約セクション
            st.markdown('<h3 class="section-header">📊 AI Summary</h3>', unsafe_allow_html=True)
            with st.spinner("要約を生成中..."):
                st.markdown('''
                <div class="loading-container">
                    <div class="loading-dots">
                        <span></span><span></span><span></span>
                    </div>
                    <p class="loading-text">AIが要約を生成しています</p>
                    <div class="shimmer"></div>
                </div>
                ''', unsafe_allow_html=True)
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
                st.button("📋 コピー", key="copy_summary", use_container_width=True)

            # Add proofread button after summary
            st.markdown('<h3 class="section-header">✨ Text Enhancement</h3>', unsafe_allow_html=True)
            if st.button("校閲して整形する", use_container_width=True, key="proofread_button"):
                try:
                    with st.spinner("テキストを校閲中..."):
                        st.markdown('''
                        <div class="loading-container">
                            <div class="loading-spinner"></div>
                            <p class="loading-text">テキストを校閲・整形しています</p>
                            <div class="shimmer"></div>
                        </div>
                        ''', unsafe_allow_html=True)
                        proofread_transcript = text_processor.proofread_text(transcript)
                        st.session_state.proofread_transcript = proofread_transcript
                        
                        # Determine if text needs to be split (more than 2000 characters as threshold)
                        if len(proofread_transcript) <= 2000:
                            # Show in single window if text is short enough
                            st.markdown('<h5 class="subsection-header">校閲済みテキスト</h5>', unsafe_allow_html=True)
                            col1, col2 = st.columns([4, 1])
                            with col1:
                                st.text_area(
                                    "校閲済みテキスト",
                                    proofread_transcript,
                                    height=300,
                                    label_visibility="collapsed"
                                )
                            with col2:
                                st.button("📋 コピー", key="copy_proofread", use_container_width=True)
                        else:
                            # Split text into chunks of roughly equal size
                            total_length = len(proofread_transcript)
                            chunk_size = total_length // 3 if total_length > 4000 else total_length // 2
                            
                            chunks = []
                            current_chunk = []
                            current_length = 0
                            
                            # Split at sentence boundaries
                            for sentence in proofread_transcript.split('。'):
                                if not sentence.strip():
                                    continue
                                sentence = sentence + '。'
                                
                                if current_length + len(sentence) > chunk_size and current_chunk:
                                    chunks.append(''.join(current_chunk))
                                    current_chunk = [sentence]
                                    current_length = len(sentence)
                                else:
                                    current_chunk.append(sentence)
                                    current_length += len(sentence)
                            
                            if current_chunk:
                                chunks.append(''.join(current_chunk))
                            
                            # Display each chunk
                            for i, chunk in enumerate(chunks, 1):
                                st.markdown(f'<h5 class="subsection-header">校閲済みテキスト_{i}</h5>', unsafe_allow_html=True)
                                col1, col2 = st.columns([4, 1])
                                with col1:
                                    st.text_area(
                                        f"校閲済みテキスト_{i}",
                                        chunk.strip(),
                                        height=200,
                                        label_visibility="collapsed"
                                    )
                                with col2:
                                    st.button("📋 コピー", key=f"copy_proofread_{i}", use_container_width=True)
                                    
                except Exception as e:
                    st.error(f"校閲中にエラーが発生しました: {str(e)}")

        # マインドマップ生成
        mindmap_gen = MindMapGenerator()
        with st.spinner("マインドマップを生成中..."):
            st.markdown('''
            <div class="loading-container">
                <div class="loading-spinner"></div>
                <p class="loading-text">マインドマップを生成しています</p>
                <div class="progress-bar"></div>
            </div>
            ''', unsafe_allow_html=True)
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

        # PDFレポート生成
        st.markdown('<h3 class="section-header">📑 Analysis Report</h3>', unsafe_allow_html=True)
        
        with st.spinner("PDFレポートを生成中..."):
            st.markdown('''
            <div class="loading-container">
                <div class="loading-dots">
                    <span></span><span></span><span></span>
                </div>
                <p class="loading-text">PDFレポートを生成しています</p>
                <div class="shimmer"></div>
            </div>
            ''', unsafe_allow_html=True)
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
                    file_name=f"{video_info['title']}_分析レポート.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
                
            except Exception as e:
                st.error(f"PDFレポートの生成中にエラーが発生しました: {str(e)}")

    except Exception as e:
        st.error(f"エラーが発生しました: {str(e)}")
