# syntax=docker/dockerfile:1
# Vlade-RAG server image: API, CLI and native engine (extra "server", ADR-0003).
# Build context: repository root.

ARG PYTHON_IMAGE=python:3.12-slim-trixie

# ---------------------------------------------------------------- native engine (Rust)
FROM ${PYTHON_IMAGE} AS native
ARG RUST_VERSION=1.100.0
ARG MATURIN_VERSION=1.16.0
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates build-essential \
 && rm -rf /var/lib/apt/lists/*
ENV CARGO_HOME=/usr/local/cargo RUSTUP_HOME=/usr/local/rustup PATH=/usr/local/cargo/bin:$PATH
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
    | sh -s -- -y --profile minimal --default-toolchain ${RUST_VERSION}
RUN pip install --no-cache-dir --root-user-action=ignore maturin==${MATURIN_VERSION}
WORKDIR /src
COPY Cargo.toml Cargo.lock ./
COPY packages/rust packages/rust
COPY LICENSE ./
RUN maturin build --release --locked -m packages/rust/vlade_rag_core/Cargo.toml -o /wheels

# ---------------------------------------------------------------- runtime
FROM ${PYTHON_IMAGE} AS runtime
COPY --from=ghcr.io/astral-sh/uv:0.8.12 /uv /usr/local/bin/uv
WORKDIR /app

# Locked third-party dependencies first, for layer caching.
COPY pyproject.toml uv.lock ./
COPY packages/python/pyproject.toml packages/python/pyproject.toml
COPY packages/rust/vlade_rag_core/pyproject.toml packages/rust/vlade_rag_core/pyproject.toml
RUN uv export --frozen --no-dev --package vlade-rag \
      --extra api --extra cli --extra postgres --extra ollama --extra openai --extra otel \
      --extra cache --extra mcp --extra s3 --extra graph --no-emit-workspace -o /tmp/requirements.txt \
 && uv pip install --system --no-cache -r /tmp/requirements.txt

# Workspace packages.
COPY LICENSE ./
COPY packages/python packages/python
COPY --from=native /wheels /wheels
RUN uv pip install --system --no-cache --no-deps /wheels/*.whl ./packages/python \
 && rm -rf /wheels /root/.cache

RUN useradd --system --uid 10001 --no-create-home vlade \
 && mkdir -p /data/objects /data/graph && chown -R vlade /data
USER vlade

ENV VLADE_API__HOST=0.0.0.0 \
    VLADE_API__PORT=8000 \
    VLADE_OBJECT_STORAGE__PATH=/data/objects \
    PYTHONUNBUFFERED=1
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2).status == 200 else 1)"]
CMD ["vlade-rag", "api", "serve"]
