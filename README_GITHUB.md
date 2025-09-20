Publish to GitHub (from Windows PowerShell)

1) Initialize repo and first commit
cd "c:/Users/HAMMAD/Twitter Bot"
git init
git add .
git commit -m "init: wenlambo twitter bot (node + gemini + oauth1)"

2) Create a new repo on GitHub
- Go to https://github.com/new and create an empty repository (no README/license).
- Copy the repo URL, e.g., https://github.com/<your-username>/wenlambo-bot.git

3) Add remote and push
git branch -M main
git remote add origin https://github.com/<your-username>/wenlambo-bot.git
git push -u origin main

Then connect the repo on Railway per README_RAILWAY.md.
