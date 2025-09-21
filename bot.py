import os
import time
import random
import base64
import requests
from requests_oauthlib import OAuth1

# --- Environment variables (set these in Railway) ---
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.getenv("ACCESS_TOKEN_SECRET")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_TEXT_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-1.5-flash")
GEMINI_IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image-preview")
POST_EVERY_HOURS = int(os.getenv("POST_EVERY_HOURS", 1))

# --- Endpoints ---
TWEET_URL = "https://api.twitter.com/2/tweets"
UPLOAD_URL = "https://upload.twitter.com/1.1/media/upload.json"
GENAI_BASE = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"

# --- Prompts ---
PROMPTS = [
    "Write a short tweet about the benefits of launching a token on our multi-chain launchpad.",
    "Create a fun tweet announcing that users can now trade instantly after creating tokens.",
    "Write a tweet highlighting that our launchpad supports BSC, Base, and Arbitrum.",
    "Write a hype tweet about how our launchpad gives projects instant liquidity and access to multiple chains.",
    "Create a tweet showing how easy it is to create and launch tokens for free on our platform.",
    "Write a tweet encouraging builders to launch on our platform for faster growth and wider exposure.",
    "Make a tweet that positions our launchpad as the future of token creation and trading.",
    "Craft a tweet comparing our instant tradability with traditional slow launch processes.",
    "Write a motivational tweet for crypto founders to choose our multi-chain launchpad for success.",
    "Write a persuasive tweet that makes builders feel they are missing out if they don’t launch on our multi-chain launchpad.",
    "Craft a powerful tweet that builds trust and shows our launchpad is the safest way to launch and trade tokens instantly.",
    "Write a motivational tweet that convinces founders their project will gain massive adoption by choosing our launchpad.",
]

# --- Helpers ---
def call_gemini_generate(model: str, contents):
    """
    Call the Generative Language API generateContent endpoint.
    `contents` should be a list of simple strings or objects.
    """
    url = GENAI_BASE.format(model) + f"?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    payload = {"contents": contents}
    r = requests.post(url, headers=headers, json=payload, timeout=60)
    r.raise_for_status()
    return r.json()


def generate_text(prompt: str) -> str:
    try:
        resp = call_gemini_generate(GEMINI_TEXT_MODEL, [prompt])
        # Attempt to read the usual text path:
        cand = resp.get("candidates", [])
        if cand:
            for part in cand[0].get("content", {}).get("parts", []):
                if part.get("text"):
                    return part["text"].strip()
        # fallback to casual
        return prompt
    except Exception as e:
        print("Gemini text generation failed:", e)
        return prompt


def _extract_image_bytes_from_part(part):
    """
    Attempt several possible fields that Gemini REST may return for inline image data.
    We handle a few possibilities observed in different clients/versions.
    Returns bytes or None.
    """
    # Many outputs put binary in part["inlineData"] or part["inline_data"]
    inline = part.get("inline_data") or part.get("inlineData") or {}
    # 1) inline_data.data may already be base64 string
    if isinstance(inline, dict):
        data = inline.get("data") or inline.get("b64_json") or inline.get("base64")
        if isinstance(data, str):
            try:
                return base64.b64decode(data)
            except Exception:
                pass
    # 2) some clients return b64_json at top-level part
    b64 = part.get("b64_json") or part.get("b64")
    if isinstance(b64, str):
        try:
            return base64.b64decode(b64)
        except Exception:
            pass
    # 3) some libs might return bytes-like directly (unlikely via JSON) - ignore
    return None


def generate_image(prompt: str) -> str | None:
    """
    Generate image via Gemini image-capable model and save to local file.
    Returns file path or None on failure.
    """
    try:
        resp = call_gemini_generate(GEMINI_IMAGE_MODEL, [prompt])
        cand = resp.get("candidates", [])
        if not cand:
            print("No candidates from Gemini image response:", resp)
            return None

        # Scan parts for inline image bytes
        parts = cand[0].get("content", {}).get("parts", [])
        for i, part in enumerate(parts):
            img_bytes = _extract_image_bytes_from_part(part)
            if img_bytes:
                out_path = f"generated_image_{int(time.time())}.png"
                with open(out_path, "wb") as f:
                    f.write(img_bytes)
                return out_path

        # If nothing found:
        print("No inline image data found in Gemini response:", resp)
        return None
    except Exception as e:
        print("Gemini image generation failed:", e)
        return None


def upload_media(img_path: str) -> str | None:
    try:
        auth = OAuth1(API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET)
        with open(img_path, "rb") as f:
            files = {"media": f}
            r = requests.post(UPLOAD_URL, auth=auth, files=files, timeout=60)
            r.raise_for_status()
            return r.json().get("media_id_string")
    except Exception as e:
        print("Upload to Twitter failed:", e)
        return None


def post_tweet(text: str, media_id: str | None = None):
    auth = OAuth1(API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET)
    payload = {"text": text}
    if media_id:
        payload["media"] = {"media_ids": [media_id]}
    r = requests.post(TWEET_URL, auth=auth, json=payload, timeout=30)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Failed to post tweet: {r.status_code} {r.text}")
    return r.json()


# --- Main loop ---
def main():
    interval_seconds = max(60, POST_EVERY_HOURS * 3600)

    # small randomized startup delay to avoid bursty posts on restarts
    startup_delay = random.randint(10, 90)
    print(f"Startup delay: {startup_delay}s")
    time.sleep(startup_delay)

    while True:
        try:
            prompt = random.choice(PROMPTS)
            print("Generating tweet text...")
            text = generate_text(prompt)

            # create an image prompt oriented to the text
            image_prompt = f"Create a high-quality promotional poster for a crypto launchpad: {text} " \
                           "Style: futuristic, clean, dark background with glowing blockchain icons, include short legible headline text."
            print("Generating image...")
            img_path = generate_image(image_prompt)

            media_id = None
            if img_path:
                print("Uploading image to Twitter:", img_path)
                media_id = upload_media(img_path)

            print("Posting tweet...")
            resp = post_tweet(text, media_id)
            print("Tweet posted:", resp)
        except Exception as e:
            print("Error during posting:", e)

        print(f"Sleeping for {interval_seconds} seconds...")
        time.sleep(interval_seconds)


if __name__ == "__main__":
    main()
