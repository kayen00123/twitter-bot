Twitter Bot (OAuth 2.0 PKCE or OAuth 1.0a) - Node.js

Prerequisites
- Node.js 16+

Setup (Node.js)
1) Install dependencies
   - npm install

2) Configure credentials (choose ONE path)
   A) OAuth 1.0a (use your Access Token and Access Token Secret)
      - In config.json, fill these fields:
        {
          "api_key": "<Your API Key>",
          "api_secret": "<Your API Key Secret>",
          "access_token": "1950916076478275586-3a297Zz9nTFYPMxz1oFegdJoQdPnYh",
          "access_token_secret": "ThDSsoMEAUTpdCgpVJ3sAumDTLY9HHyiSFS2FoQOQk5RM"
        }
      - The bot will use OAuth 1.0a and post immediately without running auth.

   B) OAuth 2.0 (PKCE user flow)
      - Ensure client_id, redirect_uri, and scopes are set in config.json.
      - Run: npm run auth
      - Approve the requested permissions in the browser; tokens.json will be created.

3) Run the bot (tweets every hour)
   - npm start

Notes
- The bot posts one of five test sentences randomly on each run interval.
- With OAuth 1.0a, you must provide API Key and API Key Secret in addition to your Access Token and Secret.
- With OAuth 2.0, token refresh is automatic; if your refresh token becomes invalid, run `npm run auth` again.
- Ensure your Twitter App has the correct permissions and the redirect URL matches exactly (for PKCE).
