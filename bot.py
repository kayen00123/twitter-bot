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
# Twitter credentials
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.getenv("ACCESS_TOKEN_SECRET")

# Gemini for text generation
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

# Posting cadence and behavior
POST_EVERY_HOURS = int(os.getenv("POST_EVERY_HOURS", 3))  # tweet every 3 hours
LAUNCHPAD_NAME = os.getenv("LAUNCHPAD_NAME", "wenlambo")
LAUNCHPAD_WEBSITE = os.getenv("LAUNCHPAD_WEBSITE", "wenlambo.lol")

# Persistence for deduplication and website usage
DATA_DIR = os.getenv("DATA_DIR", "data")
HISTORY_PATH = os.getenv("HISTORY_PATH", os.path.join(DATA_DIR, "posted_history.jsonl"))
WEBSITE_USAGE_PATH = os.getenv("WEBSITE_USAGE_PATH", os.path.join(DATA_DIR, "website_usage.json"))

# Twitter endpoints
TWEET_URL = "https://api.twitter.com/2/tweets"

# ==========================================================

# Viral prompt seeds: mix of launchpad hype + memes + questions
PROMPTS = [
    "short tweet that highlights what wenlambo launchpad offers, like free token creation and registration of tokens created outside the platform, 0.1% fees for creators, weekly airdrops, staking, and many more. Make it very convincing, fun, and full of energy with natural emojis.",
    "craft a viral tweet hyping how wenlambo is the launchpad for degens tired of high fees and complex tools. compare it with typical crypto pain points and show how easy it is to mint, trade, and stake instantly. keep it fun and punchy.",
    "make a meme-style crypto tweet comparing the chaos of rugpulls and gas wars to how simple it feels trading on a good launchpad. add crypto slang, humor, and energy. short, fun, natural.",
    "write a degen humor tweet about how everyone in crypto is waiting for the next moonshot, but only smart traders find the early gems. keep it fun, sarcastic, and engaging.",
    "ask the crypto community: which memecoin is the best right now? which one will actually moon next? make it hype and engaging, encouraging replies. fun degen-style with emojis.",
    "create a crypto culture tweet referencing trends like memecoins, staking, and airdrops. make it feel like a community vibe, fun and fast-paced."
]

# Default crypto hashtags pool
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
    """Fix extra spaces around punctuation and emojis to make it look natural."""
    text = re.sub(r"\s+([?.!,])", r"\1", text)   # remove space before punctuation
    text = re.sub(r"([?.!,])([^\s])", r"\1 \2", text)  # ensure space after punctuation
    text = re.sub(r"\s+", " ", text).strip()     # collapse multiple spaces
    return text

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

def recent_word_usage(history_file: str, limit: int = 10) -> set:
    """Return a set of words used in the last N tweets."""
    words = set()
    try:
        with open(history_file, "r", encoding="utf-8") as f:
            lines = f.readlines()[-limit:]
        for line in lines:
            try:
                obj = json.loads(line)
                preview = obj.get("preview", "")
                words.update(normalize_text(preview).split())
            except Exception:
                continue
    except FileNotFoundError:
        pass
    return words

def is_too_similar(text: str, recent_words: set, overlap_limit: int = 6) -> bool:
    """Check if too many words are reused from recent tweets."""
    words = set(normalize_text(text).split())
    overlap = words & recent_words
    return len(overlap) >= overlap_limit

def append_history_record(text: str, tweet_ids: list):
    ensure_dir_for_file(HISTORY_PATH)
    has_website = LAUNCHPAD_WEBSITE.lower() in normalize_text(text)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hash": text_hash(text),
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
    usage = {"date": _today_str(), "used": True}
    with open(WEBSITE_USAGE_PATH, "w", encoding="utf-8") as f:
        json.dump(usage, f)

# ===================== Text Generation =====================

def build_viral_prompt(launchpad_name: str, website: str, seed: str, include_site: bool) -> str:
    rules = [
        "You are crafting a SINGLE viral-style crypto tweet. It must be punchy, humorous or mildly controversial, and persuasive.",
        f"Brand: {launchpad_name} | Site: {website}.",
        "Hard rules:",
        "- Output ONE tweet only, no preambles or explanations.",
        "- Max 260 characters (leave room for final brand/site append).",
        "- Strong hook at the start, compelling CTA or engagement.",
        "- 0-3 hashtags max. 0-2 emojis max. No lists, no numbering, no quotes around the tweet.",
    ]
    if include_site:
        rules.append(f"- Include '{website}' exactly once.")
    else:
        rules.append(f"- Do NOT include any URLs or the domain '{website}'.")
    rules.append("")
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

    if include_site:
        if website.lower() not in t.lower():
            candidate = t + f" — {website}"
            t = _trim_to_tweet(candidate, 280)
    else:
        pattern = re.compile(re.escape(website), flags=re.IGNORECASE)
        t = pattern.sub("", t)
        t = re.sub(r"\s{2,}", " ", t).strip()

    return t

def add_crypto_hashtags(text: str, min_tags: int = 3) -> str:
    hashtags_in_text = [tag for tag in CRYPTO_HASHTAGS if tag.lower() in text.lower()]
    needed = max(0, min_tags - len(hashtags_in_text))
    if needed > 0:
        extra = random.sample(CRYPTO_HASHTAGS, needed)
        candidate = text + " " + " ".join(extra)
        text = _trim_to_tweet(candidate, 280)
    return text

def finalize_tweet(text: str, launchpad_name: str, website: str, include_site: bool) -> str:
    if (text.startswith("\"") and text.endswith("\"")) or (text.startswith("'") and text.endswith("'")):
        text = text[1:-1]

    text = ensure_brand_and_site(text, launchpad_name, website, include_site)
    text = clean_spacing(text)
    text = add_crypto_hashtags(text, min_tags=3)
    return _trim_to_tweet(text, 280)

def generate_viral_tweet(
    launchpad_name: str,
    website: str,
    history_hashes: set,
    include_site: bool,
    max_attempts: int = 10
) -> Optional[str]:
    recent_words = recent_word_usage(HISTORY_PATH, limit=10)

    for attempt in range(1, max_attempts + 1):
        seed = random.choice(PROMPTS)
        prompt = build_viral_prompt(launchpad_name, website, seed, include_site)
        try:
            text = gemini_generate_text(prompt)
        except Exception as e:
            print("Gemini text generation failed", e)
            continue

        if not text:
            continue

        text = finalize_tweet(text, launchpad_name, website, include_site)
        if not text:
            continue

        h = text_hash(text)
        if h in history_hashes:
            print(f"Attempt {attempt}: duplicate tweet detected, regenerating.")
            continue

        if is_too_similar(text, recent_words, overlap_limit=6):
            print(f"Attempt {attempt}: tweet too similar in wording, regenerating.")
            continue

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
            include_site = should_include_site_today()
            text = generate_viral_tweet(LAUNCHPAD_NAME, LAUNCHPAD_WEBSITE, history_hashes, include_site=include_site)
            if not text:
                print("Skipping this cycle due to generation constraints.")
                print(f"Sleeping for {interval_seconds} seconds...")
                time.sleep(interval_seconds)
                continue

            print(f"Posting viral tweet (len={len(text)}, include_site={include_site}):", text)
            try:
                resp = post_tweet(text)
                tweet_id = resp.get("data", {}).get("id")
                if not tweet_id:
                    raise RuntimeError(f"No tweet id in response: {resp}")
                append_history_record(text, [tweet_id])
                history_hashes.add(text_hash(text))
                if include_site and LAUNCHPAD_WEBSITE.lower() in normalize_text(text):
                    mark_site_used_today()
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





