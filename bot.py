import json
import os
import random
import time
from typing import Dict, Any

import requests

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')
TOKENS_PATH = os.path.join(os.path.dirname(__file__), 'tokens.json')
TOKEN_URL = 'https://api.twitter.com/2/oauth2/token'
TWEET_URL = 'https://api.twitter.com/2/tweets'

TEST_SENTENCES = [
    "Testing automated post 1: Hello from my hourly bot!",
    "Testing automated post 2: This is a scheduled tweet.",
    "Testing automated post 3: Verifying OAuth refresh works.",
    "Testing automated post 4: Rotating through messages.",
    "Testing automated post 5: Everything looks good so far!",
]


def load_config() -> Dict[str, Any]:
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_tokens() -> Dict[str, Any]:
    with open(TOKENS_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_tokens(tokens: Dict[str, Any]):
    with open(TOKENS_PATH, 'w', encoding='utf-8') as f:
        json.dump(tokens, f, indent=2)


def ensure_token(cfg: Dict[str, Any], tokens: Dict[str, Any]) -> Dict[str, Any]:
    now = int(time.time())
    if tokens.get('access_token') and tokens.get('expires_at', 0) > now:
        return tokens
    # Need refresh
    print('Refreshing access token...')
    data = {
        'grant_type': 'refresh_token',
        'refresh_token': tokens.get('refresh_token'),
        'client_id': cfg['client_id'],
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    r = requests.post(TOKEN_URL, data=data, headers=headers, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f'Failed to refresh token: {r.status_code} {r.text}')
    new_tok = r.json()
    expires_in = new_tok.get('expires_in', 0)
    new_tok['expires_at'] = int(time.time()) + int(expires_in) - 60
    # Keep old refresh_token if new one not provided
    if 'refresh_token' not in new_tok and 'refresh_token' in tokens:
        new_tok['refresh_token'] = tokens['refresh_token']
    save_tokens(new_tok)
    print('Token refreshed.')
    return new_tok


def post_tweet(access_token: str, text: str):
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
    }
    payload = {"text": text}
    r = requests.post(TWEET_URL, headers=headers, json=payload, timeout=30)
    if r.status_code not in (200, 201):
        raise RuntimeError(f'Failed to post tweet: {r.status_code} {r.text}')
    return r.json()


def main():
    cfg = load_config()
    interval_hours = int(cfg.get('post_every_hours', 1))
    interval_seconds = max(60, interval_hours * 3600)

    if not os.path.exists(TOKENS_PATH):
        raise SystemExit('tokens.json not found. Run "python auth.py" first to authorize the app.')

    tokens = load_tokens()

    # Round-robin or random selection for testing; here we randomize
    idx = 0

    while True:
        try:
            tokens = ensure_token(cfg, tokens)
            # Choose text
            text = random.choice(TEST_SENTENCES)
            print(f'Posting tweet: {text}')
            resp = post_tweet(tokens['access_token'], text)
            print('Tweet posted:', resp)
        except Exception as e:
            print('Error during posting:', e)
        # Sleep interval
        print(f'Sleeping for {interval_seconds} seconds...')
        time.sleep(interval_seconds)


if __name__ == '__main__':
    main()
