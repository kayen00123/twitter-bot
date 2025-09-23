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
LAUNCHPAD_NAME = os.getenv("LAUNCHPAD_NAME", "wenlambo")
LAUNCHPAD_WEBSITE = os.getenv("LAUNCHPAD_WEBSITE", "wenlambo.lol")

# Persistence for deduplication
HISTORY_PATH = os.getenv("HISTORY_PATH", os.path.join("data", "posted_history.jsonl"))

# Twitter endpoints
TWEET_URL = "https://api.twitter.com/2/tweets"

# ==========================================================

# Viral prompt seeds: crypto humor + controversy + CTA
PROMPTS = [
    # Humor
    "light-hearted roast of 'wen lambo' culture, playful degen vibes, punchy hook, invite to actually build",
    "gas fees jokes and meme-NRG about launching tokens smarter, not harder",
    "the eternal cycle: buy top, sell bottom, then build smarter with a real launchpad",
    "gm/gm? markets down, memes up — turn cope into tokens with an easy launch",
    "everyone's 'early' after it's trending — be actually early by deploying now",
    # Controversy (spicy but not toxic)
    "memecoins vs 'serious' tokens: why speed + liquidity beats pure whitepapers",
    "KOL pumps and VC allocations are cool until you need liquidity and users",
    "centralized exchange listing dreams vs instant trading reality",
    "rug paranoia is valid — transparency + instant tradability wins trust",
    "are presales dead? launch first, build community from day one",
    # FOMO + CTA
    "ship today, iterate tomorrow: fast launch, instant trading, real momentum",
    "turn your idea into a token in minutes — then let the market speak",
    "builders who wait lose narrative — deploy now and write your own story",
    "alpha isn't a Discord role, it's shipping your token before the hype",
    "if your community asks 'wen', answer with a live chart not a roadmap",
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


def _trim_to_tweet(text: str, limit: int = 280) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    trimmed = text[: limit - 1].rstrip()
    return trimmed + "…"


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
        "preview": normalize_text(text)[:200],
        "tweet_ids": tweet_ids,
    }
    with open(HISTORY_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ===================== Text Generation =====================

def build_viral_prompt(launchpad_name: str, website: str, seed: str) -> str:
    return (
        "You are crafting a SINGLE viral-style crypto tweet. It must be punchy, humorous or mildly controversial, and persuasive.\n"
        f"Brand: {launchpad_name} | Site: {website}.\n"
        "Hard rules:\n"
        "- Output ONE tweet only, no preambles or explanations.\n"
        "- Max 260 characters (leave room for final brand/site append).\n"
        f"- Include '{launchpad_name}' or '{website}' naturally at least once.\n"
        "- Strong hook at the start, compelling CTA to follow or visit the site.\n"
        "- 0-3 hashtags max. 0-2 emojis max. No lists, no numbering, no quotes around the tweet.\n"
        "- No links except the site if used. No disclaimers.\n\n"
        f"Theme seed: {seed}."
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


def ensure_brand_presence(text: str, launchpad_name: str, website: str) -> str:
    lt = text.lower()
    has_brand = launchpad_name.lower() in lt
    has_site = website.lower() in lt
    appendix = None
    if not (has_brand or has_site):
        # Prefer appending website to drive traffic
        appendix = f" — {website}"
    if appendix:
        # Try to append; if it exceeds limit, trim first
        candidate = text + appendix
        return _trim_to_tweet(candidate, 280)
    return text


def finalize_tweet(text: str, launchpad_name: str, website: str) -> str:
    # Remove surrounding quotes if model added them
    if (text.startswith("\"") and text.endswith("\"")) or (text.startswith("'") and text.endswith("'")):
        text = text[1:-1]
    text = re.sub(r"\s+", " ", text).strip()
    text = ensure_brand_presence(text, launchpad_name, website)
    # Final trim to 280 chars
    return _trim_to_tweet(text, 280)


def generate_viral_tweet(launchpad_name: str, website: str, history_hashes: set, max_attempts: int = 8) -> str | None:
    for attempt in range(1, max_attempts + 1):
        seed = random.choice(PROMPTS)
        prompt = build_viral_prompt(launchpad_name, website, seed)
        try:
            text = gemini_generate_text(prompt)
        except Exception as e:
            print("Gemini text generation failed:", e)
            text = None

        if not text:
            continue

        text = finalize_tweet(text, launchpad_name, website)
        if not text:
            continue

        h = text_hash(text)
        if h in history_hashes:
            print(f"Attempt {attempt}: duplicate tweet detected, regenerating.")
            continue

        # Basic sanity: tweet length and minimal substance
        if len(text) < 40:
            print(f"Attempt {attempt}: too short after finalization, retrying.")
            continue

        return text

    print("Failed to generate unique viral tweet.")
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
            text = generate_viral_tweet(LAUNCHPAD_NAME, LAUNCHPAD_WEBSITE, history_hashes)
            if not text:
                print("Skipping this cycle due to generation constraints.")
                print(f"Sleeping for {interval_seconds} seconds...")
                time.sleep(interval_seconds)
                continue

            print(f"Posting viral tweet (len={len(text)}):", text)
            try:
                resp = post_tweet(text)
                tweet_id = resp.get("data", {}).get("id")
                if not tweet_id:
                    raise RuntimeError(f"No tweet id in response: {resp}")
                append_history_record(text, [tweet_id])
                history_hashes.add(text_hash(text))
                print("Tweet posted. Tweet id:", tweet_id)
            except Exception as e:
                msg = str(e)
                if " 429 " in msg:
                    print("Rate limited (429). Your app/account hit posting limits. Retrying next cycle.")
                else:
                    print("Failed to post:", e)

        except Exception as e:
            print("Error during posting loop:", e)

        print(f"Sleeping for {interval_seconds} seconds...")
        time.sleep(interval_seconds)


if __name__ == "__main__":
    main()


