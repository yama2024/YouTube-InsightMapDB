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
        background: linear-gradient(-45deg, #f3f4f6, #ffffff, #e2e8f0, #f8fafc);
        background-size: 400% 400%;
        animation: gradientBG 15s ease infinite;
    }
    
    .card-hover {
        transition: transform 0.3s ease, box-shadow 0.3s ease;
    }
    
    .card-hover:hover {
        transform: translateY(-5px);
        box-shadow: 0 10px 20px rgba(0,0,0,0.1);
    }
    
    .section-header {
        background: linear-gradient(90deg, #1a365d, #2d4a8a);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 700;
    }
</style>
""", unsafe_allow_html=True)

# ヘッダーセクション
st.markdown("""
<div style='text-align: center; padding: 2rem 0; animation: fadeIn 1.2s ease-in;'>
    <h1 style='font-size: 2.5rem; font-weight: 800; margin-bottom: 0.5rem;
              background: linear-gradient(90deg, #1a365d, #2d4a8a);
              -webkit-background-clip: text;
              -webkit-text-fill-color: transparent;'>
        YouTube Insight Map
    </h1>
    <p style='font-size: 1.2rem; color: #4a5568; margin-bottom: 2rem;
              font-weight: 500; letter-spacing: 0.5px;'>
        動画コンテンツを知識の地図に変換
    </p>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div style='background: rgba(255, 255, 255, 0.95); 
            backdrop-filter: blur(10px); 
            padding: 2.5rem; 
            border-radius: 20px; 
            margin: 2rem 0; 
            border: 1px solid rgba(255, 255, 255, 0.2);
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            animation: fadeIn 0.8s ease-in;'>
    <h4 style='margin: 0; color: #1a365d; 
              font-size: 1.8rem; 
              margin-bottom: 1.5rem; 
              font-weight: 700;
              letter-spacing: 0.5px;'>
        🎯 コンテンツを深く理解する
    </h4>
    <p style='color: #2d3748; 
              margin-bottom: 2rem; 
              font-weight: 500;
              font-size: 1.1rem;
              line-height: 1.6;'>
        AIを活用して動画コンテンツを分析し、知識を構造化します。
    </p>
    <div style='display: grid; 
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); 
                gap: 1.5rem;'>
        <div class='card-hover' style='background: rgba(255,255,255,0.9); 
                    padding: 1.5rem; 
                    border-radius: 16px;
                    border: 1px solid rgba(26, 54, 93, 0.1);'>
            <h5 style='color: #1a365d; 
                      margin: 0; 
                      font-size: 1.3rem; 
                      font-weight: 700;'>📝 文字起こし</h5>
            <p style='color: #4a5568; 
                      margin: 0.8rem 0 0 0; 
                      font-size: 1rem; 
                      font-weight: 500;
                      line-height: 1.5;'>
                高精度な音声認識で動画の内容を自動でテキスト化
            </p>
        </div>
        <div class='card-hover' style='background: rgba(255,255,255,0.9); 
                    padding: 1.5rem; 
                    border-radius: 16px;
                    border: 1px solid rgba(26, 54, 93, 0.1);'>
            <h5 style='color: #1a365d; 
                      margin: 0; 
                      font-size: 1.3rem; 
                      font-weight: 700;'>🤖 AI要約</h5>
            <p style='color: #4a5568; 
                      margin: 0.8rem 0 0 0; 
                      font-size: 1rem; 
                      font-weight: 500;
                      line-height: 1.5;'>
                重要なポイントを自動で抽出し、簡潔に要約
            </p>
        </div>
        <div class='card-hover' style='background: rgba(255,255,255,0.9); 
                    padding: 1.5rem; 
                    border-radius: 16px;
                    border: 1px solid rgba(26, 54, 93, 0.1);'>
            <h5 style='color: #1a365d; 
                      margin: 0; 
                      font-size: 1.3rem; 
                      font-weight: 700;'>🔄 マインドマップ</h5>
            <p style='color: #4a5568; 
                      margin: 0.8rem 0 0 0; 
                      font-size: 1rem; 
                      font-weight: 500;
                      line-height: 1.5;'>
                コンテンツを視覚的に構造化し、理解を深める
            </p>
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
st.markdown("<h3 class='section-header' style='font-size: 1.8rem; margin: 2rem 0 1rem;'>🎥 動画を分析する</h3>", unsafe_allow_html=True)
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
        st.markdown("<h3 class='section-header' style='font-size: 1.8rem; margin: 2rem 0 1rem;'>📺 動画の基本情報</h3>", unsafe_allow_html=True)
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.image(video_info['thumbnail_url'], use_container_width=True)
        
        with col2:
            st.markdown(f"""
            <div style='background: rgba(255, 255, 255, 0.95); 
                        backdrop-filter: blur(10px);
                        padding: 2rem; 
                        border-radius: 20px; 
                        height: 100%;
                        border: 1px solid rgba(255, 255, 255, 0.2);
                        box-shadow: 0 8px 32px rgba(0,0,0,0.1);'>
                <h2 style='margin: 0; 
                          color: #1a365d; 
                          font-size: 1.5rem; 
                          font-weight: 700;
                          text-shadow: 1px 1px 2px rgba(0,0,0,0.1);
                          line-height: 1.4;'>
                    {video_info['title']}
                </h2>
                <p style='margin: 1.5rem 0;'>
                    <span style='background: rgba(26,54,93,0.1); 
                              padding: 0.6rem 1rem; 
                              border-radius: 12px; 
                              margin-right: 1rem; 
                              color: #1a365d;
                              font-weight: 600;
                              display: inline-block;
                              margin-bottom: 0.5rem;'>
                        👤 {video_info['channel_title']}
                    </span>
                    <span style='background: rgba(26,54,93,0.1); 
                              padding: 0.6rem 1rem; 
                              border-radius: 12px; 
                              margin-right: 1rem; 
                              color: #1a365d;
                              font-weight: 600;
                              display: inline-block;
                              margin-bottom: 0.5rem;'>
                        ⏱️ {video_info['duration']}
                    </span>
                </p>
                <p style='margin: 0; 
                         color: #2d3748; 
                         font-weight: 500;
                         font-size: 1.1rem;'>
                    📅 投稿日: {video_info['published_at']}
                </p>
            </div>
            """, unsafe_allow_html=True)

        # 文字起こしと要約の処理
        text_processor = TextProcessor()
        
        with st.spinner("文字起こしを生成中..."):
            transcript = text_processor.get_transcript(youtube_url)
            st.markdown("<h3 class='section-header' style='font-size: 1.8rem; margin: 2rem 0 1rem;'>📝 文字起こし</h3>", unsafe_allow_html=True)
            st.text_area("文字起こしテキスト", transcript, height=200, label_visibility="collapsed")
            
            col1, col2 = st.columns([1, 4])
            with col1:
                # 文字起こしの保存ボタン
                st.download_button(
                    label="💾 テキストを保存",
                    data=transcript.encode('utf-8'),
                    file_name="transcript.txt",
                    mime="text/plain",
                    use_container_width=True
                )

        with st.spinner("要約を生成中..."):
            summary = text_processor.generate_summary(transcript)
            st.markdown("<h3 class='section-header' style='font-size: 1.8rem; margin: 2rem 0 1rem;'>📊 AI要約</h3>", unsafe_allow_html=True)
            st.markdown(f"""
            <div style='background: rgba(255, 255, 255, 0.95); 
                        backdrop-filter: blur(10px);
                        padding: 2rem; 
                        border-radius: 20px;
                        border: 1px solid rgba(255, 255, 255, 0.2);
                        box-shadow: 0 8px 32px rgba(0,0,0,0.1);'>
                <div style='color: #1a365d; 
                          font-weight: 500;
                          font-size: 1.1rem;
                          line-height: 1.6;'>
                    {summary}
                </div>
            </div>
            """, unsafe_allow_html=True)

        # マインドマップの生成と表示
        mindmap_gen = MindMapGenerator()
        with st.spinner("マインドマップを生成中..."):
            mindmap_data = mindmap_gen.generate_mindmap(transcript)
            st.markdown("<h3 class='section-header' style='font-size: 1.8rem; margin: 2rem 0 1rem;'>🔄 マインドマップ</h3>", unsafe_allow_html=True)
            fig = mindmap_gen.create_visualization(mindmap_data)
            st.plotly_chart(fig, use_container_width=True)

            # マインドマップの画像をSVG形式で保存
            mindmap_svg = fig.to_image(format="svg")

        # PDFレポートの生成と保存ボタンの追加
        st.markdown("<h3 class='section-header' style='font-size: 1.8rem; margin: 2rem 0 1rem;'>📑 分析レポート</h3>", unsafe_allow_html=True)
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
