FROM python:3.11-slim

WORKDIR /app/server

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY server/requirements.txt /tmp/requirements.txt
RUN python -m pip install --upgrade pip && \
    pip install -r /tmp/requirements.txt

COPY server /app/server

EXPOSE 5001
CMD ["python", "stt_improved.py"]
