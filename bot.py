import os
import random
import time
import requests

TOKEN_URL = 'https://api.twitter.com/2/oauth2/token'
TWEET_URL = 'https://api.twitter.com/2/tweets'

TEST_SENTENCES = [
    "🚀 WenLambo Launchpad is live! Build, launch & trade instantly.",
    "⚡ Multi-chain support (BSC, Base, Arbitrum) — your token, your rules.",
    "🔥 Create tokens for free, trade instantly on our launchpad.",
    "💎 Next-gen launchpad powered by speed and simplicity. WenLambo!",
    "📈 Build, launch, and moon — all in one place. #WenLambo"
]


def ensure_token(tokens: dict) -> dict:
    """Refresh access token if expired"""
    now = int(time.time())
    if tokens.get("access_token") and tokens.get("expires_at", 0) > now:
        return tokens

    print("Refreshing access token...")

    data = {
        "grant_type": "refresh_token",
        "refresh_token": os.getenv("TWITTER_REFRESH_TOKEN"),
        "client_id": os.getenv("TWITTER_CLIENT_ID"),
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    r = requests.post(TOKEN_URL, data=data, headers=headers, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Failed to refresh token: {r.status_code} {r.text}")

    new_tok = r.json()
    expires_in = new_tok.get("expires_in", 0)
    new_tok["expires_at"] = int(time.time()) + int(expires_in) - 60

    # Save refresh token back if API doesn’t return a new one
    if "refresh_token" not in new_tok:
        new_tok["refresh_token"] = os.getenv("TWITTER_REFRESH_TOKEN")

    print("Token refreshed.")
    return new_tok


def post_tweet(access_token: str, text: str):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    payload = {"text": text}

    r = requests.post(TWEET_URL, headers=headers, json=payload, timeout=30)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Failed to post tweet: {r.status_code} {r.text}")
    return r.json()


def main():
    interval_hours = int(os.getenv("POST_EVERY_HOURS", 1))
    interval_seconds = max(60, interval_hours * 3600)

    # Load tokens from ENV
    tokens = {
        "access_token": os.getenv("TWITTER_ACCESS_TOKEN"),
        "refresh_token": os.getenv("TWITTER_REFRESH_TOKEN"),
        "expires_at": 0,  # force refresh on start
    }

    while True:
        try:
            tokens = ensure_token(tokens)
            text = random.choice(TEST_SENTENCES)
            print(f"Posting tweet: {text}")
            resp = post_tweet(tokens["access_token"], text)
            print("Tweet posted:", resp)
        except Exception as e:
            print("Error during posting:", e)

        print(f"Sleeping for {interval_seconds} seconds...")
        time.sleep(interval_seconds)


if __name__ == "__main__":
    main()
