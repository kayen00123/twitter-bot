Deploying to Railway

1) Push this project to GitHub
- Ensure .gitignore excludes config.json and tokens.json (already set).
- Initialize git, commit, and push to your repository.

2) Create a new Railway project from GitHub
- On https://railway.app, create a project and select your repo.
- Railway will detect Node.js and install dependencies.

3) Configure environment variables in Railway (Settings -> Variables)
- API_KEY = <your Twitter API Key>
- API_SECRET = <your Twitter API Key Secret>
- ACCESS_TOKEN = <your Twitter Access Token>
- ACCESS_TOKEN_SECRET = <your Twitter Access Token Secret>
- GEMINI_API_KEY = <your Gemini key>
- GEMINI_MODEL = gemini-1.5-flash (optional)
- POST_EVERY_HOURS = 1 (or your desired interval; min effective is 1 minute)

4) Deploy
- Set the deploy service to run: npm start
- Railway will build and start the process. Check Logs for runtime output.

Notes
- This service runs continuously and posts at the configured interval.
- If logs indicate auth or API errors, verify your environment variables are correct.
- For PKCE OAuth2 you would also need CLIENT_ID and a stateful token store; the current Railway guide assumes OAuth 1.0a for simplicity.
