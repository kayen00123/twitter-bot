import os
import time
import random
import hashlib
import json
import re
from datetime import datetime

import requests
from requests_oauthlib import OAuth1

# ========================= Config =========================
# Twitter credentials
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.getenv("ACCESS_TOKEN_SECRET")

# Gemini for text generation
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

# Posting cadence and behavior
POST_EVERY_HOURS = int(os.getenv("POST_EVERY_HOURS", 1))
MIN_WORDS = int(os.getenv("MIN_WORDS", 500))
LAUNCHPAD_NAME = os.getenv("LAUNCHPAD_NAME", "Your Launchpad")

# Persistence for deduplication
HISTORY_PATH = os.getenv("HISTORY_PATH", os.path.join("data", "posted_history.jsonl"))

# Twitter endpoints
TWEET_URL = "https://api.twitter.com/2/tweets"

# ==========================================================

# Example topic prompts to vary themes
PROMPTS = [
    "benefits of launching a token on a multi-chain launchpad",
    "instant trading after token creation and why it matters",
    "support for BSC, Base, and Arbitrum and cross-chain reach",
    "how instant liquidity and multi-chain access accelerates growth",
    "how to create and launch tokens for free on the platform",
    "tips for builders to grow faster and reach wider audiences",
    "why this launchpad represents the future of token creation and trading",
    "comparison between instant tradability and traditional launch processes",
    "motivational message to crypto founders to choose a multi-chain launchpad",
    "FOMO angle showing what founders miss by ignoring a multi-chain launchpad",
    "safety, credibility and trust when launching and trading instantly",
    "how choosing the right launchpad drives adoption and community momentum",
]


# ========================= Helpers =========================

def ensure_dir_for_file(path: str):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


def text_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def word_count(text: str) -> int:
    return len(re.findall(r"[\w’']+", text))


def load_history_hashes() -> set:
    hashes = set()
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    if "hash" in obj:
                        hashes.add(obj["hash"])
                except Exception:
                    pass
    except FileNotFoundError:
        pass
    return hashes


def append_history_record(text: str, tweet_ids: list):
    ensure_dir_for_file(HISTORY_PATH)
    record = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "hash": text_hash(text),
        "first_chars": normalize_text(text)[:200],
        "word_count": word_count(text),
        "tweet_ids": tweet_ids,
    }
    with open(HISTORY_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ===================== Text Generation =====================

def build_long_tweet_prompt(launchpad_name: str, topic: str, min_words: int, variation_id: int) -> str:
    return (
        f"Write a SINGLE long tweet (not a thread). Minimum length: {min_words} words. "
        f"Focus topic: {topic}. The launchpad is called '{launchpad_name}'. Mention '{launchpad_name}' naturally and contextually throughout the content (not just once). "
        "Audience: crypto founders, builders, and communities. Tone: confident, helpful, trustworthy, and forward-looking. "
        "Avoid heavy emoji usage and avoid ALL-CAPS. Provide concrete benefits, examples, and practical guidance. "
        "Do not include numbering (no 1/, 2/) and do not say it will be split into a thread. "
        "Use short paragraphs separated by single newlines. If you include hashtags, include 1-3 max at the very end only. "
        f"Variation ID: {variation_id}."
    )


def gemini_generate_text(prompt: str) -> str:
    headers = {"Content-Type": "application/json"}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    r = requests.post(
        f"{GEMINI_URL}?key={GEMINI_API_KEY}",
        headers=headers,
        json=payload,
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()


def generate_long_tweet(min_words: int, launchpad_name: str, history_hashes: set, max_attempts: int = 5):
    for attempt in range(1, max_attempts + 1):
        topic = random.choice(PROMPTS)
        prompt = build_long_tweet_prompt(launchpad_name, topic, min_words, random.randint(100000, 999999))
        try:
            text = gemini_generate_text(prompt)
        except Exception as e:
            print("Gemini text generation failed:", e)
            text = None

        if not text:
            continue

        # Ensure launchpad name appears at least twice
        lc_name = launchpad_name.lower()
        if normalize_text(text).count(lc_name) < 2:
            text = f"{launchpad_name} empowers builders across chains. " + text + f"\n\nChoose {launchpad_name} for instant liquidity and reach."

        # Ensure minimum words
        if word_count(text) < min_words:
            try:
                expand_prompt = (
                    "Expand and enrich the following content with more examples, practical steps, and details. "
                    f"Ensure the total is at least {min_words} words and keep the same tone.\n\n" + text
                )
                extended = gemini_generate_text(expand_prompt)
                if word_count(extended) > word_count(text):
                    text = extended
            except Exception:
                pass

        if word_count(text) < min_words:
            print(f"Attempt {attempt}: not enough words (have {word_count(text)}, need {min_words}).")
            continue

        h = text_hash(text)
        if h in history_hashes:
            print(f"Attempt {attempt}: duplicate content detected, regenerating.")
            continue

        return text

    print("Failed to generate unique long-form tweet meeting requirements.")
    return None


# ======================== Twitter API ========================

def post_tweet(text: str):
    auth = OAuth1(API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET)
    payload = {"text": text}
    r = requests.post(TWEET_URL, auth=auth, json=payload, timeout=60)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Failed to post tweet: {r.status_code} {r.text}")
    return r.json()


# =========================== Main ===========================

def main():
    if not all([API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET]):
        raise RuntimeError("Twitter API credentials are not fully set in environment variables.")
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY must be set for text generation.")

    interval_seconds = max(60, POST_EVERY_HOURS * 3600)
    history_hashes = load_history_hashes()

    while True:
        try:
            text = generate_long_tweet(MIN_WORDS, LAUNCHPAD_NAME, history_hashes)
            if not text:
                print("Skipping this cycle due to generation constraints.")
                print(f"Sleeping for {interval_seconds} seconds...")
                time.sleep(interval_seconds)
                continue

            print(f"Attempting to post a single long tweet, words: {word_count(text)}")
            try:
                resp = post_tweet(text)
                tweet_id = resp.get("data", {}).get("id")
                if not tweet_id:
                    raise RuntimeError(f"No tweet id in response: {resp}")
                append_history_record(text, [tweet_id])
                history_hashes.add(text_hash(text))
                print("Posted single tweet. Tweet id:", tweet_id)
            except Exception as e:
                msg = str(e)
                if " 429 " in msg:
                    print("Rate limited (429). Your app/account hit posting limits. Retrying next cycle.")
                elif " 400 " in msg and "Too Long" in msg:
                    print("Tweet too long for this account. Long posts require X Premium/Paid plan on X API.")
                else:
                    print("Failed to post:", e)

        except Exception as e:
            print("Error during posting loop:", e)

        print(f"Sleeping for {interval_seconds} seconds...")
        time.sleep(interval_seconds)


if __name__ == "__main__":
    main()

