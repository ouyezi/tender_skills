from __future__ import annotations

import logging

import uvicorn

from viewer.config import ViewerSettings


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )
    settings = ViewerSettings.load()
    uvicorn.run("viewer.main:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    main()
