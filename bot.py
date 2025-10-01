import os
import time
import random
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Optional

import requests
from requests_oauthlib import OAuth1

# ========================= Config =========================
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.getenv("ACCESS_TOKEN_SECRET")

# Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

POST_EVERY_HOURS = int(os.getenv("POST_EVERY_HOURS", 3))  # tweet every 3 hours
LAUNCHPAD_NAME = os.getenv("LAUNCHPAD_NAME", "wenlambo")
LAUNCHPAD_WEBSITE = os.getenv("LAUNCHPAD_WEBSITE", "wenlambo.lol")

DATA_DIR = os.getenv("DATA_DIR", "data")
HISTORY_PATH = os.getenv("HISTORY_PATH", os.path.join(DATA_DIR, "posted_history.jsonl"))
WEBSITE_USAGE_PATH = os.getenv("WEBSITE_USAGE_PATH", os.path.join(DATA_DIR, "website_usage.json"))
PROMPT_INDEX_PATH = os.getenv("PROMPT_INDEX_PATH", os.path.join(DATA_DIR, "prompt_index.json"))

TWEET_URL = "https://api.twitter.com/2/tweets"

# ==========================================================

PROMPTS = [
    "short tweet that highlights what wenlambo launchpad offers, like free token creation and registration of tokens created outside the platform, 0.1% fees for creators, weekly airdrops, staking, and many more. Make it very convincing, fun, and full of energy with natural emojis.",
    "craft a viral tweet hyping how wenlambo is the launchpad for degens tired of high fees and complex tools. compare it with typical crypto pain points and show how easy it is to mint, trade, and stake instantly. keep it fun and punchy.",
    "make a meme-style crypto tweet comparing the chaos of rugpulls and gas wars to how simple it feels trading on a good launchpad. add crypto slang, humor, and energy. short, fun, natural.",
    "write a degen humor tweet about how everyone in crypto is waiting for the next moonshot, but only smart traders find the early gems. keep it fun, sarcastic, and engaging.",
    "ask the crypto community: which memecoin is the best right now? which one will actually moon next? make it hype and engaging, encouraging replies. fun degen-style with emojis.",
    "create a crypto culture tweet referencing trends like memecoins, staking, and airdrops. make it feel like a community vibe, fun and fast-paced.",
    "write a hype crypto tweet about a launchpad that gives free token creation, 0.1% swap royalties for creators, weekly airdrops, 5% supply to users, staking rewards & whale protection. Make it fun, human, with emojis and spacing.",
    "make a meme-style tweet comparing other launchpads that charge fees vs ours that pays users and creators. Add emojis, spacing, and degen slang. It should sound like a human shill, not a robot.",
    "create a short viral tweet that highlights how our launchpad is fair, rewarding, and safe from whales. Use hype energy, emojis, and spacing to sound like a community-driven crypto post.",
    "write a playful crypto tweet that flexes how users on our launchpad get airdrops every week + 5% supply at launch. Make it funny, human-like, with emojis and casual tone."
]

CRYPTO_HASHTAGS = [
    "#crypto", "#bnb", "#ethereum", "#bitcoin", "#memecoin",
    "#blockchain", "#web3", "#trading", "#altcoins", "#defi"
]

# ========================= Helpers =========================

def ensure_dir_for_file(path: str):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).lower()

def clean_spacing(text: str) -> str:
    text = re.sub(r"\s+([?.!,])", r"\1", text)
    text = re.sub(r"([?.!,])([^\s])", r"\1 \2", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def _trim_to_tweet(text: str, limit: int = 280) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"

def append_history_record(text: str, tweet_ids: list):
    ensure_dir_for_file(HISTORY_PATH)
    has_website = LAUNCHPAD_WEBSITE.lower() in normalize_text(text)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "preview": normalize_text(text)[:200],
        "tweet_ids": tweet_ids,
        "has_website": has_website,
    }
    with open(HISTORY_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

def _today_str() -> str:
    return datetime.now(timezone.utc).date().isoformat()

def _load_site_usage() -> dict:
    try:
        with open(WEBSITE_USAGE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def should_include_site_today() -> bool:
    usage = _load_site_usage()
    return usage.get("date") != _today_str() or not usage.get("used", False)

def mark_site_used_today():
    ensure_dir_for_file(WEBSITE_USAGE_PATH)
    with open(WEBSITE_USAGE_PATH, "w", encoding="utf-8") as f:
        json.dump({"date": _today_str(), "used": True}, f)

# ================= Prompt Rotation =================

def load_prompt_index() -> int:
    try:
        with open(PROMPT_INDEX_PATH, "r", encoding="utf-8") as f:
            return int(json.load(f).get("index", 0))
    except Exception:
        return 0

def save_prompt_index(index: int):
    ensure_dir_for_file(PROMPT_INDEX_PATH)
    with open(PROMPT_INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump({"index": index}, f)

def next_prompt() -> str:
    idx = load_prompt_index()
    seed = PROMPTS[idx % len(PROMPTS)]
    save_prompt_index((idx + 1) % len(PROMPTS))
    return seed

# ===================== Text Generation =====================

def build_viral_prompt(launchpad_name: str, website: str, seed: str, include_site: bool) -> str:
    rules = [
        "You are crafting a SINGLE viral-style crypto tweet. It must be punchy, humorous or mildly controversial, and persuasive.",
        f"Site: {website}.",
        "- Output ONE tweet only.",
        "- Max 260 characters.",
    ]
    if include_site:
        rules.append(f"- Include '{website}' exactly once.")
    else:
        rules.append(f"- Do NOT include '{website}'.")
    return "\n".join(rules) + f"\nTheme seed: {seed}."

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

def ensure_brand_and_site(text: str, launchpad_name: str, website: str, include_site: bool) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    if include_site and website.lower() not in t.lower():
        t = _trim_to_tweet(t + f" — {website}", 280)
    return t

def add_crypto_hashtags(text: str, min_tags: int = 3) -> str:
    hashtags_in_text = [tag for tag in CRYPTO_HASHTAGS if tag.lower() in text.lower()]
    needed = max(0, min_tags - len(hashtags_in_text))
    if needed > 0:
        extra = random.sample(CRYPTO_HASHTAGS, needed)
        text = _trim_to_tweet(text + " " + " ".join(extra), 280)
    return text

def finalize_tweet(text: str, launchpad_name: str, website: str, include_site: bool) -> str:
    if (text.startswith("\"") and text.endswith("\"")) or (text.startswith("'") and text.endswith("'")):
        text = text[1:-1]
    text = ensure_brand_and_site(text, launchpad_name, website, include_site)
    text = clean_spacing(text)
    text = add_crypto_hashtags(text, min_tags=3)
    return _trim_to_tweet(text, 280)

def generate_viral_tweet(launchpad_name: str, website: str, include_site: bool) -> Optional[str]:
    seed = next_prompt()
    prompt = build_viral_prompt(launchpad_name, website, seed, include_site)
    try:
        text = gemini_generate_text(prompt)
    except Exception as e:
        print("Gemini text generation failed", e)
        return None
    if not text:
        return None
    return finalize_tweet(text, launchpad_name, website, include_site)

# ======================== Twitter API ========================

def post_tweet(text: str):
    auth = OAuth1(API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET)
    r = requests.post(TWEET_URL, auth=auth, json={"text": text}, timeout=60)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Failed to post tweet: {r.status_code} {r.text}")
    return r.json()

# =========================== Main ===========================

def main():
    if not all([API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET]):
        raise RuntimeError("Twitter API credentials not fully set.")
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY must be set.")

    interval_seconds = max(60, POST_EVERY_HOURS * 3600)

    while True:
        try:
            include_site = should_include_site_today()
            text = generate_viral_tweet(LAUNCHPAD_NAME, LAUNCHPAD_WEBSITE, include_site=include_site)
            if not text:
                print("⚠️ No tweet generated this cycle.")
                time.sleep(interval_seconds)
                continue
            print(f"🚀 Posting tweet (len={len(text)}, include_site={include_site}): {text}")
            try:
                resp = post_tweet(text)
                tweet_id = resp.get("data", {}).get("id")
                if include_site and LAUNCHPAD_WEBSITE.lower() in normalize_text(text):
                    mark_site_used_today()
                append_history_record(text, [tweet_id] if tweet_id else [])
                print("✅ Tweet posted. ID:", tweet_id)
            except Exception as e:
                print("❌ Failed to post:", e)
        except Exception as e:
            print("🔥 Error in loop:", e)
        print(f"😴 Sleeping for {interval_seconds} seconds...")
        time.sleep(interval_seconds)

if __name__ == "__main__":
    main()






