from googleapiclient.discovery import build
from datetime import datetime
import isodate
import re
import os
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class YouTubeHelper:
    def __init__(self):
        api_key = os.environ.get('YOUTUBE_API_KEY')
        if not api_key:
            raise ValueError("YouTube API key is not set in environment variables")
        self.youtube = build('youtube', 'v3', developerKey=api_key)
        self._cache = {}

    def extract_video_id(self, url):
        """URLからビデオIDを抽出"""
        if "youtu.be" in url:
            video_id = url.split("/")[-1].split("?")[0]
        else:
            video_id = None
            patterns = [
                r"(?:v=|\/)([0-9A-Za-z_-]{11}).*",
                r"(?:embed\/)([0-9A-Za-z_-]{11})",
                r"(?:watch\?v=)([0-9A-Za-z_-]{11})"
            ]
            for pattern in patterns:
                match = re.search(pattern, url)
                if match:
                    video_id = match.group(1)
                    break

        if not video_id:
            raise ValueError("無効なYouTube URLです")
        return video_id

    def get_video_info(self, url):
        """動画の詳細情報を取得"""
        try:
            video_id = self.extract_video_id(url)
            
            # Check cache first
            cache_key = f"video_info_{video_id}"
            if cache_key in self._cache:
                return self._cache[cache_key]

            # Get video and channel details
            video_request = self.youtube.videos().list(
                part="snippet,contentDetails,statistics",
                id=video_id
            )
            video_response = video_request.execute()

            if not video_response.get('items'):
                raise ValueError("動画が見つかりませんでした")

            video = video_response['items'][0]
            snippet = video['snippet']
            content_details = video['contentDetails']
            statistics = video.get('statistics', {})

            # Get channel details
            channel_request = self.youtube.channels().list(
                part="statistics",
                id=snippet['channelId']
            )
            channel_response = channel_request.execute()
            
            if not channel_response.get('items'):
                raise ValueError("チャンネル情報が取得できませんでした")
                
            channel_statistics = channel_response['items'][0]['statistics']

            # ISO 8601形式の期間を読みやすい形式に変換
            duration = isodate.parse_duration(content_details['duration'])
            duration_str = str(duration).split('.')[0]  # マイクロ秒を除去

            # Format view count with Japanese counter suffix
            def format_count(count):
                try:
                    count = int(count)
                    if count >= 10000:
                        return f"{count//10000}万"
                    return str(count)
                except (ValueError, TypeError):
                    return "0"

            video_info = {
                'title': snippet.get('title', '無題'),
                'channel_title': snippet.get('channelTitle', '不明'),
                'published_at': datetime.strptime(
                    snippet['publishedAt'], 
                    '%Y-%m-%dT%H:%M:%SZ'
                ).strftime('%Y年%m月%d日'),
                'duration': duration_str,
                'thumbnail_url': snippet.get('thumbnails', {}).get('high', {}).get('url', ''),
                'video_url': f"https://youtube.com/watch?v={video_id}",
                'view_count': format_count(statistics.get('viewCount', '0')),
                'subscriber_count': format_count(channel_statistics.get('subscriberCount', '0')),
            }

            # Cache the result
            self._cache[cache_key] = video_info
            return video_info

        except Exception as e:
            logger.error(f"動画情報の取得中にエラーが発生しました: {str(e)}")
            raise Exception(f"動画情報の取得に失敗しました: {str(e)}")
