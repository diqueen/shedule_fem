FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first (better layer caching).
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --upgrade pip && pip install .

# Copy the rest of the project.
COPY alembic.ini ./
COPY migrations ./migrations
COPY docker ./docker
RUN chmod +x docker/entrypoint.sh

CMD ["./docker/entrypoint.sh"]
