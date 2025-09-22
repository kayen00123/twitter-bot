import os
import time
import random
import requests
from requests_oauthlib import OAuth1

# Load config from environment variables
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.getenv("ACCESS_TOKEN_SECRET")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
POST_EVERY_HOURS = int(os.getenv("POST_EVERY_HOURS", 1))

TWEET_URL = "https://api.twitter.com/2/tweets"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

# Example prompts (always request 300+ words)
PROMPTS = [
    "Write a detailed tweet of at least 300 words about the benefits of launching a token on our multi-chain launchpad.",
    "Create a fun and engaging tweet of at least 300 words announcing that users can now trade instantly after creating tokens.",
    "Write a tweet of at least 300 words highlighting that our launchpad supports BSC, Base, and Arbitrum.",
    "Write a hype tweet of at least 300 words about how our launchpad gives projects instant liquidity and access to multiple chains.",
    "Create a persuasive tweet of at least 300 words showing how easy it is to create and launch tokens for free on our platform.",
    "Write a motivational tweet of at least 300 words encouraging builders to launch on our platform for faster growth and wider exposure.",
    "Make a tweet of at least 300 words that positions our launchpad as the future of token creation and trading.",
    "Craft a tweet of at least 300 words comparing our instant tradability with traditional slow launch processes.",
    "Write a motivational tweet of at least 300 words for crypto founders to choose our multi-chain launchpad for success.",
    "Write a persuasive tweet of at least 300 words that makes builders feel they are missing out if they don’t launch on our multi-chain launchpad.",
    "Craft a powerful tweet of at least 300 words that builds trust and shows our launchpad is the safest way to launch and trade tokens instantly.",
    "Write a motivational tweet of at least 300 words that convinces founders their project will gain massive adoption by choosing our launchpad.",
    "Write a funny crypto humor tweet of at least 300 words that uses jokes, memes, and witty takes on token launches, but still highlights our launchpad.",
    "Write a controversial but safe crypto tweet of at least 300 words that sparks debate about the future of multi-chain launchpads vs traditional platforms, while promoting our project.",
]


# Keep track of last few tweets to avoid duplicates
recent_tweets = set()
MAX_RECENT = 20  # remember last 20 tweets


def generate_tweet():
    """Generate tweet text from Gemini with duplicate protection."""
    for attempt in range(5):  # up to 5 retries
        prompt = random.choice(PROMPTS)
        headers = {"Content-Type": "application/json"}
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        try:
            r = requests.post(
                f"{GEMINI_URL}?key={GEMINI_API_KEY}",
                headers=headers,
                json=payload,
                timeout=60
            )
            r.raise_for_status()
            data = r.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"].strip()

            if text not in recent_tweets:
                # Track recent tweets
                recent_tweets.add(text)
                if len(recent_tweets) > MAX_RECENT:
                    recent_tweets.pop()
                return text
        except Exception as e:
            print("Gemini generation failed:", e)

    # Fallback: random prompt if all retries failed
    return random.choice(PROMPTS)


def post_tweet(text):
    """Post tweet using Twitter API v2."""
    auth = OAuth1(API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET)
    payload = {"text": text}
    r = requests.post(TWEET_URL, auth=auth, json=payload, timeout=30)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Failed to post tweet: {r.status_code} {r.text}")
    return r.json()


def main():
    interval_seconds = max(60, POST_EVERY_HOURS * 3600)
    while True:
        try:
            text = generate_tweet()
            print("Posting tweet:", text[:100], "...")
            resp = post_tweet(text)
            print("Tweet posted:", resp)
        except Exception as e:
            print("Error during posting:", e)
        print(f"Sleeping for {interval_seconds} seconds...")
        time.sleep(interval_seconds)


if __name__ == "__main__":
    main()

