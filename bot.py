import os
import time
import random
import requests
from requests_oauthlib import OAuth1

# Twitter credentials from Railway variables
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.getenv("ACCESS_TOKEN_SECRET")

# Gemini AI
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

# Posting settings
POST_EVERY_HOURS = int(os.getenv("POST_EVERY_HOURS", 1))
MAX_TWEETS_TO_CHECK = int(os.getenv("MAX_TWEETS_TO_CHECK", 5))

# Twitter API endpoints
TWEET_URL = "https://api.twitter.com/2/tweets"
USER_LOOKUP_URL = "https://api.twitter.com/2/users/by/username/{}"
USER_TWEETS_URL = "https://api.twitter.com/2/users/{}/tweets"

# Only reply to Binance account
REPLY_ACCOUNTS = ["BNBCHAIN"]

# Example prompts for Gemini-generated tweets
PROMPTS = [
    "Write a short tweet about the benefits of launching a token on our multi-chain launchpad.",
    "Create a fun tweet announcing that users can now trade instantly after creating tokens.",
    "Write a tweet highlighting that our launchpad supports BSC, Base, and Arbitrum.",
]

# Cache numeric IDs to avoid repeated API calls
user_ids = {}

def get_user_id(username):
    if username in user_ids:
        return user_ids[username]
    auth = OAuth1(API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET)
    r = requests.get(USER_LOOKUP_URL.format(username), auth=auth, timeout=30)
    r.raise_for_status()
    uid = r.json()["data"]["id"]
    user_ids[username] = uid
    return uid

def get_recent_tweets(user_id, max_results=MAX_TWEETS_TO_CHECK):
    auth = OAuth1(API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET)
    max_results = max(5, min(max_results, 100))
    params = {"max_results": max_results, "exclude": "retweets,replies"}
    r = requests.get(USER_TWEETS_URL.format(user_id), auth=auth, params=params, timeout=30)
    r.raise_for_status()
    return r.json().get("data", [])

def generate_gemini_text(prompt):
    headers = {"Content-Type": "application/json"}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}",
            headers=headers,
            json=payload,
            timeout=30
        )
        r.raise_for_status()
        data = r.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        print("Gemini generation failed:", e)
        return prompt  # fallback

def post_tweet(text):
    auth = OAuth1(API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET)
    payload = {"text": text}
    r = requests.post(TWEET_URL, auth=auth, json=payload, timeout=30)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Failed to post tweet: {r.status_code} {r.text}")
    return r.json()

def reply_to_account(username):
    try:
        uid = get_user_id(username)
        tweets = get_recent_tweets(uid)
        # Limit to 2 replies per account
        for tweet in tweets[:2]:
            prompt = f"Write a reply to this tweet to relate it to our multi-chain launchpad:\n{tweet['text']}"
            reply_text = generate_gemini_text(prompt)
            payload = {"text": reply_text, "reply": {"in_reply_to_tweet_id": tweet["id"]}}
            auth = OAuth1(API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET)
            r = requests.post(TWEET_URL, auth=auth, json=payload, timeout=30)
            if r.status_code not in (200, 201):
                print(f"Failed to reply to {username}: {r.status_code} {r.text}")
            else:
                print(f"Replied to {username}: {reply_text}")
            time.sleep(5)  # small delay between replies
    except requests.exceptions.HTTPError as e:
        print(f"Failed to fetch tweets for user {username}: {e}")
    except Exception as e:
        print(f"Error replying to {username}: {e}")

def main():
    # Random startup delay to avoid spamming multiple replies at once
    startup_delay = random.randint(5, 60)
    print(f"Startup delay: {startup_delay} seconds")
    time.sleep(startup_delay)

    interval_seconds = max(60, POST_EVERY_HOURS * 3600)
    while True:
        # Post a standalone tweet
        try:
            text = generate_gemini_text(random.choice(PROMPTS))
            print("Posting tweet:", text)
            resp = post_tweet(text)
            print("Tweet posted:", resp)
        except Exception as e:
            print("Error posting main tweet:", e)

        # Reply only to Binance
        for acct in REPLY_ACCOUNTS:
            reply_to_account(acct)

        print(f"Sleeping for {interval_seconds} seconds...")
        time.sleep(interval_seconds)

if __name__ == "__main__":
    main()
