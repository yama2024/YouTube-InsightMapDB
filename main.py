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
<div class="app-subtitle">コンテンツを知識の地図に変換</div>
''', unsafe_allow_html=True)

# 機能紹介セクション
st.markdown('''
<div class="glass-container">
    <h4 class="section-header" style="margin-top: 0;">🎯 コンテンツを深く理解する</h4>
    <p style="color: rgba(255, 255, 255, 0.95); margin-bottom: 2rem; font-size: 1.2rem; line-height: 1.6;">
        AIを活用して動画コンテンツを分析し、知識を構造化します。
    </p>
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1.5rem;">
        <div class="glass-container" style="margin: 0 !important;">
            <h5 style="color: white; margin: 0; font-size: 1.3rem; font-weight: 700;">📝 文字起こし</h5>
            <p style="color: rgba(255, 255, 255, 0.9); margin: 0.8rem 0 0 0; font-size: 1rem;">
                高精度な音声認識で動画の内容を自動でテキスト化
            </p>
        </div>
        <div class="glass-container" style="margin: 0 !important;">
            <h5 style="color: white; margin: 0; font-size: 1.3rem; font-weight: 700;">🤖 AI要約</h5>
            <p style="color: rgba(255, 255, 255, 0.9); margin: 0.8rem 0 0 0; font-size: 1rem;">
                重要なポイントを自動で抽出し、簡潔に要約
            </p>
        </div>
        <div class="glass-container" style="margin: 0 !important;">
            <h5 style="color: white; margin: 0; font-size: 1.3rem; font-weight: 700;">🔄 マインドマップ</h5>
            <p style="color: rgba(255, 255, 255, 0.9); margin: 0.8rem 0 0 0; font-size: 1rem;">
                コンテンツを視覚的に構造化し、理解を深める
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
st.markdown('<h3 class="section-header">🎥 動画を分析する</h3>', unsafe_allow_html=True)

youtube_url = st.text_input(
    "YouTube URLを入力してください",
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
        st.markdown('<h3 class="section-header">📺 動画の基本情報</h3>', unsafe_allow_html=True)
        
        col1, col2 = st.columns([1, 2])
        with col1:
            st.image(video_info['thumbnail_url'], use_container_width=True)
        
        with col2:
            st.markdown(f'''
            <div class="glass-container" style="height: 100%;">
                <h2 style="color: white; font-size: 1.8rem; font-weight: 700; margin-bottom: 1rem; line-height: 1.4;">
                    {video_info['title']}
                </h2>
                <div style="display: flex; flex-wrap: wrap; gap: 0.8rem; margin: 1.5rem 0;">
                    <span class="glass-container" style="margin: 0; padding: 0.6rem 1rem;">
                        👤 {video_info['channel_title']}
                    </span>
                    <span class="glass-container" style="margin: 0; padding: 0.6rem 1rem;">
                        ⏱️ {video_info['duration']}
                    </span>
                    <span class="glass-container" style="margin: 0; padding: 0.6rem 1rem;">
                        👁️ {video_info['view_count']}回視聴
                    </span>
                </div>
                <p style="color: rgba(255, 255, 255, 0.9); font-weight: 500; font-size: 1.1rem; margin: 0;">
                    📅 投稿日: {video_info['published_at']}
                </p>
            </div>
            ''', unsafe_allow_html=True)

        # テキスト処理
        text_processor = TextProcessor()
        with st.spinner("文字起こしを生成中..."):
            transcript = text_processor.get_transcript(youtube_url)
            st.markdown('<h3 class="section-header">📝 文字起こし</h3>', unsafe_allow_html=True)

            if st.button("✨ 校閲して整形する", use_container_width=True):
                try:
                    with st.spinner("テキストを校閲中..."):
                        proofread_transcript = text_processor.proofread_text(transcript)
                        st.session_state.proofread_transcript = proofread_transcript
                        st.rerun()
                except Exception as e:
                    st.error(f"校閲中にエラーが発生しました: {str(e)}")

            display_text = st.session_state.get('proofread_transcript', transcript)
            col1, col2 = st.columns([4, 1])
            with col1:
                st.text_area("文字起こしテキスト", display_text, height=200, label_visibility="collapsed")
            with col2:
                st.button("📋 コピー", key="copy_transcript", use_container_width=True)

            # AI要約セクション
            st.markdown('<h3 class="section-header">📊 AI要約</h3>', unsafe_allow_html=True)
            summary = text_processor.generate_summary(transcript)
            
            col1, col2 = st.columns([4, 1])
            with col1:
                st.markdown(f'''
                <div class="glass-container">
                    <div style="color: white; font-weight: 500; font-size: 1.1rem; line-height: 1.6;">
                        {summary}
                    </div>
                </div>
                ''', unsafe_allow_html=True)
            with col2:
                st.button("📋 コピー", key="copy_summary", use_container_width=True)

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