import streamlit as st
import pandas as pd
from utils.youtube_helper import YouTubeHelper
from utils.text_processor import TextProcessor
from utils.mindmap_generator import MindMapGenerator
from utils.pdf_generator import PDFGenerator
import plotly.graph_objects as go
import os
import io

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

# Enhanced visual styles
st.markdown("""
<style>
    @keyframes gradientBG {
        0% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }
    
    .stApp {
        background: linear-gradient(-45deg, #1a365d, #4a90e2, #7fb3d5);
        background-size: 400% 400%;
        animation: gradientBG 15s ease infinite;
    }
    
    .glass-container {
        background: rgba(255, 255, 255, 0.15) !important;
        backdrop-filter: blur(12px) !important;
        border: 1px solid rgba(255, 255, 255, 0.2) !important;
        border-radius: 20px !important;
        padding: 2rem !important;
        margin: 1.5rem 0 !important;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1) !important;
    }
    
    .stTextInput > div > div > input {
        background: rgba(255, 255, 255, 0.95) !important;
        color: #1a365d !important;
        border-radius: 10px !important;
        border: 1px solid rgba(26, 54, 93, 0.2) !important;
        padding: 0.75rem 1rem !important;
        font-size: 1.1rem !important;
        transition: all 0.3s ease !important;
    }
    
    .stTextInput > div > div > input:focus {
        border-color: #4a90e2 !important;
        box-shadow: 0 0 0 2px rgba(74, 144, 226, 0.2) !important;
    }
    
    .stButton > button {
        background: linear-gradient(45deg, #1a365d, #4a90e2) !important;
        color: white !important;
        border: none !important;
        padding: 0.75rem 1.5rem !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
        transition: all 0.3s ease !important;
        text-transform: uppercase !important;
        letter-spacing: 0.5px !important;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 5px 15px rgba(0, 0, 0, 0.2) !important;
    }
    
    .title {
        font-size: 3.5rem !important;
        font-weight: 800 !important;
        background: linear-gradient(45deg, #FFFFFF, #E0E7FF) !important;
        -webkit-background-clip: text !important;
        -webkit-text-fill-color: transparent !important;
        text-transform: capitalize !important;
        text-align: center !important;
        margin: 2rem 0 !important;
        letter-spacing: 1px !important;
    }
    
    .subtitle {
        font-size: 1.4rem !important;
        color: rgba(255, 255, 255, 0.95) !important;
        text-align: center !important;
        font-weight: 500 !important;
        margin-bottom: 3rem !important;
    }
</style>
""", unsafe_allow_html=True)

# Enhanced header section
st.markdown("""
<div class="title">YouTube InsightMap</div>
<div class="subtitle">コンテンツを知識の地図に変換</div>
""", unsafe_allow_html=True)

# Feature showcase section
st.markdown("""
<div class="glass-container">
    <h4 style="color: white; font-size: 2rem; margin-bottom: 1.5rem; font-weight: 700;">
        🎯 コンテンツを深く理解する
    </h4>
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
""", unsafe_allow_html=True)

# Initialize session state
if 'pdf_data' not in st.session_state:
    st.session_state.pdf_data = None
if 'video_info' not in st.session_state:
    st.session_state.video_info = None

# URL input section with enhanced styling
st.markdown("""
<h3 style="color: white; font-size: 2rem; margin: 2rem 0 1rem; font-weight: 700;">
    🎥 動画を分析する
</h3>
""", unsafe_allow_html=True)

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
        
        # 動画情報の表示
        st.markdown("""
        <h3 style="
            font-size: 2rem;
            color: white;
            margin: 2rem 0 1rem;
            font-weight: 700;
        ">📺 動画の基本情報</h3>
        """, unsafe_allow_html=True)
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.image(video_info['thumbnail_url'], use_container_width=True)
        
        with col2:
            st.markdown(f"""
            <div style="
                background: rgba(255, 255, 255, 0.15);
                backdrop-filter: blur(10px);
                padding: 2rem;
                border-radius: 20px;
                height: 100%;
                border: 1px solid rgba(255, 255, 255, 0.2);
            ">
                <h2 style="
                    color: white;
                    font-size: 1.8rem;
                    font-weight: 700;
                    margin-bottom: 1rem;
                    line-height: 1.4;
                ">{video_info['title']}</h2>
                <div style="
                    display: flex;
                    flex-wrap: wrap;
                    gap: 0.8rem;
                    margin: 1.5rem 0;
                ">
                    <span style="
                        background: rgba(255, 255, 255, 0.2);
                        padding: 0.6rem 1rem;
                        border-radius: 12px;
                        color: white;
                        font-weight: 600;
                    ">👤 {video_info['channel_title']}</span>
                    <span style="
                        background: rgba(255, 255, 255, 0.2);
                        padding: 0.6rem 1rem;
                        border-radius: 12px;
                        color: white;
                        font-weight: 600;
                    ">⏱️ {video_info['duration']}</span>
                    <span style="
                        background: rgba(255, 255, 255, 0.2);
                        padding: 0.6rem 1rem;
                        border-radius: 12px;
                        color: white;
                        font-weight: 600;
                    ">👁️ {video_info['view_count']}回視聴</span>
                </div>
                <p style="
                    color: rgba(255, 255, 255, 0.9);
                    font-weight: 500;
                    font-size: 1.1rem;
                    margin: 0;
                ">📅 投稿日: {video_info['published_at']}</p>
            </div>
            """, unsafe_allow_html=True)

        # 文字起こしと要約の処理
        text_processor = TextProcessor()
        
        with st.spinner("文字起こしを生成中..."):
            transcript = text_processor.get_transcript(youtube_url)
            st.markdown("""
            <h3 style="
                font-size: 2rem;
                color: white;
                margin: 2rem 0 1rem;
                font-weight: 700;
            ">📝 文字起こし</h3>
            """, unsafe_allow_html=True)
            
            col1, col2, col3 = st.columns([1, 2, 2])
            with col1:
                st.download_button(
                    label="💾 テキストを保存",
                    data=transcript.encode('utf-8'),
                    file_name="transcript.txt",
                    mime="text/plain",
                    use_container_width=True
                )
            with col2:
                if st.button("✨ 校閲して整形する", use_container_width=True):
                    try:
                        with st.spinner("テキストを校閲中..."):
                            proofread_transcript = text_processor.proofread_text(transcript)
                            st.session_state.proofread_transcript = proofread_transcript
                            st.rerun()
                    except Exception as e:
                        st.error(f"校閲中にエラーが発生しました: {str(e)}")

            # テキストエリアを校閲済みテキストで更新
            display_text = st.session_state.get('proofread_transcript', transcript)
            st.text_area("文字起こしテキスト", display_text, height=200, label_visibility="collapsed")

            with col3:
                st.markdown("""
                <h3 style="
                    font-size: 2rem;
                    color: white;
                    margin: 2rem 0 1rem;
                    font-weight: 700;
                ">📊 AI要約</h3>
                """, unsafe_allow_html=True)
                summary = text_processor.generate_summary(transcript)
                st.markdown(f"""
                <div style="
                    background: rgba(255, 255, 255, 0.15);
                    backdrop-filter: blur(10px);
                    padding: 2rem;
                    border-radius: 20px;
                    border: 1px solid rgba(255, 255, 255, 0.2);
                ">
                    <div style="
                        color: white;
                        font-weight: 500;
                        font-size: 1.1rem;
                        line-height: 1.6;
                    ">{summary}</div>
                </div>
                """, unsafe_allow_html=True)

        # マインドマップの生成と表示
        mindmap_gen = MindMapGenerator()
        with st.spinner("マインドマップを生成中..."):
            mindmap_data = mindmap_gen.generate_mindmap(transcript)
            st.markdown("""
            <h3 style="
                font-size: 2rem;
                color: white;
                margin: 2rem 0 1rem;
                font-weight: 700;
            ">🔄 マインドマップ</h3>
            """, unsafe_allow_html=True)
            fig = mindmap_gen.create_visualization(mindmap_data)
            
            # Update figure layout for better visibility
            fig.update_layout(
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                font=dict(color='white'),
            )
            st.plotly_chart(fig, use_container_width=True)

            # マインドマップの画像をSVG形式で保存
            mindmap_svg = fig.to_image(format="svg")

        # PDFレポートの生成と保存ボタンの追加
        st.markdown("""
        <h3 style="
            font-size: 2rem;
            color: white;
            margin: 2rem 0 1rem;
            font-weight: 700;
        ">📑 分析レポート</h3>
        """, unsafe_allow_html=True)
        
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