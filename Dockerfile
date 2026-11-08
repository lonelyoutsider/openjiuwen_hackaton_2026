FROM python:3.12.14-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 HOME=/tmp \
    XDG_CACHE_HOME=/tmp/.cache HF_HOME=/tmp/huggingface \
    MPLCONFIGDIR=/tmp/matplotlib
WORKDIR /app
COPY requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir --only-binary=:all: -r /app/requirements.lock
COPY harness /app/harness
COPY run_agent.py /app/run_agent.py
ENTRYPOINT ["python", "/app/run_agent.py"]
