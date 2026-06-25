from __future__ import annotations

import logging
import os

import uvicorn

from viewer.config import ViewerSettings


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("doc_chunk.llm").setLevel(logging.INFO)
    logging.getLogger("tender_insights.interpret.llm").setLevel(logging.INFO)
    settings = ViewerSettings.load()
    reload_raw = os.environ.get("VIEWER_RELOAD", "1")
    reload = reload_raw.strip().lower() in {"1", "true", "yes", "on"}
    uvicorn.run("viewer.main:app", host=settings.host, port=settings.port, reload=reload)


if __name__ == "__main__":
    main()
