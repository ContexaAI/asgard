FROM python:3.11-slim

RUN export DEBIAN_FRONTEND=noninteractive && apt-get update && apt-get upgrade -y

WORKDIR /app

COPY poetry.lock pyproject.toml /app/
RUN poetry config virtualenvs.create false && poetry install --no-root

COPY . /app
RUN poetry run pip install -e .

ENTRYPOINT ["thor"]


    