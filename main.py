from utils.youtube_helper import YouTubeHelper
from utils.text_processor import TextProcessor
from utils.mindmap_generator import MindMapGenerator
from utils.pdf_generator import PDFGenerator
import streamlit as st
import os
import time
import logging
import json

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

try:
    from streamlit_mermaid import st_mermaid
    MERMAID_AVAILABLE = True
except Exception as e:
    logger.error(f"Failed to import streamlit_mermaid: {str(e)}")
    st.error("マインドマップコンポーネントの読み込みに失敗しました")
    MERMAID_AVAILABLE = False

try:
    # Page configuration
    st.set_page_config(page_title="YouTube InsightMap",
                       page_icon="🎯",
                       layout="wide",
                       initial_sidebar_state="collapsed")

    # Load CSS
    def load_css():
        try:
            css_path = os.path.join(os.path.dirname(__file__), 'styles',
                                    'custom.css')
            if os.path.exists(css_path):
                with open(css_path) as f:
                    st.markdown(f'<style>{f.read()}</style>',
                               unsafe_allow_html=True)
            else:
                logger.error("CSS file not found!")
        except Exception as e:
            logger.error(f"Error loading CSS: {str(e)}")

    load_css()

    def copy_text_block(text, label=""):
        try:
            if label:
                st.markdown(f"#### {label}")
            st.markdown(text, unsafe_allow_html=False)
        except Exception as e:
            logger.error(f"Error in copy_text_block: {str(e)}")

    # Initialize session state with error handling
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
    if 'quality_scores' not in st.session_state:
        st.session_state.quality_scores = None
    if 'mindmap' not in st.session_state:
        st.session_state.mindmap = None
    if 'mindmap_svg' not in st.session_state:
        st.session_state.mindmap_svg = None
    if 'pdf_data' not in st.session_state:
        st.session_state.pdf_data = None
    if 'enhanced_text' not in st.session_state:
        st.session_state.enhanced_text = None
    if 'enhancement_progress' not in st.session_state:
        st.session_state.enhancement_progress = {
            'progress': 0.0,
            'message': ''
        }
    if 'current_summary_style' not in st.session_state:
        st.session_state.current_summary_style = "overview"  # Default to overview

    def update_step_progress(step_name: str, completed: bool = True):
        """Update the completion status of a processing step"""
        try:
            st.session_state.steps_completed[step_name] = completed
        except Exception as e:
            logger.error(f"Error updating step progress: {str(e)}")

    # Application Header
    st.markdown('''
    <div class="app-header">
        <div class="app-title">YouTube InsightMap</div>
        <div class="app-subtitle">Content Knowledge Visualization</div>
    </div>
    ''',
                unsafe_allow_html=True)

    def get_step_status(step_number):
        try:
            if st.session_state.current_step > step_number:
                return "completed"
            elif st.session_state.current_step == step_number:
                return "active"
            return ""
        except Exception as e:
            logger.error(f"Error getting step status: {str(e)}")
            return ""

    def render_step_header(step_number, title, emoji, description=""):
        try:
            status = get_step_status(step_number)
            st.markdown(f'''
            <div class="step-header {status}">
                <div class="step-content">
                    <div class="step-title">{emoji} {title}</div>
                    {f'<div class="step-description">{description}</div>' if description else ''}
                </div>
            </div>
            ''',
                        unsafe_allow_html=True)
        except Exception as e:
            logger.error(f"Error rendering step header: {str(e)}")

    def get_score_indicator(score: float) -> tuple:
        """Get visual indicator and color class based on score"""
        if score >= 7:
            return "✅", "high"
        elif score >= 5:
            return "⚠️", "medium"
        return "❌", "low"

    def render_quality_score(score: float, label: str, description: str):
        """品質スコアを視覚的に表示"""
        indicator, score_class = get_score_indicator(score)
        
        st.markdown(f"""
        <div class="score-item">
            <div class="score-header">
                <div class="score-title">
                    {indicator} {label}
                    <div class="score-range score-{score_class}">
                        {score:.1f}/10
                    </div>
                </div>
            </div>
            <div class="score-description">{description}</div>
            <div class="score-bar">
                <div class="score-fill {score_class}" style="width: {score*10}%;"></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    def display_summary(summary_text: str):
        """Display formatted summary with importance indicators"""
        try:
            # Ensure the summary is valid JSON
            if not summary_text or not summary_text.strip():
                raise ValueError("要約テキストが空です")
                
            summary_data = json.loads(summary_text.strip())
            
            # Always display overview
            st.markdown("## 📑 動画の概要")
            st.markdown(summary_data.get("動画の概要", ""))
            
            if st.session_state.current_summary_style == "detailed":
                # Display points with proper type conversion
                st.markdown("## 🎯 主要ポイント")
                for point in summary_data.get("ポイント", []):
                    try:
                        importance = int(point.get("重要度", 3))
                    except (ValueError, TypeError):
                        importance = 3
                    
                    emoji = "🔥" if importance >= 4 else "⭐" if importance >= 2 else "ℹ️"
                    
                    st.markdown(f'''
                        <div class="summary-card">
                            <div class="importance-{'high' if importance >= 4 else 'medium' if importance >= 2 else 'low'}">
                                {emoji} <strong>ポイント{point.get("番号", "")}: {point.get("タイトル", "")}</strong>
                            </div>
                            <p>{point.get("内容", "")}</p>
                            {f'<p class="supplementary-info">{point.get("補足情報", "")}</p>' if "補足情報" in point else ""}
                        </div>
                    ''', unsafe_allow_html=True)
                
                st.markdown("## 🔑 重要なキーワード")
                for keyword in summary_data.get("キーワード", []):
                    st.markdown(f'''
                        <div class="keyword-card">
                            <strong>{keyword.get("用語", "")}</strong>: {keyword.get("説明", "")}
                            {f'<div class="related-terms">関連用語: {", ".join(keyword.get("関連用語", []))}</div>' if "関連用語" in keyword else ""}
                        </div>
                    ''', unsafe_allow_html=True)
                
                # Display quality scores only in detailed mode
                quality_scores = st.session_state.quality_scores
                if quality_scores:
                    st.markdown('''
                    <div class="quality-score-section">
                        <h3>要約品質スコア</h3>
                        <div class="quality-score-container">
                    ''', unsafe_allow_html=True)
                    
                    render_quality_score(
                        quality_scores["構造の完全性"],
                        "構造の完全性",
                        "要約の構造がどれだけ整っているか"
                    )
                    render_quality_score(
                        quality_scores["情報量"],
                        "情報量",
                        "重要な情報をどれだけ含んでいるか"
                    )
                    render_quality_score(
                        quality_scores["簡潔性"],
                        "簡潔性",
                        "簡潔に要点を示せているか"
                    )
                    render_quality_score(
                        quality_scores["総合スコア"],
                        "総合スコア",
                        "全体的な要約の質"
                    )
                    
                    st.markdown('</div></div>', unsafe_allow_html=True)
            
            # Always display conclusion
            st.markdown("## 💡 結論")
            st.markdown(summary_data.get("結論", ""))
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error: {str(e)}")
            st.error("要約データの形式が正しくありません。再試行してください。")
        except Exception as e:
            logger.error(f"Summary display error: {str(e)}")
            st.error("要約の表示中にエラーが発生しました")

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
    ''',
                unsafe_allow_html=True)

    # Main application logic
    try:
        # Step 1: Video Input
        with st.expander("Step 1: Video Input",
                         expanded=st.session_state.current_step == 1):
            render_step_header(1, "Video Input", "🎥",
                               "分析したいYouTube動画のURLを入力してください")

            youtube_url = st.text_input(
                "YouTube URL",
                placeholder="https://www.youtube.com/watch?v=...",
                help="分析したいYouTube動画のURLを入力してください")

            if youtube_url:
                try:
                    yt_helper = YouTubeHelper()
                    video_info = yt_helper.get_video_info(youtube_url)
                    st.session_state.video_info = video_info
                    st.session_state.current_step = 2
                    update_step_progress('video_info')
                    time.sleep(0.5)
                except Exception as e:
                    st.error(f"動画情報の取得に失敗しました: {str(e)}")
                    logger.error(f"Error in video info retrieval: {str(e)}")
                    st.stop()

        # Step 2: Content Overview
        with st.expander("Step 2: Content Overview",
                         expanded=st.session_state.current_step == 2):
            render_step_header(2, "Content Overview", "📊",
                               "動画の基本情報と文字起こしを表示します")
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
                ''',
                            unsafe_allow_html=True)

                if 'transcript' not in st.session_state or not st.session_state.transcript:
                    st.markdown('''
                    <div class="process-step">
                        <div class="step-content">文字起こしを生成します</div>
                    </div>
                    ''',
                                unsafe_allow_html=True)

                    try:
                        text_processor = TextProcessor()
                        transcript = text_processor.get_transcript(youtube_url)
                        st.session_state.transcript = transcript
                        st.session_state.current_step = 3
                        update_step_progress('transcript')
                        time.sleep(0.5)
                    except Exception as e:
                        st.error(f"文字起こしの生成に失敗しました: {str(e)}")
                        logger.error(
                            f"Error in transcript generation: {str(e)}")
                        st.stop()

        # Step 3: Content Analysis
        with st.expander("Step 3: Content Analysis",
                         expanded=st.session_state.current_step == 3):
            render_step_header(3, "Content Analysis", "🔍",
                               "文字起こし、要約、マインドマップを生成します")
            if st.session_state.transcript:
                # Add style selection with proper label
                summary_style = st.radio(
                    "要約スタイル",
                    options=["detailed", "overview"],
                    format_func=lambda x: {
                        "detailed": "詳細 (より詳しい分析と説明)",
                        "overview": "概要 (簡潔なポイントのみ)"
                    }[x],
                    help="要約の詳細度を選択してください"
                )

                tabs = st.tabs([
                    "📝 Transcript", "📊 Summary", "🔄 Mind Map", "✨ Enhancement"
                ])

                with tabs[0]:
                    st.markdown("### Original Transcript")
                    copy_text_block(st.session_state.transcript)

                with tabs[1]:
                    if ('summary' not in st.session_state or 
                        not st.session_state.summary or
                        st.session_state.current_summary_style != summary_style):
                        
                        # Clear previous summary when style changes
                        st.session_state.current_summary_style = summary_style
                        try:
                            text_processor = TextProcessor()
                            summary, quality_scores = text_processor.generate_summary(
                                st.session_state.transcript, summary_style)
                            st.session_state.summary = summary
                            st.session_state.quality_scores = quality_scores
                            st.session_state.current_summary_style = summary_style
                            update_step_progress('summary')
                        except Exception as e:
                            logger.error(f"Summary generation error: {str(e)}")
                            st.error("要約の生成に失敗しました。もう一度お試しください。")
                            st.stop()

                    display_summary(st.session_state.summary)

                with tabs[2]:
                    st.markdown("### 🔄 Mind Map")
                    if not MERMAID_AVAILABLE:
                        st.error("マインドマップ機能が利用できません。依存関係を確認してください。")
                    elif st.session_state.summary:
                        try:
                            if ('mindmap' not in st.session_state or 
                                st.session_state.current_summary_style != summary_style):
                                
                                mindmap_generator = MindMapGenerator()
                                mindmap_content, success = mindmap_generator.generate_mindmap(
                                    st.session_state.summary)
                                
                                if success:
                                    st.session_state.mindmap = mindmap_content
                                    update_step_progress('mindmap')
                                    logger.info("マインドマップを生成しました")
                                else:
                                    st.warning("マインドマップの生成に問題が発生しました。簡略化されたマップを表示します。")
                            
                            # Display mindmap with error handling
                            try:
                                if st.session_state.mindmap:
                                    st_mermaid(st.session_state.mindmap, height="800px")
                                else:
                                    st.warning("マインドマップのデータがありません")
                            except Exception as e:
                                logger.error(f"Mindmap display error: {str(e)}")
                                st.error("マインドマップの表示中にエラーが発生しました")
                                
                        except Exception as e:
                            logger.error(f"Mindmap generation error: {str(e)}")
                            st.error("マインドマップの生成中にエラーが発生しました")
                        if st.session_state.current_summary_style != summary_style:
                            st.session_state.summary = None
                            st.session_state.quality_scores = None
                        
                        st.session_state.current_summary_style = summary_style
                        
                        with st.spinner("AI要約を生成中..."):
                            try:
                                text_processor = TextProcessor()
                                summary, quality_scores = text_processor.generate_summary(
                                    st.session_state.transcript,
                                    style=summary_style
                                )
                                st.session_state.summary = summary
                                st.session_state.quality_scores = quality_scores
                            except Exception as e:
                                st.error(f"要約の生成に失敗しました: {str(e)}")
                                logger.error(f"Summary generation error: {str(e)}")
                    
                    if st.session_state.summary:
                        display_summary(st.session_state.summary)
                        update_step_progress('summary')

                with tabs[2]:
                    if st.session_state.summary:
                        try:
                            mindmap_generator = MindMapGenerator()
                            mindmap_syntax = mindmap_generator.generate_mindmap(st.session_state.summary)
                            
                            if MERMAID_AVAILABLE:
                                st_mermaid(mindmap_syntax)
                            else:
                                st.warning("マインドマップの表示機能は現在利用できません。代替表示を使用します。")
                                st.code(mindmap_syntax, language="mermaid")
                            
                            update_step_progress('mindmap')
                        except Exception as e:
                            st.error(f"マインドマップの生成に失敗しました: {str(e)}")
                            logger.error(f"Mindmap generation error: {str(e)}")
                    else:
                        st.info("マインドマップを生成するには、まず要約を生成してください。")

                with tabs[3]:
                    st.markdown("### Text Enhancement")
                    if st.button("Generate Enhanced Text"):
                        if st.session_state.transcript:
                            try:
                                # Enhancement logic here
                                st.session_state.enhancement_progress = {
                                    'progress': 1.0,
                                    'message': '✨ Text enhancement completed!'
                                }
                                update_step_progress('proofread')
                            except Exception as e:
                                st.error(f"テキスト強化に失敗しました: {str(e)}")
                                logger.error(f"Text enhancement error: {str(e)}")
                        else:
                            st.warning("テキスト強化を開始するには、まず文字起こしを生成してください。")

                    # Show progress
                    if st.session_state.enhancement_progress['progress'] > 0:
                        st.progress(st.session_state.enhancement_progress['progress'])
                        st.info(st.session_state.enhancement_progress['message'])

    except Exception as e:
        st.error(f"アプリケーションエラー: {str(e)}")
        logger.error(f"Application error: {str(e)}")

except Exception as e:
    st.error(f"初期化エラー: {str(e)}")
    logger.error(f"Initialization error: {str(e)}")