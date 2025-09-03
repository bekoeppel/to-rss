FROM python:3.14-slim

WORKDIR /app

COPY requirements.txt requirements.txt
# mwparserfromhell ships no cp314 wheel, so its C tokenizer is compiled here.
# gcc is dropped again afterwards to keep the image slim.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libc6-dev \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y gcc libc6-dev \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

COPY . .

EXPOSE 8080

CMD ["gunicorn", "-b", "0.0.0.0:8080", "server:app"]

