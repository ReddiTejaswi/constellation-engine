import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Satisfy the strict env-driven settings during tests
os.environ.setdefault("MODEL_NAME", "test-model")
os.environ.setdefault("MODEL_BASE_URL", "http://localhost:9/v1")
os.environ.setdefault("MODEL_API_KEY", "test-key")
os.environ.setdefault("RETRIEVAL_PROVIDERS", "pubmed")
os.environ.setdefault("RETRIEVAL_CACHE_DIR", str(ROOT / "tests" / ".cache"))
