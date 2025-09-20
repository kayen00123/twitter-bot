'use strict';

const fs = require('fs');
const path = require('path');
const http = require('http');
const crypto = require('crypto');
const { exec } = require('child_process');
const { URLSearchParams } = require('url');
const fetch = require('node-fetch');

const CONFIG_PATH = path.join(__dirname, 'config.json');
const TOKENS_PATH = path.join(__dirname, 'tokens.json');

const AUTH_URL = 'https://twitter.com/i/oauth2/authorize';
const TOKEN_URL = 'https://api.twitter.com/2/oauth2/token';

function loadConfig() {
  const raw = fs.readFileSync(CONFIG_PATH, 'utf8');
  return JSON.parse(raw);
}

function b64urlNoPad(buf) {
  return buf.toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

function genCodeVerifier() {
  // 43-128 chars; high-entropy, URL-safe
  return b64urlNoPad(crypto.randomBytes(64));
}

function genCodeChallenge(verifier) {
  const hash = crypto.createHash('sha256').update(verifier).digest();
  return b64urlNoPad(hash);
}

function openInBrowser(url) {
  const platform = process.platform;
  if (platform === 'win32') {
    exec(`start "" "${url}"`);
  } else if (platform === 'darwin') {
    exec(`open "${url}"`);
  } else {
    exec(`xdg-open "${url}"`);
  }
}

function startLocalServer() {
  let resolveFn;
  const promise = new Promise((resolve) => { resolveFn = resolve; });

  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://127.0.0.1:8080');
    if (url.pathname !== '/callback') {
      res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
      res.end('Not Found');
      return;
    }
    const code = url.searchParams.get('code');
    const state = url.searchParams.get('state');

    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end('<html><body><h2>Authorization received. You can close this tab.</h2></body></html>');

    resolveFn({ code, state, server });
  });

  server.listen(8080, '127.0.0.1');
  return promise;
}

async function exchangeCodeForToken(cfg, code, verifier) {
  const params = new URLSearchParams({
    grant_type: 'authorization_code',
    client_id: cfg.client_id,
    redirect_uri: cfg.redirect_uri,
    code_verifier: verifier,
    code,
  });

  const resp = await fetch(TOKEN_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: params.toString(),
  });

  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Token exchange failed: ${resp.status} ${text}`);
  }

  const token = await resp.json();
  const expiresIn = Number(token.expires_in || 0);
  token.expires_at = Math.floor(Date.now() / 1000) + expiresIn - 60; // refresh 1 min early
  return token;
}

function saveTokens(tokens) {
  fs.writeFileSync(TOKENS_PATH, JSON.stringify(tokens, null, 2), 'utf8');
  console.log(`Saved tokens to ${TOKENS_PATH}`);
}

async function main() {
  const cfg = loadConfig();
  const scopes = cfg.scopes || [ 'tweet.write', 'users.read', 'offline.access' ];

  const codeVerifier = genCodeVerifier();
  const codeChallenge = genCodeChallenge(codeVerifier);
  const state = b64urlNoPad(crypto.randomBytes(16));

  const q = new URLSearchParams({
    response_type: 'code',
    client_id: cfg.client_id,
    redirect_uri: cfg.redirect_uri,
    scope: scopes.join(' '),
    state,
    code_challenge: codeChallenge,
    code_challenge_method: 'S256',
  });

  const authUrl = `${AUTH_URL}?${q.toString()}`;

  console.log('Opening browser for authorization...');
  console.log(authUrl);

  const pending = startLocalServer();
  openInBrowser(authUrl);

  const { code, state: recvState, server } = await pending;
  server.close();

  if (!code) throw new Error('Authorization code not found in callback.');
  if (recvState !== state) throw new Error('State mismatch; potential CSRF detected.');

  console.log('Exchanging authorization code for tokens...');
  const tokens = await exchangeCodeForToken(cfg, code, codeVerifier);
  saveTokens(tokens);
  console.log('Authorization complete.');
}

main().catch((err) => {
  console.error('Auth error:', err);
  process.exit(1);
});
