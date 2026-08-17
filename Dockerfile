FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .

RUN apt-get update -y && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends ffmpeg curl unzip \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL https://deno.land/install.sh | sh


ENV DENO_INSTALL="/root/.deno"
ENV PATH="${DENO_INSTALL}/bin:${PATH}"
ENV MALLOC_ARENA_MAX=2
ENV NODE_OPTIONS="--max-old-space-size=96"


RUN pip3 install -U pip && pip3 install -U -r requirements.txt

COPY . .

CMD ["bash", "start"]
