"""ASGI entry point: `python -m backend.server`."""
from __future__ import annotations

import logging

import uvicorn

from backend.config.settings import get_settings


def main() -> None:
    s = get_settings()
    logging.basicConfig(level=getattr(logging, s.log_level.upper(), logging.INFO))
    uvicorn.run(
        "backend.api.app:app",
        host=s.host,
        port=s.port,
        reload=False,
        timeout_graceful_shutdown=2,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
