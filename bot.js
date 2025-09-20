'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { URL, URLSearchParams } = require('url');
const fetch = require('node-fetch');

const CONFIG_PATH = path.join(__dirname, 'config.json');
const TOKENS_PATH = path.join(__dirname, 'tokens.json');

const TOKEN_URL = 'https://api.twitter.com/2/oauth2/token';
const TWEET_URL = 'https://api.twitter.com/2/tweets';

// Gemini (Generative Language API)
function geminiGenerateUrl(model, apiKey) {
  return `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(model)}:generateContent?key=${apiKey}`;
}

const TEST_SENTENCES = [
  'Testing automated post 1: Hello from my hourly bot!',
  'Testing automated post 2: This is a scheduled tweet.',
  'Testing automated post 3: Verifying OAuth refresh works.',
  'Testing automated post 4: Rotating through messages.',
  'Testing automated post 5: Everything looks good so far!'
];

function loadConfig() {
  let fileCfg = {};
  try {
    if (fs.existsSync(CONFIG_PATH)) {
      fileCfg = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8'));
    }
  } catch (_) {
    fileCfg = {};
  }
  const merged = {
    ...fileCfg,
    // OAuth 1.0a credentials
    api_key: process.env.API_KEY || fileCfg.api_key,
    api_secret: process.env.API_SECRET || fileCfg.api_secret,
    access_token: process.env.ACCESS_TOKEN || fileCfg.access_token,
    access_token_secret: process.env.ACCESS_TOKEN_SECRET || fileCfg.access_token_secret,

    // Gemini
    gemini_api_key: process.env.GEMINI_API_KEY || fileCfg.gemini_api_key,
    gemini_model: process.env.GEMINI_MODEL || fileCfg.gemini_model || 'gemini-1.5-flash',

    // Interval
    post_every_hours: Number(process.env.POST_EVERY_HOURS || fileCfg.post_every_hours || 1),

    // OAuth2 (if used locally)
    client_id: process.env.CLIENT_ID || fileCfg.client_id,
  };
  return merged;
}

function loadTokens() {
  return JSON.parse(fs.readFileSync(TOKENS_PATH, 'utf8'));
}

function saveTokens(tokens) {
  fs.writeFileSync(TOKENS_PATH, JSON.stringify(tokens, null, 2), 'utf8');
}

// =========================
// Gemini text generation
// =========================
async function generateTweet(cfg) {
  if (!cfg.gemini_api_key) {
    // Not configured, fallback
    return TEST_SENTENCES[Math.floor(Math.random() * TEST_SENTENCES.length)];
  }

  const model = cfg.gemini_model || 'gemini-1.5-flash';
  const url = geminiGenerateUrl(model, cfg.gemini_api_key);

  // Rotating on-brand prompts for Wenlambo.lol
  const PROMPTS = [
    'Wenlambo.lol lets anyone launch a new token or register an existing one — free to create, just pay gas. Tokens trade instantly on our marketplace. Creators earn 5% at launch + 0.1% per swap auto-routed. Add 1-3 crypto emojis + 2-4 crypto hashtags.',
    'Launch or register your token on Wenlambo.lol in minutes. No platform fees (gas only), instant trading, and creator rewards: 5% of total supply at launch and 0.1% on every swap to the creator. Use 1-3 emojis and 2-4 crypto hashtags.',
    'Ship your token on Wenlambo.lol: free creation (gas only), instant marketplace trading, and built-in incentives — 5% supply at launch + 0.1% of all swaps to creators. Include 1-3 emojis and 2-4 crypto hashtags.',
    'Register an existing token or launch a new one on Wenlambo.lol. Creation/registration are free (gas only). Trade immediately. Creators get 5% at launch and 0.1% per swap automatically. Add 1-3 emojis + 2-4 crypto hashtags.'
  ];
  const prompt = PROMPTS[Math.floor(Math.random() * PROMPTS.length)] + ' Output a single tweet under 240 characters, include 2-4 relevant crypto hashtags and 1-3 emojis. No URLs. Output only the tweet text.';

  const body = {
    contents: [
      { parts: [{ text: prompt }] }
    ],
    generationConfig: {
      temperature: 0.9,
      maxOutputTokens: 120
    }
  };

  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });

  if (!resp.ok) {
    const t = await resp.text();
    throw new Error(`Gemini error: ${resp.status} ${t}`);
  }

  const data = await resp.json();
  let text = null;
  if (data && Array.isArray(data.candidates) && data.candidates[0] && data.candidates[0].content && Array.isArray(data.candidates[0].content.parts)) {
    // Concatenate all parts text if multiple
    text = data.candidates[0].content.parts.map(p => p.text || '').join(' ').trim();
  }
  if (!text) throw new Error('Gemini returned no content');

  // Sanitize to a single-line tweet and cap to 280 chars (Twitter limit)
  text = String(text).trim().replace(/\s+/g, ' ');
  text = text.replace(/^"|"$/g, '').replace(/^`+|`+$/g, '');
  if (text.length > 280) text = text.slice(0, 279);

  return text;
}

// =========================
// OAuth 1.0a (User context)
// =========================
function hasOAuth1(cfg) {
  return Boolean(cfg.api_key && cfg.api_secret && cfg.access_token && cfg.access_token_secret);
}

function rfc3986Encode(str) {
  return encodeURIComponent(str)
    .replace(/[!'()*]/g, c => '%' + c.charCodeAt(0).toString(16).toUpperCase());
}

function buildBaseString(method, baseURL, params) {
  // params: object of key->array(values) already normalized to arrays
  const pairs = [];
  const keys = Object.keys(params).sort();
  for (const k of keys) {
    const vs = Array.isArray(params[k]) ? params[k] : [params[k]];
    vs.sort();
    for (const v of vs) {
      pairs.push(`${rfc3986Encode(k)}=${rfc3986Encode(String(v))}`);
    }
  }
  const paramString = pairs.join('&');
  const base = [method.toUpperCase(), rfc3986Encode(baseURL), rfc3986Encode(paramString)].join('&');
  return base;
}

function oauth1HeaderForRequest({ method, url, cfg }) {
  const parsed = new URL(url);
  const baseURL = `${parsed.origin}${parsed.pathname}`;

  const oauthParams = {
    oauth_consumer_key: cfg.api_key,
    oauth_nonce: crypto.randomBytes(16).toString('hex'),
    oauth_signature_method: 'HMAC-SHA1',
    oauth_timestamp: Math.floor(Date.now() / 1000).toString(),
    oauth_token: cfg.access_token,
    oauth_version: '1.0',
  };

  // Collect all parameters (OAuth + query) for signature base string
  const sigParams = { ...oauthParams };
  for (const [k, v] of parsed.searchParams.entries()) {
    if (sigParams[k] === undefined) sigParams[k] = [];
    if (!Array.isArray(sigParams[k])) sigParams[k] = [sigParams[k]];
    sigParams[k].push(v);
  }

  const signingKey = `${rfc3986Encode(cfg.api_secret)}&${rfc3986Encode(cfg.access_token_secret)}`;
  const baseString = buildBaseString(method, baseURL, sigParams);
  const signature = crypto.createHmac('sha1', signingKey).update(baseString).digest('base64');

  const headerParams = { ...oauthParams, oauth_signature: signature };
  const auth = 'OAuth ' + Object.keys(headerParams)
    .sort()
    .map(k => `${rfc3986Encode(k)}="${rfc3986Encode(headerParams[k])}"`)
    .join(', ');
  return auth;
}

async function postTweetOAuth1(cfg, text) {
  const method = 'POST';
  const url = TWEET_URL; // no query params
  const headers = {
    'Authorization': oauth1HeaderForRequest({ method, url, cfg }),
    'Content-Type': 'application/json',
  };
  const resp = await fetch(url, {
    method,
    headers,
    body: JSON.stringify({ text })
  });
  if (!(resp.status === 200 || resp.status === 201)) {
    const textResp = await resp.text();
    throw new Error(`Failed to post tweet (OAuth1): ${resp.status} ${textResp}`);
  }
  return await resp.json();
}

// =========================
// OAuth 2.0 (PKCE user flow)
// =========================
async function ensureToken(cfg, tokens) {
  const now = Math.floor(Date.now() / 1000);
  if (tokens.access_token && Number(tokens.expires_at || 0) > now) {
    return tokens;
  }
  console.log('Refreshing access token...');
  const params = new URLSearchParams({
    grant_type: 'refresh_token',
    refresh_token: tokens.refresh_token,
    client_id: cfg.client_id,
  });
  const resp = await fetch(TOKEN_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: params.toString(),
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Failed to refresh token: ${resp.status} ${text}`);
  }
  const newTok = await resp.json();
  const expiresIn = Number(newTok.expires_in || 0);
  newTok.expires_at = Math.floor(Date.now() / 1000) + expiresIn - 60;
  if (!newTok.refresh_token && tokens.refresh_token) {
    newTok.refresh_token = tokens.refresh_token;
  }
  saveTokens(newTok);
  console.log('Token refreshed.');
  return newTok;
}

async function postTweetOAuth2(accessToken, text) {
  const resp = await fetch(TWEET_URL, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${accessToken}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ text })
  });
  if (!(resp.status === 200 || resp.status === 201)) {
    const textResp = await resp.text();
    throw new Error(`Failed to post tweet: ${resp.status} ${textResp}`);
  }
  return await resp.json();
}

async function main() {
  const cfg = loadConfig();
  const intervalHours = Number(cfg.post_every_hours || 1);
  const intervalMs = Math.max(60_000, intervalHours * 3600_000);

  const useOAuth1 = hasOAuth1(cfg);

  if (!useOAuth1) {
    // OAuth2 path requires tokens.json
    if (!fs.existsSync(TOKENS_PATH)) {
      console.error('No OAuth 1.0a credentials found in config and tokens.json not found.');
      console.error('Either:');
      console.error('  1) Provide api_key, api_secret, access_token, access_token_secret in config.json (OAuth 1.0a), or');
      console.error('  2) Run "npm run auth" to authorize with OAuth 2.0 (PKCE).');
      process.exit(1);
    }
  }

  let tokens = null;
  if (!useOAuth1) {
    tokens = loadTokens();
  }

  async function cycle() {
    try {
      // Generate tweet via Gemini (with safe fallback)
      let text;
      try {
        text = await generateTweet(cfg);
      } catch (genErr) {
        console.error('Gemini generation failed, using fallback:', genErr.message || genErr);
        text = TEST_SENTENCES[Math.floor(Math.random() * TEST_SENTENCES.length)];
      }

      let resp;
      console.log('Posting tweet:', text);
      if (useOAuth1) {
        resp = await postTweetOAuth1(cfg, text);
      } else {
        tokens = await ensureToken(cfg, tokens);
        resp = await postTweetOAuth2(tokens.access_token, text);
      }
      console.log('Tweet posted:', resp);
    } catch (err) {
      console.error('Error during posting:', err);
    }
  }

  // Run immediately then on interval
  await cycle();
  setInterval(cycle, intervalMs);
}

main().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
