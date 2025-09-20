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
REPLY_ACCOUNTS = os.getenv("REPLY_ACCOUNTS", "BNBCHAIN,cz_binance,binance,CoinMarketCap").split(",")
MAX_REPLIES_PER_ACCOUNT = int(os.getenv("MAX_REPLIES_PER_ACCOUNT", 2))
MAX_TWEETS_TO_CHECK = int(os.getenv("MAX_TWEETS_TO_CHECK", 3))

TWEET_URL = "https://api.twitter.com/2/tweets"
USERS_LOOKUP_URL = "https://api.twitter.com/2/users/by/username/{}"
USER_TWEETS_URL = "https://api.twitter.com/2/users/{}/tweets"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

auth = OAuth1(API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET)

# Store last replied tweet per account
last_replied = {acct: [] for acct in REPLY_ACCOUNTS}


def gemini_generate(prompt: str) -> str:
    headers = {"Content-Type": "application/json"}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        r = requests.post(f"{GEMINI_URL}?key={GEMINI_API_KEY}", headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        data = r.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        print("Gemini generation failed:", e)
        return prompt  # fallback


def post_tweet(text: str) -> dict:
    payload = {"text": text}
    r = requests.post(TWEET_URL, auth=auth, json=payload, timeout=30)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Failed to post tweet: {r.status_code} {r.text}")
    return r.json()


def get_user_id(username: str) -> str:
    r = requests.get(USERS_LOOKUP_URL.format(username), auth=auth, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Failed to fetch user ID for {username}: {r.status_code} {r.text}")
    return r.json()["data"]["id"]


def get_recent_tweets(user_id: str, max_results: int = 3):
    r = requests.get(USER_TWEETS_URL.format(user_id), params={"max_results": max_results}, auth=auth, timeout=30)
    if r.status_code != 200:
        print(f"Failed to fetch tweets for user {user_id}: {r.status_code} {r.text}")
        return []
    return r.json().get("data", [])


def reply_to_account(username: str):
    user_id = get_user_id(username)
    tweets = get_recent_tweets(user_id, MAX_TWEETS_TO_CHECK)
    replies_done = 0

    for tweet in tweets:
        tweet_id = tweet["id"]
        if tweet_id in last_replied[username]:
            continue  # already replied
        prompt = f"Read the following tweet and generate a reply relating it to my multi-chain launchpad: {tweet['text']}"
        reply_text = gemini_generate(prompt)
        payload = {"text": reply_text, "reply": {"in_reply_to_tweet_id": tweet_id}}
        r = requests.post(TWEET_URL, auth=auth, json=payload, timeout=30)
        if r.status_code in (200, 201):
            print(f"Replied to {username}: {reply_text}")
            last_replied[username].append(tweet_id)
            replies_done += 1
        if replies_done >= MAX_REPLIES_PER_ACCOUNT:
            break


def main():
    interval_seconds = max(60, POST_EVERY_HOURS * 3600)
    while True:
        try:
            # Post general tweet
            prompt = "Write a tweet about the benefits of launching a token on our multi-chain launchpad."
            text = gemini_generate(prompt)
            print("Posting tweet:", text)
            resp = post_tweet(text)
            print("Tweet posted:", resp)

            # Comment on selected accounts
            for acct in REPLY_ACCOUNTS:
                reply_to_account(acct)
        except Exception as e:
            print("Error:", e)
        print(f"Sleeping for {interval_seconds} seconds...")
        time.sleep(interval_seconds)


if __name__ == "__main__":
    main()
