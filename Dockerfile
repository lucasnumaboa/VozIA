FROM python:3.11-slim

WORKDIR /app

# System deps: audio capture + PIL + pydub (ffmpeg) + screenshot (scrot/xvfb)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libportaudio2 portaudio19-dev \
    libglib2.0-0 libsm6 libxrender1 libxext6 \
    ffmpeg \
    scrot xvfb \
    && rm -rf /var/lib/apt/lists/*

# Persistent directory for uploaded voice reference files
RUN mkdir -p /app/voices

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["python", "app.py"]
