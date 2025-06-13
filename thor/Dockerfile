FROM python:3.11-slim as base

ENV PYTHONFAULTHANDLER=1 \
    PYTHONHASHSEED=random \
    PYTHONUNBUFFERED=1

WORKDIR /app

FROM base as builder

ENV PIP_DEFAULT_TIMEOUT=100 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VERSION=2.1.3

RUN pip install "poetry==$POETRY_VERSION"

COPY pyproject.toml poetry.lock README.md ./

RUN poetry config virtualenvs.create false && \
    poetry install --only main --no-interaction --no-ansi --no-root

COPY . .
RUN poetry build --format wheel -o dist/ --no-interaction --no-ansi




# ---- Final Stage ----
FROM base as final

WORKDIR /app

# Copy the built wheels from the builder stage
COPY --from=builder /app/dist/ /tmp/dist/

# Install the wheel using pip.
# This will also install any dependencies specified in the wheel's metadata.
RUN pip install --no-cache-dir /tmp/dist/*.whl && \
    rm -rf /tmp/dist/

ENTRYPOINT ["thor"]