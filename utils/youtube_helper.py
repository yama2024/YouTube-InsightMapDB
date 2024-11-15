from googleapiclient.discovery import build
from datetime import datetime
import isodate
import re

class YouTubeHelper:
    def __init__(self):
        self.youtube = build('youtube', 'v3', developerKey='YOUR_API_KEY')

    def extract_video_id(self, url):
        """URLからビデオIDを抽出"""
        video_id_match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', url)
        if video_id_match:
            return video_id_match.group(1)
        return None

    def get_video_info(self, url):
        """動画の詳細情報を取得"""
        video_id = self.extract_video_id(url)
        if not video_id:
            raise ValueError("無効なYouTube URLです")

        request = self.youtube.videos().list(
            part="snippet,contentDetails",
            id=video_id
        )
        response = request.execute()

        if not response['items']:
            raise ValueError("動画が見つかりませんでした")

        video = response['items'][0]
        snippet = video['snippet']
        content_details = video['contentDetails']

        # ISO 8601形式の期間を読みやすい形式に変換
        duration = isodate.parse_duration(content_details['duration'])
        duration_str = str(duration).split('.')[0]  # マイクロ秒を除去

        return {
            'title': snippet['title'],
            'channel_title': snippet['channelTitle'],
            'published_at': datetime.strptime(snippet['publishedAt'], '%Y-%m-%dT%H:%M:%SZ').strftime('%Y年%m月%d日'),
            'duration': duration_str,
            'thumbnail_url': snippet['thumbnails']['high']['url']
        }
