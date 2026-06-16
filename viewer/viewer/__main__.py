from __future__ import annotations

import uvicorn

from viewer.config import ViewerSettings


def main() -> None:
    settings = ViewerSettings.load()
    uvicorn.run("viewer.main:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    main()
