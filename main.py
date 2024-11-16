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
    <h4 class="section-header" style="margin-top: 0;">🎯 動画コンテンツの深い理解</h4>
    <p class="feature-description">
        AIテクノロジーを活用して動画コンテンツを分析し、知識を構造化します。
    </p>
    <div class="feature-grid">
        <div class="feature-card">
            <h5 class="feature-title">📝 文字起こし</h5>
            <p class="feature-text">
                高精度な自動音声認識による文字起こし
            </p>
        </div>
        <div class="feature-card">
            <h5 class="feature-title">🤖 AI要約</h5>
            <p class="feature-text">
                重要ポイントの自動抽出
            </p>
        </div>
        <div class="feature-card">
            <h5 class="feature-title">🔄 マインドマップ</h5>
            <p class="feature-text">
                コンテンツ構造の可視化
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
st.markdown('<h3 class="section-header">🎥 動画を分析</h3>', unsafe_allow_html=True)

youtube_url = st.text_input(
    "YouTube URLを入力",
    placeholder="https://www.youtube.com/watch?v=...",
    help="分析したいYouTube動画のURLを入力してください"
)

if youtube_url:
    try:
        # YouTube情報の取得
        yt_helper = YouTubeHelper()
        video_info = yt_helper.get_video_info(youtube_url)
        st.session_state.video_info = video_info
        
        # 動画情報セクション
        st.markdown('<h3 class="section-header">📺 動画情報</h3>', unsafe_allow_html=True)
        
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
            transcript = text_processor.get_transcript(youtube_url)
            st.markdown('<h3 class="section-header">📝 文字起こし</h3>', unsafe_allow_html=True)

            # Original transcript display
            st.markdown('<h5 class="subsection-header">元の文字起こし</h5>', unsafe_allow_html=True)
            col1, col2 = st.columns([4, 1])
            with col1:
                st.text_area("文字起こしテキスト", transcript, height=200, label_visibility="collapsed")
            with col2:
                st.button("📋 コピー", key="copy_original", use_container_width=True)

            # Proofread text display
            if 'proofread_transcript' in st.session_state:
                st.markdown('<h5 class="subsection-header">校閲済みテキスト</h5>', unsafe_allow_html=True)
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.text_area("校閲済みテキスト", st.session_state.proofread_transcript, height=200, label_visibility="collapsed")
                with col2:
                    st.button("📋 コピー", key="copy_proofread", use_container_width=True)

            # AI要約セクション
            st.markdown('<h3 class="section-header">📊 AI要約</h3>', unsafe_allow_html=True)
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
            st.markdown('<h3 class="section-header">✨ テキスト校閲</h3>', unsafe_allow_html=True)
            if st.button("校閲して整形する", use_container_width=True, key="proofread_button"):
                try:
                    with st.spinner("テキストを校閲中..."):
                        proofread_transcript = text_processor.proofread_text(transcript)
                        st.session_state.proofread_transcript = proofread_transcript
                except Exception as e:
                    st.error(f"校閲中にエラーが発生しました: {str(e)}")

        # マインドマップ生成
        mindmap_gen = MindMapGenerator()
        with st.spinner("マインドマップを生成中..."):
            mindmap_data = mindmap_gen.generate_mindmap(transcript)
            st.markdown('<h3 class="section-header">🔄 マインドマップ</h3>', unsafe_allow_html=True)
            
            fig = mindmap_gen.create_visualization(mindmap_data)
            fig.update_layout(
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                font=dict(color='white'),
            )
            st.plotly_chart(fig, use_container_width=True)
            mindmap_svg = fig.to_image(format="svg")

        # PDFレポート生成
        st.markdown('<h3 class="section-header">📑 分析レポート</h3>', unsafe_allow_html=True)
        
        with st.spinner("PDFレポートを生成中..."):
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
                    label="📥 PDFレポートをダウンロード",
                    data=pdf_data,
                    file_name=f"{video_info['title']}_分析レポート.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
                
            except Exception as e:
                st.error(f"PDFレポートの生成中にエラーが発生しました: {str(e)}")

    except Exception as e:
        st.error(f"エラーが発生しました: {str(e)}")
