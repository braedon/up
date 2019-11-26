FROM python:3.7-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY *.py /app/
COPY *.html /app/
COPY LICENSE /app/
COPY README.md /app/

ENTRYPOINT ["python", "-u", "main.py"]
