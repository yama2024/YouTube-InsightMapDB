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
    page_title="YouTube Insight Map",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# カスタムCSSの読み込み
css_path = 'styles/custom.css'
if os.path.exists(css_path):
    with open(css_path) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

# Additional CSS for enhanced visuals
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
    
    .element-container {
        background: rgba(255, 255, 255, 0.1);
        backdrop-filter: blur(10px);
        border-radius: 15px;
        padding: 1.5rem;
        margin: 1rem 0;
    }
    
    .css-1d391kg {  /* Streamlit's default containers */
        background: rgba(255, 255, 255, 0.05) !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        padding: 1rem !important;
        border-radius: 15px !important;
    }
    
    .stButton>button {
        background: linear-gradient(45deg, #1a365d, #4a90e2);
        color: white;
        border: none;
        padding: 0.5rem 1rem;
        border-radius: 10px;
        transition: all 0.3s ease;
    }
    
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(0,0,0,0.2);
    }
    
    /* Enhanced text input styling */
    .stTextInput>div>div>input {
        background: rgba(255, 255, 255, 0.9);
        border-radius: 10px;
        border: 1px solid rgba(26, 54, 93, 0.2);
        padding: 0.5rem 1rem;
        transition: all 0.3s ease;
    }
    
    .stTextInput>div>div>input:focus {
        border-color: #4a90e2;
        box-shadow: 0 0 0 2px rgba(74, 144, 226, 0.2);
    }
</style>
""", unsafe_allow_html=True)

# ヘッダーセクション
st.markdown("""
<div style="text-align: center; padding: 2rem 0;">
    <h1 style="
        font-size: 3.5rem;
        font-weight: 800;
        background: linear-gradient(45deg, #FFFFFF, #E0E7FF);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 1rem;
        text-transform: capitalize;
    ">YouTube Insight Map</h1>
    <p style="
        font-size: 1.4rem;
        color: rgba(255, 255, 255, 0.9);
        margin-bottom: 2rem;
        font-weight: 500;
    ">動画コンテンツを知識の地図に変換</p>
</div>

<div style="
    background: rgba(255, 255, 255, 0.1);
    backdrop-filter: blur(10px);
    padding: 2.5rem;
    border-radius: 20px;
    border: 1px solid rgba(255, 255, 255, 0.2);
    margin: 2rem 0;
">
    <h4 style="
        color: white;
        font-size: 2rem;
        margin-bottom: 1.5rem;
        font-weight: 700;
    ">🎯 コンテンツを深く理解する</h4>
    <p style="
        color: rgba(255, 255, 255, 0.9);
        margin-bottom: 2rem;
        font-size: 1.2rem;
        line-height: 1.6;
    ">AIを活用して動画コンテンツを分析し、知識を構造化します。</p>
    <div style="
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
        gap: 1.5rem;
    ">
        <div style="
            background: rgba(255, 255, 255, 0.15);
            padding: 1.5rem;
            border-radius: 16px;
            border: 1px solid rgba(255, 255, 255, 0.2);
            transition: transform 0.3s ease;
        ">
            <h5 style="color: white; margin: 0; font-size: 1.3rem; font-weight: 700;">📝 文字起こし</h5>
            <p style="color: rgba(255, 255, 255, 0.9); margin: 0.8rem 0 0 0; font-size: 1rem;">高精度な音声認識で動画の内容を自動でテキスト化</p>
        </div>
        <div style="
            background: rgba(255, 255, 255, 0.15);
            padding: 1.5rem;
            border-radius: 16px;
            border: 1px solid rgba(255, 255, 255, 0.2);
            transition: transform 0.3s ease;
        ">
            <h5 style="color: white; margin: 0; font-size: 1.3rem; font-weight: 700;">🤖 AI要約</h5>
            <p style="color: rgba(255, 255, 255, 0.9); margin: 0.8rem 0 0 0; font-size: 1rem;">重要なポイントを自動で抽出し、簡潔に要約</p>
        </div>
        <div style="
            background: rgba(255, 255, 255, 0.15);
            padding: 1.5rem;
            border-radius: 16px;
            border: 1px solid rgba(255, 255, 255, 0.2);
            transition: transform 0.3s ease;
        ">
            <h5 style="color: white; margin: 0; font-size: 1.3rem; font-weight: 700;">🔄 マインドマップ</h5>
            <p style="color: rgba(255, 255, 255, 0.9); margin: 0.8rem 0 0 0; font-size: 1rem;">コンテンツを視覚的に構造化し、理解を深める</p>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# セッション状態の初期化
if 'pdf_data' not in st.session_state:
    st.session_state.pdf_data = None
if 'video_info' not in st.session_state:
    st.session_state.video_info = None

# URL入力セクション
st.markdown("""
<h3 style="
    font-size: 2rem;
    color: white;
    margin: 2rem 0 1rem;
    font-weight: 700;
">🎥 動画を分析する</h3>
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
                            st.experimental_rerun()
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