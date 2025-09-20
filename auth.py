import base64
import hashlib
import http.server
import json
import os
import secrets
import threading
import time
import urllib.parse
import webbrowser
from typing import Dict, Any

import requests

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')
TOKENS_PATH = os.path.join(os.path.dirname(__file__), 'tokens.json')

AUTH_URL = 'https://twitter.com/i/oauth2/authorize'
TOKEN_URL = 'https://api.twitter.com/2/oauth2/token'


def load_config() -> Dict[str, Any]:
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def b64url_nopad(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode('utf-8').rstrip('=')


def gen_code_verifier() -> str:
    # 43-128 chars allowed. Use high-entropy URL-safe string.
    verifier = secrets.token_urlsafe(64)
    # Ensure length within 43-128
    if len(verifier) < 43:
        verifier = (verifier + 'A' * 43)[:43]
    return verifier[:128]


def gen_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode('utf-8')).digest()
    return b64url_nopad(digest)


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    server_version = "TwitterAuthCallback/1.0"

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != '/callback':
            self.send_response(404)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(b'Not Found')
            return
        qs = urllib.parse.parse_qs(parsed.query)
        code = qs.get('code', [None])[0]
        state = qs.get('state', [None])[0]
        self.server.auth_code = code  # type: ignore[attr-defined]
        self.server.auth_state = state  # type: ignore[attr-defined]
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(b"<html><body><h2>Authorization received. You can close this tab.</h2></body></html>")
        # Signal main thread
        self.server.done_event.set()  # type: ignore[attr-defined]

    def log_message(self, format, *args):
        # Silence HTTP server logs
        return


def start_local_server() -> http.server.HTTPServer:
    server = http.server.HTTPServer(('127.0.0.1', 8080), CallbackHandler)
    server.done_event = threading.Event()  # type: ignore[attr-defined]
    server.auth_code = None  # type: ignore[attr-defined]
    server.auth_state = None  # type: ignore[attr-defined]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


def exchange_code_for_token(cfg: Dict[str, Any], code: str, verifier: str) -> Dict[str, Any]:
    data = {
        'grant_type': 'authorization_code',
        'client_id': cfg['client_id'],
        'redirect_uri': cfg['redirect_uri'],
        'code_verifier': verifier,
        'code': code,
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    r = requests.post(TOKEN_URL, data=data, headers=headers, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f'Token exchange failed: {r.status_code} {r.text}')
    token = r.json()
    # Compute expiry timestamp
    expires_in = token.get('expires_in', 0)
    token['expires_at'] = int(time.time()) + int(expires_in) - 60  # refresh 1 min early
    return token


def save_tokens(tokens: Dict[str, Any]):
    with open(TOKENS_PATH, 'w', encoding='utf-8') as f:
        json.dump(tokens, f, indent=2)
    print(f'Saved tokens to {TOKENS_PATH}')


def main():
    cfg = load_config()
    scopes = cfg.get('scopes', ["tweet.write", "users.read", "offline.access"]) 

    code_verifier = gen_code_verifier()
    code_challenge = gen_code_challenge(code_verifier)
    state = secrets.token_urlsafe(16)

    query = {
        'response_type': 'code',
        'client_id': cfg['client_id'],
        'redirect_uri': cfg['redirect_uri'],
        'scope': ' '.join(scopes),
        'state': state,
        'code_challenge': code_challenge,
        'code_challenge_method': 'S256',
    }

    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(query)}"

    server = start_local_server()
    print('Opening browser for authorization...')
    print(auth_url)
    webbrowser.open(auth_url)

    # Wait up to 5 minutes for callback
    if not server.done_event.wait(timeout=300):  # type: ignore[attr-defined]
        server.shutdown()
        raise TimeoutError('Did not receive authorization callback in time.')

    # Extract code and state
    code = server.auth_code  # type: ignore[attr-defined]
    recv_state = server.auth_state  # type: ignore[attr-defined]
    server.shutdown()

    if not code:
        raise RuntimeError('Authorization code not found in callback.')
    if recv_state != state:
        raise RuntimeError('State mismatch; potential CSRF detected.')

    print('Exchanging authorization code for tokens...')
    tokens = exchange_code_for_token(cfg, code, code_verifier)
    save_tokens(tokens)
    print('Authorization complete.')


if __name__ == '__main__':
    main()
