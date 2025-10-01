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

# DeepSeek AI for text generation
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-f04a791f36804900aaaabbcf6ef94cdc")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"

# Posting cadence and behavior
POST_EVERY_HOURS = int(os.getenv("POST_EVERY_HOURS", 3))  # tweet every 3 hours
LAUNCHPAD_NAME = os.getenv("LAUNCHPAD_NAME", "wenlambo")
LAUNCHPAD_WEBSITE = os.getenv("LAUNCHPAD_WEBSITE", "wenlambo.lol")

# Persistence for deduplication and website usage
DATA_DIR = os.getenv("DATA_DIR", "data")
HISTORY_PATH = os.getenv("HISTORY_PATH", os.path.join(DATA_DIR, "posted_history.jsonl"))
WEBSITE_USAGE_PATH = os.getenv("WEBSITE_USAGE_PATH", os.path.join(DATA_DIR, "website_usage.json"))
PROMPT_INDEX_PATH = os.getenv("PROMPT_INDEX_PATH", os.path.join(DATA_DIR, "prompt_index.json"))

# Twitter endpoints
TWEET_URL = "https://api.twitter.com/2/tweets"

# ==========================================================

# Viral prompt seeds
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
    text = re.sub(r"\s+([?.!,])", r"\1", text)
    text = re.sub(r"([?.!,])([^\s])", r"\1 \2", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def text_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()

def _trim_to_tweet(text: str, limit: int = 280) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"

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

def deepseek_generate_text(prompt: str) -> str:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
    }
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.9,
        "max_tokens": 200,
    }
    r = requests.post(DEEPSEEK_URL, headers=headers, json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"].strip()

def ensure_brand_and_site(text: str, launchpad_name: str, website: str, include_site: bool) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    if include_site:
        if website.lower() not in t.lower():
            t = _trim_to_tweet(t + f" — {website}", 280)
    else:
        t = re.sub(re.escape(website), "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s{2,}", " ", t).strip()
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

def generate_viral_tweet(launchpad_name: str, website: str, history_hashes: set, include_site: bool, max_attempts: int = 10) -> Optional[str]:
    for attempt in range(1, max_attempts + 1):
        seed = next_prompt()
        prompt = build_viral_prompt(launchpad_name, website, seed, include_site)
        try:
            text = deepseek_generate_text(prompt)
        except Exception as e:
            print("DeepSeek text generation failed", e)
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
        if len(text) < 40:
            print(f"Attempt {attempt}: too short after finalization, retrying.")
            continue
        return text
    print("Failed to generate unique viral tweet.")
    return None

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
        raise RuntimeError("Twitter API credentials are not fully set in environment variables.")
    if not DEEPSEEK_API_KEY:
        raise RuntimeError("DEEPSEEK_API_KEY must be set for text generation.")

    interval_seconds = max(60, POST_EVERY_HOURS * 3600)
    history_hashes = load_history_hashes()

    while True:
        try:
            include_site = should_include_site_today()
            text = generate_viral_tweet(LAUNCHPAD_NAME, LAUNCHPAD_WEBSITE, history_hashes, include_site=include_site)
            if not text:
                print("Skipping this cycle due to generation constraints.")
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
                if " 429 " in str(e):
                    print("Rate limited (429). Retrying next cycle.")
                else:
                    print("Failed to post:", e)
        except Exception as e:
            print("Error during posting loop:", e)
        print(f"Sleeping for {interval_seconds} seconds...")
        time.sleep(interval_seconds)

if __name__ == "__main__":
    main()






