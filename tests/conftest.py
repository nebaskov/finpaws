from __future__ import annotations

import os

# Set before anything imports app.config. The 127.0.0.1:9 URLs ensure no test path can reach
# a real LLM/embeddings endpoint and hang — it fails fast and offline instead.
os.environ.setdefault("PII_REDACT", "true")
os.environ.setdefault("HLEDGER_MIRROR", "false")
os.environ.setdefault("LOG_JSON", "false")
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("LLM_BASE_URL", "http://127.0.0.1:9/v1")
os.environ.setdefault("EMBEDDING_API_KEY", "test-key")
os.environ.setdefault("EMBEDDING_BASE_URL", "http://127.0.0.1:9/v1")
os.environ.setdefault("JWT_SECRET", "0123456789abcdef0123456789abcdef0123456789abcdef")
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")
