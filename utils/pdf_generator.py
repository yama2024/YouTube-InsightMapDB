from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping
from svglib.svglib import svg2rlg
import os
import io
import requests
import logging
import re
import tempfile

# ロギングの設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PDFGenerator:
    def __init__(self):
        self._setup_fonts()
        self._setup_styles()

    def _setup_fonts(self):
        """日本語フォントのセットアップ"""
        try:
            # フォントファイルのダウンロードとセットアップ
            font_urls = {
                'regular': "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/Japanese/NotoSansJP-Regular.otf",
                'bold': "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/Japanese/NotoSansJP-Bold.otf"
            }
            
            font_files = {}
            for style, url in font_urls.items():
                response = requests.get(url)
                if response.status_code == 200:
                    # 一時ファイルにフォントを保存
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.otf') as f:
                        f.write(response.content)
                        font_files[style] = f.name

            # フォントの登録
            pdfmetrics.registerFont(TTFont('NotoSansJP-Regular', font_files['regular']))
            pdfmetrics.registerFont(TTFont('NotoSansJP-Bold', font_files['bold']))
            
            # フォントマッピングの設定
            addMapping('NotoSansJP-Regular', 0, 0, 'NotoSansJP-Regular')
            addMapping('NotoSansJP-Bold', 1, 0, 'NotoSansJP-Bold')
            
            self.use_fallback_fonts = False
            logger.info("日本語フォントの設定が完了しました")
            
        except Exception as e:
            logger.error(f"フォントの設定中にエラーが発生しました: {str(e)}")
            self.use_fallback_fonts = True

    def _encode_text(self, text):
        """テキストのエンコード処理"""
        if isinstance(text, str):
            return text.encode('utf-8').decode('utf-8')
        return str(text)

    def _setup_styles(self):
        """スタイルの設定"""
        self.styles = getSampleStyleSheet()
        
        # 基本フォント設定
        base_font = 'NotoSansJP-Regular' if not self.use_fallback_fonts else 'Helvetica'
        bold_font = 'NotoSansJP-Bold' if not self.use_fallback_fonts else 'Helvetica-Bold'
        
        # タイトルスタイル
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            fontName=bold_font,
            fontSize=24,
            leading=32,
            alignment=1,
            spaceAfter=30,
            wordWrap='CJK'
        ))
        
        # 見出しスタイル
        self.styles.add(ParagraphStyle(
            name='JapaneseHeading',
            fontName=bold_font,
            fontSize=16,
            leading=24,
            spaceBefore=20,
            spaceAfter=10,
            wordWrap='CJK'
        ))
        
        # 本文スタイル
        self.styles.add(ParagraphStyle(
            name='JapaneseBody',
            fontName=base_font,
            fontSize=10,
            leading=14,
            spaceBefore=6,
            spaceAfter=6,
            wordWrap='CJK'
        ))

    def create_pdf(self, video_info, transcript, summary, mindmap_image=None):
        """分析結果のPDFを生成"""
        try:
            # バッファの作成
            buffer = io.BytesIO()
            
            # PDFドキュメントの設定
            doc = SimpleDocTemplate(
                buffer,
                pagesize=A4,
                rightMargin=50,
                leftMargin=50,
                topMargin=50,
                bottomMargin=50,
                encoding='utf-8'
            )

            # 要素の生成
            elements = []
            logger.info("PDFの生成を開始します")

            # タイトル
            elements.append(Paragraph("YouTube動画分析レポート", self.styles['CustomTitle']))

            # 動画情報セクション
            elements.append(Paragraph("動画情報", self.styles['JapaneseHeading']))
            
            # 動画情報テーブル
            data = [
                ['タイトル', self._encode_text(video_info['title'])],
                ['チャンネル', self._encode_text(video_info['channel_title'])],
                ['投稿日', self._encode_text(video_info['published_at'])],
                ['動画時間', self._encode_text(video_info['duration'])]
            ]
            
            # テーブルスタイルの改善
            table = Table(data, colWidths=[100, 400])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F0F2F6')),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#1B365D')),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (0, -1), 'NotoSansJP-Bold' if not self.use_fallback_fonts else 'Helvetica-Bold'),
                ('FONTNAME', (1, 0), (-1, -1), 'NotoSansJP-Regular' if not self.use_fallback_fonts else 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#E2E8F0')),
            ]))
            elements.append(table)
            elements.append(Spacer(1, 20))

            # サムネイル画像
            if 'thumbnail_url' in video_info:
                try:
                    response = requests.get(video_info['thumbnail_url'])
                    if response.status_code == 200:
                        thumbnail_data = response.content
                        thumbnail_buffer = io.BytesIO(thumbnail_data)
                        img = Image(thumbnail_buffer, width=400, height=225)
                        elements.append(img)
                        elements.append(Spacer(1, 20))
                except Exception as e:
                    logger.error(f"サムネイル画像の取得に失敗しました: {str(e)}")

            # AI要約セクション
            elements.append(Paragraph("AI要約", self.styles['JapaneseHeading']))
            summary_paragraphs = summary.split('\n')
            for paragraph in summary_paragraphs:
                if paragraph.strip():
                    elements.append(Paragraph(self._encode_text(paragraph), self.styles['JapaneseBody']))
            elements.append(Spacer(1, 20))

            # 文字起こしセクション
            elements.append(Paragraph("文字起こし", self.styles['JapaneseHeading']))
            # テキストを適切なサイズのチャンクに分割
            max_chars = 800
            chunks = [transcript[i:i+max_chars] for i in range(0, len(transcript), max_chars)]
            for chunk in chunks:
                elements.append(Paragraph(self._encode_text(chunk), self.styles['JapaneseBody']))

            # マインドマップ
            if mindmap_image:
                try:
                    elements.append(Paragraph("マインドマップ", self.styles['JapaneseHeading']))
                    mindmap_buffer = io.BytesIO(mindmap_image)
                    mindmap_buffer.seek(0)
                    
                    # SVGをReportLab描画オブジェクトに変換
                    drawing = svg2rlg(mindmap_buffer)
                    if drawing:
                        # 適切なサイズにスケーリング
                        scale_factor = min(0.75, (A4[0] - 100) / drawing.width)
                        drawing.scale(scale_factor, scale_factor)
                        drawing.height = drawing.height * scale_factor
                        drawing.width = drawing.width * scale_factor
                        
                        elements.append(drawing)
                except Exception as e:
                    logger.error(f"マインドマップの追加に失敗しました: {str(e)}")

            # PDFの生成
            doc.build(elements)
            
            # バッファの位置を先頭に戻す
            buffer.seek(0)
            
            # PDFデータを取得
            pdf_data = buffer.getvalue()
            
            # バッファをクローズ
            buffer.close()
            
            # 一時ファイルの削除
            try:
                for font_file in getattr(self, '_font_files', {}).values():
                    if os.path.exists(font_file):
                        os.remove(font_file)
            except Exception as e:
                logger.error(f"一時ファイルの削除中にエラーが発生しました: {str(e)}")

            return pdf_data

        except Exception as e:
            error_msg = f"PDFの生成中にエラーが発生しました: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)
