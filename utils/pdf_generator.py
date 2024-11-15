from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily
import os
import io

class PDFGenerator:
    def __init__(self):
        # カスタムスタイルの設定
        self.styles = getSampleStyleSheet()
        self.styles.add(ParagraphStyle(
            name='JapaneseBody',
            fontName='Courier',  # Use built-in font with better CJK support
            fontSize=10,
            leading=14,
            wordWrap='CJK'
        ))
        self.styles.add(ParagraphStyle(
            name='JapaneseHeading',
            fontName='Courier-Bold',  # Use built-in font with better CJK support
            fontSize=14,
            leading=16,
            wordWrap='CJK',
            spaceAfter=20
        ))

    def create_pdf(self, video_info, transcript, summary, mindmap_image_path=None):
        """分析結果のPDFを生成"""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=72
        )

        # PDF要素のリスト
        elements = []

        # タイトル
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=self.styles['Title'],
            fontName='Courier-Bold',
            fontSize=24,
            spaceAfter=30,
            alignment=1
        )
        elements.append(Paragraph("YouTube動画分析レポート", title_style))
        elements.append(Spacer(1, 20))

        # 動画情報
        elements.append(Paragraph("動画情報", self.styles['JapaneseHeading']))
        video_info_data = [
            ['タイトル', video_info['title']],
            ['チャンネル', video_info['channel_title']],
            ['投稿日', video_info['published_at']],
            ['動画時間', video_info['duration']]
        ]
        video_info_table = Table(video_info_data, colWidths=[100, 400])
        video_info_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Courier'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(video_info_table)
        elements.append(Spacer(1, 20))

        # サムネイル画像
        if 'thumbnail_url' in video_info:
            try:
                import requests
                thumbnail_data = requests.get(video_info['thumbnail_url']).content
                thumbnail_buffer = io.BytesIO(thumbnail_data)
                img = Image(thumbnail_buffer, width=400, height=225)  # 16:9 aspect ratio
                elements.append(img)
                elements.append(Spacer(1, 20))
            except Exception as e:
                print(f"サムネイル画像の取得に失敗しました: {str(e)}")

        # 文字起こし
        elements.append(Paragraph("文字起こし", self.styles['JapaneseHeading']))
        # Split transcript into smaller paragraphs for better readability
        transcript_paragraphs = transcript.split('\n\n')
        for para in transcript_paragraphs:
            if para.strip():
                elements.append(Paragraph(para.strip(), self.styles['JapaneseBody']))
                elements.append(Spacer(1, 10))
        elements.append(Spacer(1, 20))

        # 要約
        elements.append(Paragraph("AI要約", self.styles['JapaneseHeading']))
        # Split summary into paragraphs if it contains line breaks
        summary_paragraphs = summary.split('\n')
        for para in summary_paragraphs:
            if para.strip():
                elements.append(Paragraph(para.strip(), self.styles['JapaneseBody']))
                elements.append(Spacer(1, 10))
        elements.append(Spacer(1, 20))

        # マインドマップ画像
        if mindmap_image_path:
            elements.append(Paragraph("マインドマップ", self.styles['JapaneseHeading']))
            try:
                img = Image(mindmap_image_path, width=500, height=375)  # 4:3 aspect ratio
                elements.append(img)
            except Exception as e:
                print(f"マインドマップ画像の追加に失敗しました: {str(e)}")

        # PDFの生成
        doc.build(elements)
        pdf_data = buffer.getvalue()
        buffer.close()
        return pdf_data
