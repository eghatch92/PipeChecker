PIPE CHECKER - LOCAL WEB APP

What it does
- Paste CRM notes, opportunity text, or email chains
- Scores Budget, Authority, Need, and Timeline as Complete / Partial / Missing
- Infers deal stage from pasted text
- Raises red flags for late-stage deals missing key qualification data
- Recommends a next step, a follow-up email, and a call script
- Stores only a persistent all-time deal counter in SQLite
- Does not store your pasted deal content

How to run on Windows
1. Make sure Python 3.11 or newer is installed.
2. Open this folder.
3. Double-click run_pipe_checker.bat
4. Your browser should open to http://127.0.0.1:8000

If the browser does not open automatically
- open your browser manually and go to http://127.0.0.1:8000

Notes
- The command window must stay open while the app is running.
- Only the counter is saved. Deal text is analyzed in memory and not stored.
