#!/bin/sh
set -e

echo "[entrypoint] waiting for database..."
python - <<'PY'
import asyncio
import os

from sqlalchemy.ext.asyncio import create_async_engine


async def wait_for_db() -> None:
    url = os.environ["DATABASE_URL"]
    last_error: Exception | None = None
    for attempt in range(30):
        engine = create_async_engine(url, pool_pre_ping=True)
        try:
            async with engine.connect():
                pass
            await engine.dispose()
            print("[entrypoint] database is ready")
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            print(f"[entrypoint] db not ready ({attempt + 1}/30): {exc}")
            await engine.dispose()
            await asyncio.sleep(2)
    raise SystemExit(f"database is not available: {last_error}")


asyncio.run(wait_for_db())
PY

echo "[entrypoint] applying migrations..."
alembic upgrade head

echo "[entrypoint] starting bot..."
exec python -m app.main
