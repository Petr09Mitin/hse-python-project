FROM ghcr.io/astral-sh/uv:0.9.7@sha256:ba4857bf2a068e9bc0e64eed8563b065908a4cd6bfb66b531a9c424c8e25e142 AS uv
FROM python:3.12-slim-bookworm@sha256:6a0e06f5ba0b373d051aabd3fffb9b873f27f9a2a3a14bcbe37dee6f0e3bbc70
COPY --from=uv /uv /usr/local/bin/uv
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 fonts-dejavu-core ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/receipt-bot
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --extra dev --extra ocr --no-install-project
COPY src ./src
COPY tests ./tests
COPY .gitignore ./
RUN uv sync --frozen --extra dev --extra ocr
ENV PATH="/opt/receipt-bot/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 HF_HUB_OFFLINE=1 PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
CMD ["python", "-m", "receipt_bot"]
