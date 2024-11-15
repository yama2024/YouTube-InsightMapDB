import streamlit as st
import pandas as pd
from utils.youtube_helper import YouTubeHelper
from utils.text_processor import TextProcessor
from utils.mindmap_generator import MindMapGenerator
import plotly.graph_objects as go

# ページ設定
st.set_page_config(
    page_title="YouTube コンテンツ分析ツール",
    page_icon="📊",
    layout="wide"
)

# カスタムCSSの読み込み
with open('styles/custom.css') as f:
    st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

# タイトルと説明
st.title("YouTube コンテンツ分析・可視化ツール")
st.markdown("""
このツールでは、YouTubeの動画コンテンツを分析し、以下の機能を提供します：
- 文字起こしテキストの生成
- 内容の要約
- マインドマップの自動生成
""")

# URL入力フォーム
youtube_url = st.text_input(
    "YouTube URLを入力してください",
    placeholder="https://www.youtube.com/watch?v=..."
)

if youtube_url:
    try:
        # YouTube情報の取得
        yt_helper = YouTubeHelper()
        video_info = yt_helper.get_video_info(youtube_url)
        
        # 動画情報の表示
        col1, col2 = st.columns(2)
        with col1:
            st.image(video_info['thumbnail_url'], use_column_width=True)
        with col2:
            st.subheader("動画情報")
            st.write(f"📺 タイトル: {video_info['title']}")
            st.write(f"👤 投稿者: {video_info['channel_title']}")
            st.write(f"⏱️ 動画の長さ: {video_info['duration']}")
            st.write(f"📅 投稿日: {video_info['published_at']}")

        # 文字起こしと要約の処理
        text_processor = TextProcessor()
        
        with st.spinner("文字起こしを生成中..."):
            transcript = text_processor.get_transcript(youtube_url)
            st.subheader("文字起こし")
            st.text_area("", transcript, height=200)
            
            # 文字起こしの保存ボタン
            st.download_button(
                label="文字起こしをテキストファイルとして保存",
                data=transcript,
                file_name="transcript.txt",
                mime="text/plain"
            )

        with st.spinner("要約を生成中..."):
            summary = text_processor.generate_summary(transcript)
            st.subheader("AI要約")
            st.write(summary)

        # マインドマップの生成と表示
        mindmap_gen = MindMapGenerator()
        with st.spinner("マインドマップを生成中..."):
            mindmap_data = mindmap_gen.generate_mindmap(transcript)
            st.subheader("マインドマップ")
            fig = mindmap_gen.create_visualization(mindmap_data)
            st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"エラーが発生しました: {str(e)}")
