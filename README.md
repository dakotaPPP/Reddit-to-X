# Reddit to Twitter Bot

This bot automatically pulls top posts from selected subreddits and reposts them to Twitter with AI-optimized titles.

## Features

- Pulls top 5 posts from curated subreddits
- Daily refresh of content pool
- Posts to Twitter every 30 minutes
- AI-powered title optimization using ChatGPT
- Prevents duplicate posts
- Supports images and GIFs

## Setup

1. Clone this repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and fill in your API credentials:
   - Reddit API credentials (get from https://www.reddit.com/prefs/apps)
   - Twitter API credentials (get from https://developer.twitter.com)
   - OpenAI API key (get from https://platform.openai.com)

4. Customize the subreddit list in `reddit_twitter_bot.py`

## Usage

Run the bot:
```bash
python reddit_twitter_bot.py
```

The bot will:
- Initially fetch posts from the configured subreddits
- Post to Twitter every 30 minutes
- Refresh the post pool daily at midnight
- Store downloaded media in the `media` directory
- Track used posts in `posts_data.json`

## Configuration

Edit the `SUBREDDITS` list in `reddit_twitter_bot.py` to customize which subreddits to pull from.

## Requirements

- Python 3.7+
- PRAW (Reddit API)
- Tweepy (Twitter API)
- OpenAI API
- Other dependencies listed in requirements.txt
