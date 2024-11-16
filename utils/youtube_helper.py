from googleapiclient.discovery import build
from datetime import datetime
import isodate
import re
import os

class YouTubeHelper:
    def __init__(self):
        api_key = os.environ.get('YOUTUBE_API_KEY')
        if not api_key:
            raise ValueError("YouTube API key is not set in environment variables")
        self.youtube = build('youtube', 'v3', developerKey=api_key)

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

        # Get video and channel details
        video_request = self.youtube.videos().list(
            part="snippet,contentDetails,statistics",
            id=video_id
        )
        video_response = video_request.execute()

        if not video_response['items']:
            raise ValueError("動画が見つかりませんでした")

        video = video_response['items'][0]
        snippet = video['snippet']
        content_details = video['contentDetails']
        statistics = video['statistics']

        # Get channel details
        channel_request = self.youtube.channels().list(
            part="statistics",
            id=snippet['channelId']
        )
        channel_response = channel_request.execute()
        channel_statistics = channel_response['items'][0]['statistics']

        # ISO 8601形式の期間を読みやすい形式に変換
        duration = isodate.parse_duration(content_details['duration'])
        duration_str = str(duration).split('.')[0]  # マイクロ秒を除去

        # Format view count with Japanese counter suffix
        def format_count(count):
            count = int(count)
            if count >= 10000:
                return f"{count//10000}万"
            return str(count)

        return {
            'title': snippet['title'],
            'channel_title': snippet['channelTitle'],
            'published_at': datetime.strptime(snippet['publishedAt'], '%Y-%m-%dT%H:%M:%SZ').strftime('%Y年%m月%d日'),
            'duration': duration_str,
            'thumbnail_url': snippet['thumbnails']['high']['url'],
            'video_url': f"https://youtube.com/watch?v={video_id}",
            'view_count': format_count(statistics.get('viewCount', '0')),
            'subscriber_count': format_count(channel_statistics.get('subscriberCount', '0')),
        }
