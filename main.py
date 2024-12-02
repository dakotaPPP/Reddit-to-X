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
from PIL import Image
import subprocess
from moviepy.editor import VideoFileClip
import re
from RedDownloader import RedDownloader

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
twitter_api = tweepy.API(twitter_auth, wait_on_rate_limit=True)

try:
    user = twitter_api.verify_credentials()
    if user:
        print(f"Authentication successful. Logged in as {user.screen_name}")
    else:
        print("Authentication failed.")
except Exception as e:
    print(f"Error during authentication: {e}")

# Initialize X.ai
openai.api_key = os.getenv("XAI_API_KEY")
openai.api_base = "https://api.x.ai/v1"
    
# Initialize OpenAI
# openai.api_key = os.getenv('OPENAI_API_KEY')

# Configuration
SUBREDDITS = [
    'tiktokcringe',
    # Add more subreddits here
]

MAX_VIDEO_COUNT = 1
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

    """Use xAu to optimize the title for Twitter."""
    try:
       response = openai.ChatCompletion.create(
            model=os.getenv("MODEL_NAME"),
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

    except Exception as e:
        print(f"Error optimizing title: {e}")
        return original_title

    return response['choices'][0]['message']['content']

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
            
        if re.search('/gallery/', url):
        # Transform the URL to the API endpoint
            permalink = url.replace("gallery", "comments")
            api_url = f"{permalink}.json"

            # Fetch the gallery metadata
            headers = {"User-Agent": "YourApp/0.1"}
            response = requests.get(api_url, headers=headers)

            # Check for a valid response

            if response.status_code == 200:
                try:
                    data = response.json()
                    gallery_data = data[0]["data"]["children"][0]["data"]

                    # Extract gallery metadata
                    media_metadata = gallery_data.get("media_metadata", {})
                    if not media_metadata:
                        print("No media metadata found in gallery.")
                        return None

                    file_paths = []
                    for key, media in media_metadata.items():
                        media_url = media["s"]["u"].replace("&amp;", "&")  # Replace HTML entities
                        extension = media_url.split('.')[-1].split('?')[0].lower()
                        file_path = MEDIA_DIR / f"{post_id}_{key}.{extension}"

                        # Download each image in the gallery
                        media_response = requests.get(media_url)
                        if media_response.status_code == 200:
                            with open(str(file_path), 'wb') as f:
                                f.write(media_response.content)
                            file_paths.append(str(file_path))
                        else:
                            print(f"Failed to download media: {media_url}")

                    return file_paths[0]
                except ValueError as e:
                    print(f"Error parsing JSON: {e}")
                    print("Response content:", response.text)  # Log the raw content for debugging
                    return None

            else:
                print(f"Failed to fetch gallery metadata. Status code: {response.status_code}")
                return None

        # For Reddit-hosted videos
        elif re.search('v.redd.it', url):

            # Extract the video ID from the URL
            file_path = MEDIA_DIR / f"{post_id}downloaded.mp4"

            # Download the video
            try:
                print("downloading media reddit video")
                RedDownloader.Download(url, destination = str(MEDIA_DIR / f"{post_id}"))

                return str(file_path)
                
            except Exception as e:
                print(f"Error downloading Reddit video: {str(e)}")
                # Clean up any temporary files
                if os.path.exists(file_path):
                    os.remove(file_path)
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
    video_count = 0
    posts = []
    for subreddit_name in SUBREDDITS:
        try:
            subreddit = reddit.subreddit(subreddit_name)
            # Get the top 5 posts for the week from the subreddit
            for index ,post in enumerate(subreddit.top(limit=20, time_filter = 'week')):



                if not post.is_self and hasattr(post, 'url'):
                    print(f"\nProcessing post: {post.title[:50]}...")
                    print(f"URL: {post.url}")


                    # If you want videos only uncomment the following
                    # if not (post.is_video or 'v.redd.it' in post.url):
                    #     continue

                    # video_count += 1
                    
                    reddit_post = RedditPost(post)
                    media_path = download_media(reddit_post.url, reddit_post.id)

                    time.sleep(2)
                    
                    if media_path:

                        print(media_path)
                        reddit_post.media_path = media_path
                        posts.append(reddit_post)
                        print(f"Successfully added {'video' if media_path.endswith('.mp4') else 'image'} post from r/{subreddit_name}")
                    else:
                        print("Failed to download media, skipping post")

                    if video_count > MAX_VIDEO_COUNT:
                        break
                        
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

            # Ensure that the app's permissions include "Read and Write" 
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
    
    
    # post twice a day
    schedule.every().day.at("09:00").do(post_to_twitter)  # First post at 9:00 AM
    schedule.every().day.at("17:00").do(post_to_twitter)  # Second post at 5:00 PM
    
    # Initial fetch
    fetch_new_posts()
    
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    main()