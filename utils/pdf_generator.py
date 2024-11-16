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
            # フォントをダウンロード
            font_url = "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/Japanese/NotoSansJP-Regular.otf"
            logger.info("日本語フォントのダウンロードを開始します")
            response = requests.get(font_url)
            
            if response.status_code == 200:
                font_path = "/tmp/NotoSansJP-Regular.otf"
                with open(font_path, "wb") as f:
                    f.write(response.content)
                logger.info(f"フォントを保存しました: {font_path}")
                
                # フォントを登録
                pdfmetrics.registerFont(TTFont('NotoSansJP', font_path))
                addMapping('NotoSansJP', 0, 0, 'NotoSansJP')
                self.use_fallback_fonts = False
                logger.info("日本語フォントを正常に設定しました")
            else:
                raise Exception(f"フォントのダウンロードに失敗しました。ステータスコード: {response.status_code}")
        except Exception as e:
            logger.error(f"フォントの設定中にエラーが発生しました: {str(e)}")
            self.use_fallback_fonts = True

    def _setup_styles(self):
        """スタイルの設定"""
        self.styles = getSampleStyleSheet()
        
        # 基本フォント設定
        base_font = 'NotoSansJP' if not self.use_fallback_fonts else 'Helvetica'
        logger.info(f"使用するフォント: {base_font}")
        
        # 本文スタイル
        self.styles.add(ParagraphStyle(
            name='JapaneseBody',
            fontName=base_font,
            fontSize=10,
            leading=14,
            wordWrap='CJK',
            encoding='utf-8'
        ))
        
        # 見出しスタイル
        self.styles.add(ParagraphStyle(
            name='JapaneseHeading',
            fontName=base_font,
            fontSize=14,
            leading=16,
            wordWrap='CJK',
            encoding='utf-8',
            spaceAfter=20
        ))

    def create_pdf(self, video_info, transcript, summary, mindmap_image=None):
        """分析結果のPDFを生成"""
        try:
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(
                buffer,
                pagesize=A4,
                rightMargin=72,
                leftMargin=72,
                topMargin=72,
                bottomMargin=72,
                encoding='utf-8'
            )

            elements = []
            logger.info("PDFの生成を開始します")

            # タイトル
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=self.styles['Title'],
                fontName='NotoSansJP' if not self.use_fallback_fonts else 'Helvetica',
                fontSize=24,
                spaceAfter=30,
                alignment=1,
                encoding='utf-8'
            )
            elements.append(Paragraph("YouTube動画分析レポート", title_style))
            elements.append(Spacer(1, 20))

            # 動画情報
            elements.append(Paragraph("動画情報", self.styles['JapaneseHeading']))
            
            # 動画情報テーブル
            data = [
                ['タイトル', video_info['title'].encode('utf-8').decode('utf-8')],
                ['チャンネル', video_info['channel_title'].encode('utf-8').decode('utf-8')],
                ['投稿日', video_info['published_at'].encode('utf-8').decode('utf-8')],
                ['動画時間', video_info['duration'].encode('utf-8').decode('utf-8')]
            ]
            
            table = Table(data, colWidths=[100, 400])
            table.setStyle(TableStyle([
                ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, -1), 'NotoSansJP' if not self.use_fallback_fonts else 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('PADDING', (0, 0), (-1, -1), 6),
            ]))
            elements.append(table)
            elements.append(Spacer(1, 20))

            # サムネイル
            if 'thumbnail_url' in video_info:
                try:
                    logger.info("サムネイル画像の取得を開始します")
                    response = requests.get(video_info['thumbnail_url'])
                    if response.status_code == 200:
                        thumbnail_data = response.content
                        thumbnail_buffer = io.BytesIO(thumbnail_data)
                        img = Image(thumbnail_buffer, width=400, height=225)
                        elements.append(img)
                        elements.append(Spacer(1, 20))
                        logger.info("サムネイル画像を追加しました")
                except Exception as e:
                    logger.error(f"サムネイル画像の取得に失敗しました: {str(e)}")

            # 文字起こし
            logger.info("文字起こしの追加を開始します")
            elements.append(Paragraph("文字起こし", self.styles['JapaneseHeading']))
            # テキストを適切なサイズのチャンクに分割
            max_chars = 1000
            chunks = [transcript[i:i+max_chars] for i in range(0, len(transcript), max_chars)]
            for chunk in chunks:
                text = chunk.encode('utf-8').decode('utf-8')
                elements.append(Paragraph(text, self.styles['JapaneseBody']))
                elements.append(Spacer(1, 10))
            elements.append(Spacer(1, 20))

            # 要約
            logger.info("要約の追加を開始します")
            elements.append(Paragraph("AI要約", self.styles['JapaneseHeading']))
            summary_text = summary.encode('utf-8').decode('utf-8')
            elements.append(Paragraph(summary_text, self.styles['JapaneseBody']))
            elements.append(Spacer(1, 20))

            # マインドマップ
            if mindmap_image:
                try:
                    logger.info("マインドマップの追加を開始します")
                    elements.append(Paragraph("マインドマップ", self.styles['JapaneseHeading']))
                    mindmap_buffer = io.BytesIO(mindmap_image)
                    mindmap_buffer.seek(0)
                    drawing = svg2rlg(mindmap_buffer)
                    
                    if drawing:
                        scale_factor = min(0.7, (A4[0] - 2*72) / drawing.width)
                        drawing.scale(scale_factor, scale_factor)
                        elements.append(drawing)
                        elements.append(Spacer(1, 20))
                        logger.info("マインドマップを追加しました")
                except Exception as e:
                    logger.error(f"マインドマップの追加に失敗しました: {str(e)}")

            # PDFの生成
            logger.info("PDFのビルドを開始します")
            doc.build(elements)
            pdf_data = buffer.getvalue()
            buffer.close()
            logger.info("PDFの生成が完了しました")
            return pdf_data
            
        except Exception as e:
            error_msg = f"PDFの生成中にエラーが発生しました: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)
