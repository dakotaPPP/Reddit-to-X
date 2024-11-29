import os
import json
import time
import schedule
import praw
import tweepy
import requests
import openai
from pathlib import Path
from dotenv import load_dotenv
import random
import subprocess
from moviepy.editor import VideoFileClip
import yt_dlp

# Load environment variables
load_dotenv()

# Initialize Reddit API
reddit = praw.Reddit(
    client_id=os.getenv('REDDIT_CLIENT_ID'),
    client_secret=os.getenv('REDDIT_CLIENT_SECRET'),
    user_agent="RedditTwitterBot/1.0"
)

# Initialize Twitter API v2 and v1.1
twitter_client = tweepy.Client(
    consumer_key=os.getenv('TWITTER_API_KEY'),
    consumer_secret=os.getenv('TWITTER_API_SECRET'),
    access_token=os.getenv('TWITTER_ACCESS_TOKEN'),
    access_token_secret=os.getenv('TWITTER_ACCESS_TOKEN_SECRET')
)

# Initialize Twitter API v1.1 for media upload
twitter_auth = tweepy.OAuth1UserHandler(
    os.getenv('TWITTER_API_KEY'),
    os.getenv('TWITTER_API_SECRET'),
    os.getenv('TWITTER_ACCESS_TOKEN'),
    os.getenv('TWITTER_ACCESS_TOKEN_SECRET')
)
twitter_api = tweepy.API(twitter_auth)

# Initialize OpenAI
openai.api_key = os.getenv('OPENAI_API_KEY')

# Configuration
SUBREDDITS = [
    'TikTokCringe',
    'mildlyinfuriating',
    'clevercomebacks',
    'interestingasfuck',
    'nextfuckinglevel',
    'aww',
    'ArchitecturePorn'
    # Add more subreddits here
]
POSTS_FILE = 'posts_data.json'
MEDIA_DIR = Path('media')
MEDIA_DIR.mkdir(exist_ok=True)

class RedditPost:
    def __init__(self, post, from_json=False):
        """Initialize RedditPost with either a PRAW submission object or JSON data."""
        if from_json:
            self.id = post.id
            self.title = post.title
            self.url = post.url
            self.subreddit = post.subreddit
            self.used = post.used
            self.media_path = post.media_path
            self.created_utc = post.created_utc
        else:
            self.id = post.id
            self.title = post.title
            self.url = post.url
            self.subreddit = post.subreddit.display_name
            self.used = False
            self.media_path = None
            self.created_utc = post.created_utc

def optimize_title(original_title):
    """Use ChatGPT to optimize the title for Twitter."""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", 
                "content": """Original title: {original_title}

                    Create a Twitter-optimized version of this title that:
                    1. Is attention-grabbing and engaging
                    2. Uses SEO-friendly keywords
                    3. Keep it brief and don't be afraid to use profanity
                    4. Is under 100 characters
                    5. Maintains the original meaning but makes it more compelling
                    6. Avoids clickbait or sensationalism
                    7. Is written in a natural, conversational tone
                    8. Please don't use punctuation
                    9. type in all lower case
                    10. You are a zoomer social media pro on the internet
                    11. Don't use emojis or hashtags
                    12. Do not use the word vibe nor vibes
                    13. Do not write in 1st person, the post should always be 'this guy' 'these dudes' 'this girl' etc.
                    Respond with only the optimized title."""},
                {"role": "user", "content": original_title}
            ]
        )
        return response.choices[0].message['content'].strip()
    except Exception as e:
        print(f"Error optimizing title: {e}")
        return original_title

def download_media(url, post_id):
    """Download media from Reddit post."""
    try:
        # For images and GIFs
        if url.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
            response = requests.get(url)
            if response.status_code == 200:
                extension = url.split('.')[-1].lower()
                file_path = MEDIA_DIR / f"{post_id}.{extension}"
                with open(file_path, 'wb') as f:
                    f.write(response.content)
                return str(file_path)
        
        # For Reddit-hosted videos
        elif 'v.redd.it' in url:
            print(f"Downloading Reddit video from URL: {url}")
            temp_video_path = str(MEDIA_DIR / f'{post_id}_temp_video.mp4')
            temp_audio_path = str(MEDIA_DIR / f'{post_id}_temp_audio.mp4')
            output_path = str(MEDIA_DIR / f'{post_id}.mp4')
            
            try:
                # Get the submission using PRAW
                submission = reddit.submission(id=post_id)
                
                # Get the secure media info
                if hasattr(submission, 'secure_media') and submission.secure_media:
                    video_data = submission.secure_media['reddit_video']
                    
                    # Try to get HLS URL first
                    hls_url = video_data.get('hls_url')
                    if hls_url:
                        print("Using HLS stream URL")
                        headers = {
                            'User-Agent': f'python:reddit-to-twitter:v1.0 (by /u/{os.getenv("REDDIT_USERNAME")})'
                        }
                        
                        # Download using FFmpeg directly from HLS stream
                        cmd = [
                            'ffmpeg', '-y',
                            '-headers', f'User-Agent: {headers["User-Agent"]}',
                            '-i', hls_url,
                            '-c', 'copy',
                            output_path
                        ]
                        
                        result = subprocess.run(cmd, capture_output=True)
                        if result.returncode == 0:
                            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                                print(f"Video downloaded successfully using HLS. Size: {os.path.getsize(output_path)} bytes")
                                return output_path
                        else:
                            print(f"FFmpeg HLS error: {result.stderr.decode()}")
                    
                    # Fallback to direct download if HLS fails
                    print("Falling back to direct download...")
                    video_url = video_data['fallback_url']
                    
                    headers = {
                        'User-Agent': f'python:reddit-to-twitter:v1.0 (by /u/{os.getenv("REDDIT_USERNAME")})'
                    }
                    
                    # Download video
                    print("Downloading video stream...")
                    response = requests.get(video_url, headers=headers)
                    if response.status_code == 200:
                        with open(temp_video_path, 'wb') as f:
                            f.write(response.content)
                    else:
                        print(f"Failed to download video: {response.status_code}")
                        return None
                    
                    # Try different audio URL patterns
                    has_audio = False
                    base_url = video_url.rsplit('/', 1)[0]
                    audio_urls = [
                        f"{base_url}/DASH_audio.mp4",
                        f"{base_url}/audio",
                        video_url.replace('DASH_720.mp4', 'DASH_audio.mp4')
                            .replace('DASH_1080.mp4', 'DASH_audio.mp4')
                            .replace('DASH_480.mp4', 'DASH_audio.mp4')
                            .replace('DASH_360.mp4', 'DASH_audio.mp4')
                            .replace('DASH_240.mp4', 'DASH_audio.mp4')
                    ]
                    
                    print("Trying to download audio stream...")
                    for audio_url in audio_urls:
                        print(f"Attempting audio URL: {audio_url}")
                        response = requests.get(audio_url, headers=headers)
                        if response.status_code == 200:
                            print(f"Successfully found audio at: {audio_url}")
                            with open(temp_audio_path, 'wb') as f:
                                f.write(response.content)
                            has_audio = True
                            break
                        else:
                            print(f"Failed to get audio from {audio_url}: {response.status_code}")
                    
                    # Combine video and audio if both exist
                    if has_audio and os.path.exists(temp_video_path) and os.path.exists(temp_audio_path):
                        print("Combining video and audio streams...")
                        cmd = [
                            'ffmpeg', '-y',
                            '-i', temp_video_path,
                            '-i', temp_audio_path,
                            '-c:v', 'copy',
                            '-c:a', 'aac',
                            '-shortest',
                            output_path
                        ]
                        result = subprocess.run(cmd, capture_output=True)
                        if result.returncode != 0:
                            print(f"FFmpeg error: {result.stderr.decode()}")
                            # If combining fails, just use the video
                            os.rename(temp_video_path, output_path)
                    else:
                        print("No audio found or audio download failed, using video only")
                        # Just use video if no audio
                        os.rename(temp_video_path, output_path)
                    
                    # Clean up temporary files
                    for path in [temp_video_path, temp_audio_path]:
                        if os.path.exists(path):
                            os.remove(path)
                    
                    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                        print(f"Video downloaded successfully. Size: {os.path.getsize(output_path)} bytes")
                        return output_path
                    
                print("Failed to download video")
                return None
                
            except Exception as e:
                print(f"Error downloading Reddit video: {str(e)}")
                # Clean up any temporary files
                for path in [temp_video_path, temp_audio_path]:
                    if os.path.exists(path):
                        os.remove(path)
                return None
        
        # For direct video links
        elif url.lower().endswith(('.mp4', '.mov', '.webm')):
            print(f"Downloading direct video from URL: {url}")
            output_path = str(MEDIA_DIR / f'{post_id}.mp4')
            
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                response = requests.get(url, headers=headers, stream=True)
                if response.status_code == 200:
                    with open(output_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    
                    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                        print(f"Video downloaded successfully. Size: {os.path.getsize(output_path)} bytes")
                        return output_path
            
            except Exception as e:
                print(f"Error downloading direct video: {str(e)}")
                return None
    
    except Exception as e:
        print(f"Error in download_media: {str(e)}")
    return None

def load_posts():
    """Load posts from JSON file."""
    if os.path.exists(POSTS_FILE):
        with open(POSTS_FILE, 'r') as f:
            data = json.load(f)
            posts = []
            for post_data in data:
                post = RedditPost(type('obj', (object,), post_data), from_json=True)
                posts.append(post)
            return posts
    return []

def save_posts(posts):
    """Save posts to JSON file."""
    with open(POSTS_FILE, 'w') as f:
        json.dump([post.__dict__ for post in posts], f)

def fetch_new_posts():
    """Fetch new posts from Reddit."""
    posts = []
    for subreddit_name in SUBREDDITS:
        try:
            subreddit = reddit.subreddit(subreddit_name)
            for post in subreddit.hot(limit=5):
                if not post.is_self and hasattr(post, 'url'):
                    print(f"\nProcessing post: {post.title[:50]}...")
                    print(f"URL: {post.url}")
                    
                    # For TikTokCringe, we specifically want video posts
                    if subreddit_name.lower() == 'tiktokcringe' and not (post.is_video or 'v.redd.it' in post.url):
                        print("Skipping non-video post in TikTokCringe")
                        continue
                    
                    reddit_post = RedditPost(post)
                    media_path = download_media(reddit_post.url, reddit_post.id)
                    
                    if media_path:
                        reddit_post.media_path = media_path
                        posts.append(reddit_post)
                        print(f"Successfully added {'video' if media_path.endswith('.mp4') else 'image'} post from r/{subreddit_name}")
                    else:
                        print("Failed to download media, skipping post")
                        
        except Exception as e:
            print(f"Error fetching posts from {subreddit_name}: {str(e)}")
    
    save_posts(posts)
    print(f"\nFetched {len(posts)} new posts")

def process_video_for_twitter(input_path):
    """Process video to meet Twitter's requirements."""
    try:
        print("Processing video for Twitter compatibility...")
        # Create a temporary file path
        temp_path = str(MEDIA_DIR / f"temp_{os.path.basename(input_path)}")
        output_path = str(MEDIA_DIR / f"processed_{os.path.basename(input_path)}")

        # Load video and get info
        video = VideoFileClip(input_path)
        duration = video.duration
        
        # Twitter video requirements
        MAX_DURATION = 140  # seconds
        MAX_SIZE_MB = 512
        TARGET_BITRATE = "2M"  # 2 Mbps is a good balance
        
        if duration > MAX_DURATION:
            print(f"Video too long ({duration}s), trimming to {MAX_DURATION}s")
            video = video.subclip(0, MAX_DURATION)
        
        # Close the video to free up resources
        video.close()
        
        # Use ffmpeg to process video with Twitter-compatible settings
        command = [
            'ffmpeg', '-y',  # Overwrite output files
            '-i', input_path,
            '-c:v', 'libx264',  # Video codec
            '-c:a', 'aac',      # Audio codec
            '-b:v', TARGET_BITRATE,  # Video bitrate
            '-pix_fmt', 'yuv420p',  # Pixel format
            '-movflags', '+faststart',  # Enable fast start
            '-strict', 'experimental',
            output_path
        ]
        
        print("Running ffmpeg command...")
        result = subprocess.run(command, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"FFmpeg error: {result.stderr}")
            return None
            
        # Check final file size
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        if size_mb > MAX_SIZE_MB:
            print(f"Processed video too large ({size_mb}MB), trying with lower bitrate...")
            # Try again with lower bitrate
            command[8] = "1M"  # Lower bitrate
            subprocess.run(command, capture_output=True, text=True)
            
        if os.path.exists(output_path):
            print(f"Video processed successfully: {output_path}")
            return output_path
            
    except Exception as e:
        print(f"Error processing video: {str(e)}")
    return None

def post_to_twitter():
    """Post an unused post to Twitter."""
    posts = load_posts()
    unused_posts = [post for post in posts if not post.used]
    
    if not unused_posts:
        print("No unused posts available")
        return
    
    post = random.choice(unused_posts)
    try:
        # Optimize the title
        optimized_title = optimize_title(post.title)
        
        # Check if media file still exists
        if not os.path.exists(post.media_path):
            print(f"Media file not found: {post.media_path}")
            post.used = True
            save_posts(posts)
            return
        
        print(f"Posting to Twitter: {optimized_title}")
        
        try:
            upload_path = post.media_path
            is_video = post.media_path.endswith('.mp4')
            
            # Process video if necessary
            if is_video:
                print("Processing video before upload...")
                processed_path = process_video_for_twitter(post.media_path)
                if processed_path:
                    upload_path = processed_path
                else:
                    print("Video processing failed")
                    post.used = True
                    save_posts(posts)
                    return
            
            # Upload media using v1.1 API
            print(f"Uploading media file: {upload_path}")
            media_category = 'tweet_video' if is_video else 'tweet_image'
            
            media = twitter_api.media_upload(
                filename=upload_path,
                media_category=media_category
            )
            print(f"Media uploaded with ID: {media.media_id_string}")
            
            # Wait for video processing if it's a video
            if is_video:
                print("Waiting for video processing...")
                media_status = twitter_api.get_media_upload_status(media.media_id)
                while media_status.processing_info and media_status.processing_info['state'] == 'pending':
                    wait_time = media_status.processing_info.get('check_after_secs', 5)
                    print(f"Video still processing, waiting {wait_time} seconds...")
                    time.sleep(wait_time)
                    media_status = twitter_api.get_media_upload_status(media.media_id)
                
                if media_status.processing_info and media_status.processing_info['state'] == 'failed':
                    raise Exception("Video processing failed")
                print("Video processing completed successfully")
            
            # Post tweet with media using v2 API
            print("Creating tweet with media...")
            tweet = twitter_client.create_tweet(
                text=optimized_title,
                media_ids=[str(media.media_id)]
            )
            
            print(f"Tweet posted successfully with ID: {tweet.data['id']}")
            
            # Mark post as used and save
            post.used = True
            save_posts(posts)
            
            # Clean up media files
            try:
                # Clean up original file
                os.remove(post.media_path)
                print(f"Cleaned up original media file: {post.media_path}")
                
                # Clean up processed file if it exists
                if is_video and upload_path != post.media_path:
                    os.remove(upload_path)
                    print(f"Cleaned up processed media file: {upload_path}")
                    
            except Exception as e:
                print(f"Error cleaning up media files: {e}")
                
        except Exception as e:
            print(f"Error posting to Twitter: {str(e)}")
            if "media" in str(e).lower():
                print("Media upload failed, marking post as used to skip")
                post.used = True
                save_posts(posts)
                
    except Exception as e:
        print(f"Error in post_to_twitter: {str(e)}")

def clean_media_directory():
    """Delete all files in the media directory."""
    for media_file in MEDIA_DIR.glob('*'):
        try:
            media_file.unlink()
            print(f"Deleted media file: {media_file}")
        except Exception as e:
            print(f"Error deleting media file {media_file}: {e}")

def main():

    clean_media_directory()

    # Fetch new posts at the start of each day
    schedule.every().day.at("00:00").do(fetch_new_posts)
    
    # Post to Twitter every 60 minutes
    # note will make a good tweet schedule whenever analytics are available
    schedule.every(144).minutes.do(post_to_twitter)
    
    # Initial fetch
    fetch_new_posts()
    
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    main()