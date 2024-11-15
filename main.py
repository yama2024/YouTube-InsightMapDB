import streamlit as st
import pandas as pd
from utils.youtube_helper import YouTubeHelper
from utils.text_processor import TextProcessor
from utils.mindmap_generator import MindMapGenerator
import plotly.graph_objects as go
import os

# ページ設定
st.set_page_config(
    page_title="YouTube コンテンツ分析ツール",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# カスタムCSSの読み込み
css_path = 'styles/custom.css'
if os.path.exists(css_path):
    with open(css_path) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

# ヘッダーセクション
st.title("YouTube コンテンツ分析・可視化ツール")
st.markdown("""
<div style='background: linear-gradient(120deg, #F8FAFC, #EFF6FF); padding: 1.5rem; border-radius: 12px; margin-bottom: 2rem;'>
    <h4 style='margin: 0; color: #1B365D;'>📌 このツールでできること</h4>
    <ul style='margin-bottom: 0;'>
        <li>動画の文字起こしテキスト生成</li>
        <li>AIによる内容の要約作成</li>
        <li>マインドマップの自動生成</li>
    </ul>
</div>
""", unsafe_allow_html=True)

# URL入力セクション
st.markdown("### 🎥 動画を分析する")
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
        
        # 動画情報の表示
        st.markdown("### 📺 動画の基本情報")
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.image(video_info['thumbnail_url'], use_column_width=True)
        
        with col2:
            st.markdown(f"""
            <div style='background: white; padding: 1.5rem; border-radius: 12px; height: 100%;'>
                <h2 style='margin: 0; color: #1B365D; font-size: 1.2rem;'>{video_info['title']}</h2>
                <p style='margin: 1rem 0;'>
                    <span style='background: #E5E7EB; padding: 0.2rem 0.5rem; border-radius: 4px; margin-right: 0.5rem;'>
                        👤 {video_info['channel_title']}
                    </span>
                    <span style='background: #E5E7EB; padding: 0.2rem 0.5rem; border-radius: 4px; margin-right: 0.5rem;'>
                        ⏱️ {video_info['duration']}
                    </span>
                </p>
                <p style='margin: 0; color: #64748B;'>📅 投稿日: {video_info['published_at']}</p>
            </div>
            """, unsafe_allow_html=True)

        # 文字起こしと要約の処理
        text_processor = TextProcessor()
        
        with st.spinner("文字起こしを生成中..."):
            transcript = text_processor.get_transcript(youtube_url)
            st.markdown("### 📝 文字起こし")
            st.text_area("", transcript, height=200)
            
            col1, col2 = st.columns([1, 4])
            with col1:
                # 文字起こしの保存ボタン
                st.download_button(
                    label="💾 テキストを保存",
                    data=transcript,
                    file_name="transcript.txt",
                    mime="text/plain",
                    use_container_width=True
                )

        with st.spinner("要約を生成中..."):
            summary = text_processor.generate_summary(transcript)
            st.markdown("### 📊 AI要約")
            st.markdown(f"""
            <div style='background: white; padding: 1.5rem; border-radius: 12px;'>
                {summary}
            </div>
            """, unsafe_allow_html=True)

        # マインドマップの生成と表示
        mindmap_gen = MindMapGenerator()
        with st.spinner("マインドマップを生成中..."):
            mindmap_data = mindmap_gen.generate_mindmap(transcript)
            st.markdown("### 🔄 マインドマップ")
            fig = mindmap_gen.create_visualization(mindmap_data)
            st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"エラーが発生しました: {str(e)}")
