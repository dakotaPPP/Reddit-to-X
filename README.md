# 🤖 Reddit to X Bot

This bot automatically pulls top posts from selected subreddits and reposts them to X with AI-optimized titles! ✨

## ✨ Features

- 📱 Pulls top 5 posts from curated subreddits
- 🔄 Daily refresh of content pool
- ⏰ Posts to X every 144 minutes
- 🧠 AI-powered title optimization using ChatGPT
- 🚫 Prevents duplicate posts
- 🖼️ Supports images and GIFs

## 🛠️ Setup

1. Clone this repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Install FFmpeg:
   - Windows: 
     - Download FFmpeg from https://ffmpeg.org/download.html
     - Add FFmpeg to your system PATH
     - Or use Chocolatey: `choco install ffmpeg`
   - Mac: `brew install ffmpeg`
   - Linux: `sudo apt-get install ffmpeg`

4. Copy `.env.example` to `.env` and fill in your API credentials:
   - 🔑 Reddit API credentials (get from https://www.reddit.com/prefs/apps)
   - 🐦 X API credentials (get from https://developer.x.com)
      - Go to your app's settings and ensure that the app's permissions include "Read and Write" or "Read, Write, and Direct Messages."
   - 🤖 OpenAI API key (get from https://platform.openai.com)

5. Customize the subreddit list in `main.py`

## 🚀 Usage

Run the bot:
```bash
python main.py
```

The bot will:
- 📥 Initially fetch posts from the configured subreddits
- 🐦 Post to X every 144 minutes
- 🔄 Refresh the post pool daily at midnight
- 💾 Store downloaded media in the `media` directory
- 📝 Track used posts in `posts_data.json`

## ⚙️ Configuration

Edit the `SUBREDDITS` list in `main.py` to customize which subreddits to pull from.

## 📋 Requirements

- 🐍 Python 3.7+
- 🔌 PRAW (Reddit API)
- 🐦 Tweepy (X API)
- 🤖 OpenAI API
- 🎥 FFmpeg (for video processing)
- 📦 Other dependencies listed in requirements.txt
