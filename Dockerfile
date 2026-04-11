FROM python:3.14-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    git-lfs \
  && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 gitporter

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=gitporter:gitporter . .

USER gitporter

ENTRYPOINT ["python", "main.py"]
