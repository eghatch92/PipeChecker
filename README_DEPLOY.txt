Render deploy notes

Required env vars:
- DB_PATH=/var/data/pipe_checker.db
- ADMIN_EXPORT_KEY=your-secret-string

Optional AI env vars:
- OPENAI_API_KEY=your-server-side-openai-key
- OPENAI_MODEL=gpt-5-mini

If OPENAI_API_KEY is not set, Pipe Checker still works and falls back to built-in coaching templates.
