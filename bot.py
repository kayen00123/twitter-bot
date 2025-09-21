import os
import time
import random
import base64
import requests
from requests_oauthlib import OAuth1

# Load config from environment variables
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.getenv("ACCESS_TOKEN_SECRET")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Text model for tweet generation
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

# Image model for image generation
GEMINI_IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image-preview")
GEMINI_IMAGE_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_IMAGE_MODEL}:generateContent"

POST_EVERY_HOURS = int(os.getenv("POST_EVERY_HOURS", 1))
POST_WITH_IMAGES = os.getenv("POST_WITH_IMAGES", "1").lower() in ("1", "true", "yes", "y")

# Twitter endpoints
TWEET_URL = "https://api.twitter.com/2/tweets"
UPLOAD_URL = "https://upload.twitter.com/1.1/media/upload.json"

# Example prompts for Gemini
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


def _trim_to_tweet(text: str, limit: int = 280) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    # ensure we don't cut mid-word too harshly
    trimmed = text[: limit - 1].rstrip()
    return trimmed + "…"


def generate_tweet() -> str:
    """Generate tweet text using Gemini. Fallback to a random prompt if it fails."""
    prompt = random.choice(PROMPTS)
    headers = {"Content-Type": "application/json"}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        r = requests.post(
            f"{GEMINI_URL}?key={GEMINI_API_KEY}",
            headers=headers,
            json=payload,
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        return _trim_to_tweet(text)
    except Exception as e:
        print("Gemini text generation failed:", e)
        return _trim_to_tweet(prompt)  # fallback


def build_image_prompt(tweet_text: str) -> str:
    """Create a descriptive image prompt aligned with the tweet content."""
    base = (
        "Create a striking, on-brand social media image that visually represents the following tweet. "
        "Avoid heavy text; prioritize icons, abstract shapes, charts, coins, and launch/rocket motifs. "
        "Style: clean, modern, high-contrast, crypto/tech aesthetic, soft rim lighting, volumetric glow. "
        "Background: gradient or dark with subtle geometric patterns. Composition: square, centered focus.\n\n"
        f"Tweet: {tweet_text}"
    )
    return base


def generate_image(tweet_text: str):
    """Generate an image from Gemini and return (mime_type, image_bytes).

    Returns None on failure.
    """
    if not GEMINI_API_KEY:
        print("GEMINI_API_KEY not set; skipping image generation.")
        return None

    prompt = build_image_prompt(tweet_text)
    headers = {"Content-Type": "application/json"}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        r = requests.post(
            f"{GEMINI_IMAGE_URL}?key={GEMINI_API_KEY}",
            headers=headers,
            json=payload,
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()

        # Find the first inline_data part that looks like an image
        candidates = data.get("candidates", [])
        for cand in candidates:
            content = cand.get("content", {})
            parts = content.get("parts", [])
            for part in parts:
                inline = part.get("inline_data")
                if inline and isinstance(inline, dict):
                    mime_type = inline.get("mime_type", "image/png")
                    b64 = inline.get("data")
                    if b64:
                        try:
                            return mime_type, base64.b64decode(b64)
                        except Exception:
                            pass
        print("No inline_data image returned by Gemini.")
        return None
    except Exception as e:
        # Print response text for easier debugging if available
        try:
            print("Gemini image generation failed:", e, "\nResponse:", r.text)
        except Exception:
            print("Gemini image generation failed:", e)
        return None


def upload_media(image_bytes: bytes, media_type: str = "image/png") -> str:
    """Upload media to Twitter and return media_id_string."""
    auth = OAuth1(API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET)
    # Twitter v1.1 media upload accepts base64-encoded "media" field
    media_b64 = base64.b64encode(image_bytes).decode("ascii")
    data = {
        "media": media_b64,
        "media_category": "tweet_image",
    }
    r = requests.post(UPLOAD_URL, auth=auth, data=data, timeout=60)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Failed to upload media: {r.status_code} {r.text}")
    resp = r.json()
    return resp.get("media_id_string") or str(resp.get("media_id"))


def post_tweet(text: str):
    auth = OAuth1(API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET)
    payload = {"text": text}
    r = requests.post(TWEET_URL, auth=auth, json=payload, timeout=30)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Failed to post tweet: {r.status_code} {r.text}")
    return r.json()


def post_tweet_with_media(text: str, media_id: str):
    auth = OAuth1(API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET)
    payload = {
        "text": text,
        "media": {"media_ids": [media_id]},
    }
    r = requests.post(TWEET_URL, auth=auth, json=payload, timeout=30)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Failed to post tweet with media: {r.status_code} {r.text}")
    return r.json()


def main():
    interval_seconds = max(60, POST_EVERY_HOURS * 3600)
    while True:
        try:
            text = generate_tweet()
            print("Generated tweet:", text)

            if POST_WITH_IMAGES:
                img = generate_image(text)
            else:
                img = None

            if img:
                mime, img_bytes = img
                try:
                    media_id = upload_media(img_bytes, mime)
                    print("Media uploaded, media_id:", media_id)
                    resp = post_tweet_with_media(text, media_id)
                    print("Tweet with image posted:", resp)
                except Exception as e:
                    print("Image flow failed, falling back to text-only:", e)
                    resp = post_tweet(text)
                    print("Tweet posted:", resp)
            else:
                resp = post_tweet(text)
                print("Tweet posted:", resp)
        except Exception as e:
            print("Error during posting:", e)
        print(f"Sleeping for {interval_seconds} seconds...")
        time.sleep(interval_seconds)


if __name__ == "__main__":
    main()
