from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping
import os
import io
import requests
import logging
import re

# ロギングの設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PDFGenerator:
    def __init__(self):
        self._setup_fonts()
        self._setup_styles()

    def _setup_fonts(self):
        try:
            # Google Fonts APIから直接フォントをダウンロード
            font_url = "https://fonts.googleapis.com/css2?family=Noto+Sans+JP&display=swap"
            response = requests.get(font_url)
            if response.status_code == 200:
                # フォントファイルのURLを抽出
                font_file_url = re.search(r'src: url\((.*?)\)', response.text)
                if font_file_url:
                    font_response = requests.get(font_file_url.group(1))
                    if font_response.status_code == 200:
                        font_path = "/tmp/NotoSansJP-Regular.ttf"
                        with open(font_path, "wb") as f:
                            f.write(font_response.content)
                        
                        # フォントを登録
                        pdfmetrics.registerFont(TTFont('NotoSansJP', font_path))
                        addMapping('NotoSansJP', 0, 0, 'NotoSansJP')
                        self.use_fallback_fonts = False
                        logger.info("日本語フォントを正常に設定しました")
                        return
            
            # 代替方法：直接Noto Sans JPのwoffファイルを使用
            alt_font_url = "https://fonts.gstatic.com/s/notosansjp/v52/-F6jfjtqLzI2JPCgQBnw7HFyzSD-AsregP8VFBEj75s.woff2"
            response = requests.get(alt_font_url)
            if response.status_code == 200:
                font_path = "/tmp/NotoSansJP-Regular.ttf"
                with open(font_path, "wb") as f:
                    f.write(response.content)
                
                pdfmetrics.registerFont(TTFont('NotoSansJP', font_path))
                addMapping('NotoSansJP', 0, 0, 'NotoSansJP')
                self.use_fallback_fonts = False
                logger.info("代替方法で日本語フォントを設定しました")
            else:
                raise Exception("フォントのダウンロードに失敗しました")
        except Exception as e:
            logger.error(f"フォントの設定中にエラーが発生しました: {str(e)}")
            self.use_fallback_fonts = True

    def _encode_text(self, text):
        try:
            return text.encode('utf-8').decode('utf-8')
        except Exception as e:
            logger.error(f"テキストエンコーディングエラー: {str(e)}")
            return text

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

    def create_pdf(self, video_info, transcript, summary, proofread_text=''):
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

            # Validate required content
            if not transcript or not summary:
                raise ValueError("必須コンテンツ(文字起こしまたは要約)が不足しています")

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
                ['タイトル', self._encode_text(video_info['title'])],
                ['チャンネル', self._encode_text(video_info['channel_title'])],
                ['投稿日', self._encode_text(video_info['published_at'])],
                ['動画時間', self._encode_text(video_info['duration'])]
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
            max_chars = 1000
            transcript_chunks = [transcript[i:i+max_chars] for i in range(0, len(transcript), max_chars)]
            for chunk in transcript_chunks:
                elements.append(Paragraph(self._encode_text(chunk), self.styles['JapaneseBody']))
            elements.append(Spacer(1, 20))

            # 要約
            logger.info("要約の追加を開始します")
            elements.append(Paragraph("AI要約", self.styles['JapaneseHeading']))
            elements.append(Paragraph(self._encode_text(summary), self.styles['JapaneseBody']))
            elements.append(Spacer(1, 20))

            # 校閲済みテキスト
            if proofread_text:
                logger.info("校閲済みテキストの追加を開始します")
                elements.append(Paragraph("校閲済みテキスト", self.styles['JapaneseHeading']))
                proofread_chunks = [proofread_text[i:i+max_chars] for i in range(0, len(proofread_text), max_chars)]
                for chunk in proofread_chunks:
                    elements.append(Paragraph(self._encode_text(chunk), self.styles['JapaneseBody']))
                elements.append(Spacer(1, 20))

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