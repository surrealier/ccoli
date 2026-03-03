FROM python:3.11-slim

WORKDIR /app

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY server/requirements-test.txt /tmp/requirements-test.txt
RUN python -m pip install --upgrade pip && \
    pip install -r /tmp/requirements-test.txt

COPY . /app

CMD ["pytest", "-q", "tests/server_tests"]
