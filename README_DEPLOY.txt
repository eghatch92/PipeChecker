PIPE CHECKER - INTERNET DEPLOYMENT NOTES

This package is ready to deploy to Render.

Important:
- The app does not store pasted deal text.
- The only persistent data is the all-time deal counter in SQLite.
- For the counter to survive restarts and redeploys on Render, attach a persistent disk and set DB_PATH to /var/data/pipe_checker.db.

Files added for internet hosting:
- requirements.txt
- Procfile
- runtime.txt
- .gitignore
- /healthz endpoint in app.py
- rate limiting, size limit, no-cache headers, and generic JSON error handling
