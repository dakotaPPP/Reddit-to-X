import os
import json
import time
import schedule
import praw
import tweepy
import requests
import openai
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import random

# Load environment variables
load_dotenv()

# Initialize Reddit API
reddit = praw.Reddit(
    client_id=os.getenv('REDDIT_CLIENT_ID'),
    client_secret=os.getenv('REDDIT_CLIENT_SECRET'),
    user_agent="RedditTwitterBot/1.0"
)

# Initialize Twitter API v2 Client for general operations
twitter_client_v2 = tweepy.Client(
    consumer_key=os.getenv('TWITTER_API_KEY'),
    consumer_secret=os.getenv('TWITTER_API_SECRET'),
    access_token=os.getenv('TWITTER_ACCESS_TOKEN'),
    access_token_secret=os.getenv('TWITTER_ACCESS_TOKEN_SECRET')
)

# Initialize Twitter API v1.1 API for media uploads
auth = tweepy.OAuth1UserHandler(
    consumer_key=os.getenv('TWITTER_API_KEY'),
    consumer_secret=os.getenv('TWITTER_API_SECRET'),
    access_token=os.getenv('TWITTER_ACCESS_TOKEN'),
    access_token_secret=os.getenv('TWITTER_ACCESS_TOKEN_SECRET')
)
twitter_client_v1 = tweepy.API(auth)

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
                    4. Is under 200 characters
                    5. Maintains the original meaning but makes it more compelling
                    6. Avoids clickbait or sensationalism
                    7. Is written in a natural, conversational tone
                    8. Please don't use punctuation
                    9. type in all lower case
                    10. Prented you are a gen z, zoomer on the internet
                    11. Don't use emojis or hashtags
                    
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
        response = requests.get(url)
        if response.status_code == 200:
            extension = url.split('.')[-1].lower()
            if extension not in ['jpg', 'jpeg', 'png', 'mp4', 'gif']:
                extension = 'jpg'
            
            file_path = MEDIA_DIR / f"{post_id}.{extension}"
            with open(file_path, 'wb') as f:
                f.write(response.content)
            return str(file_path)
    except Exception as e:
        print(f"Error downloading media: {e}")
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
            for post in subreddit.hot(limit=10):  # Increased limit since we'll skip some posts
                # Skip posts that are text-only, videos, or don't have a valid media URL
                if (not post.is_self and  # Skip text posts
                    not post.is_video and  # Skip videos
                    hasattr(post, 'url') and  # Has URL
                    post.url.lower().endswith(('.jpg', '.jpeg', '.png', '.gif'))):  # Valid image extension
                    
                    reddit_post = RedditPost(post)
                    media_path = download_media(reddit_post.url, reddit_post.id)
                    if media_path:
                        reddit_post.media_path = media_path
                        posts.append(reddit_post)
                        print(f"Added post from r/{subreddit_name}: {post.title[:50]}...")
        except Exception as e:
            print(f"Error fetching posts from {subreddit_name}: {e}")
    
    save_posts(posts)
    print(f"Fetched {len(posts)} new posts")

def post_to_twitter():
    """Post an unused post to Twitter."""
    posts = load_posts()
    unused_posts = [post for post in posts if not post.used]
    
    if not unused_posts:
        print("No unused posts available")
        return
    
    post = unused_posts[0]
    post = random.choice(unused_posts)
    try:
        # Optimize the title
        optimized_title = optimize_title(post.title)
        # Check if media file still exists
        if not os.path.exists(post.media_path):
            print(f"Media file not found: {post.media_path}")
            post.used = True  # Mark as used to skip it
            save_posts(posts)
            return
            
        # Upload media and post to Twitter
        try:
            print(f"Posting to Twitter: {optimized_title}")
            media = twitter_client_v1.media_upload(post.media_path)
            print(f"Media uploaded: {media.media_id_string}")
            tweet = twitter_client_v2.create_tweet(
                text=optimized_title,
                media_ids=[media.media_id_string]
            )
            # Mark post as used and save
            post.used = True
            save_posts(posts)
            
            # Clean up media file after successful post
            try:
                os.remove(post.media_path)
                print(f"Cleaned up media file: {post.media_path}")
            except Exception as e:
                print(f"Error cleaning up media file: {e}")
                
        except Exception as e:
            print(f"Error posting to Twitter: {e}")
    except Exception as e:
        print(f"Error in post_to_twitter: {e}")

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
    schedule.every(60).minutes.do(post_to_twitter)
    
    # Initial fetch
    fetch_new_posts()
    
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    main()
