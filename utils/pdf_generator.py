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

class PDFGenerator:
    def __init__(self):
        self._setup_fonts()
        self._setup_styles()

    def _setup_fonts(self):
        """日本語フォントのセットアップ"""
        try:
            # Noto Sans JPフォントの登録
            font_path = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
            font_bold_path = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"

            # 通常フォントの登録
            pdfmetrics.registerFont(TTFont('NotoSansJP', font_path))
            # 太字フォントの登録
            pdfmetrics.registerFont(TTFont('NotoSansJP-Bold', font_bold_path))

            # フォントファミリーの設定
            addMapping('NotoSansJP', 0, 0, 'NotoSansJP')  # 通常
            addMapping('NotoSansJP', 1, 0, 'NotoSansJP-Bold')  # 太字

        except Exception as e:
            print(f"フォントの設定中にエラーが発生しました: {str(e)}")
            # フォールバックフォントとしてHelveticaを使用
            self.use_fallback_fonts = True
            print("フォールバックフォントを使用します")

    def _setup_styles(self):
        """スタイルの設定"""
        self.styles = getSampleStyleSheet()
        
        # 基本フォント設定
        base_font = 'NotoSansJP' if hasattr(self, 'use_fallback_fonts') is False else 'Helvetica'
        base_font_bold = 'NotoSansJP-Bold' if hasattr(self, 'use_fallback_fonts') is False else 'Helvetica-Bold'

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
            fontName=base_font_bold,
            fontSize=14,
            leading=16,
            wordWrap='CJK',
            encoding='utf-8',
            spaceAfter=20
        ))

    def _create_header(self, title):
        """ヘッダーの作成"""
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=self.styles['Title'],
            fontName='NotoSansJP-Bold' if hasattr(self, 'use_fallback_fonts') is False else 'Helvetica-Bold',
            fontSize=24,
            spaceAfter=30,
            alignment=1,
            encoding='utf-8'
        )
        return Paragraph(title, title_style)

    def _create_info_table(self, video_info):
        """動画情報テーブルの作成"""
        data = [
            ['タイトル', video_info['title']],
            ['チャンネル', video_info['channel_title']],
            ['投稿日', video_info['published_at']],
            ['動画時間', video_info['duration']]
        ]
        
        base_font = 'NotoSansJP' if hasattr(self, 'use_fallback_fonts') is False else 'Helvetica'
        
        table = Table(data, colWidths=[100, 400])
        table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), base_font),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('PADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        return table

    def _add_thumbnail(self, elements, video_info):
        """サムネイル画像の追加"""
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
                print(f"サムネイル画像の取得に失敗しました: {str(e)}")

    def _add_text_content(self, elements, text, style, title=None):
        """テキストコンテンツの追加"""
        if title:
            elements.append(Paragraph(title, self.styles['JapaneseHeading']))
        
        try:
            # テキストを適切なサイズのチャンクに分割
            paragraphs = text.split('\n')
            for para in paragraphs:
                if para.strip():
                    elements.append(Paragraph(para.strip(), style))
                    elements.append(Spacer(1, 10))
            elements.append(Spacer(1, 20))
        except Exception as e:
            print(f"テキストコンテンツの追加中にエラーが発生しました: {str(e)}")
            # 基本的なテキスト追加を試行
            elements.append(Paragraph(text, style))
            elements.append(Spacer(1, 20))

    def _add_mindmap(self, elements, mindmap_image):
        """マインドマップの追加"""
        if mindmap_image:
            elements.append(Paragraph("マインドマップ", self.styles['JapaneseHeading']))
            try:
                mindmap_buffer = io.BytesIO(mindmap_image)
                mindmap_buffer.seek(0)
                drawing = svg2rlg(mindmap_buffer)
                
                if drawing:
                    # ページ幅に合わせてスケール調整
                    scale_factor = min(0.7, (A4[0] - 2*72) / drawing.width)
                    drawing.scale(scale_factor, scale_factor)
                    elements.append(drawing)
                    elements.append(Spacer(1, 20))
            except Exception as e:
                print(f"マインドマップ画像の追加に失敗しました: {str(e)}")

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
            
            # タイトルの追加
            elements.append(self._create_header("YouTube動画分析レポート"))
            elements.append(Spacer(1, 20))
            
            # 動画情報の追加
            elements.append(Paragraph("動画情報", self.styles['JapaneseHeading']))
            elements.append(self._create_info_table(video_info))
            elements.append(Spacer(1, 20))
            
            # サムネイルの追加
            self._add_thumbnail(elements, video_info)
            
            # 文字起こしの追加
            self._add_text_content(
                elements,
                transcript,
                self.styles['JapaneseBody'],
                "文字起こし"
            )
            
            # 要約の追加
            self._add_text_content(
                elements,
                summary,
                self.styles['JapaneseBody'],
                "AI要約"
            )
            
            # マインドマップの追加
            self._add_mindmap(elements, mindmap_image)

            # PDFの生成
            doc.build(elements)
            pdf_data = buffer.getvalue()
            buffer.close()
            return pdf_data
            
        except Exception as e:
            error_msg = f"PDFの生成中にエラーが発生しました: {str(e)}"
            print(error_msg)
            raise Exception(error_msg)
