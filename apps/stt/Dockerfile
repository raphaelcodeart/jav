# La trascrizione della voce di JAVBOT (docs/javbot.md, «Il microfono»):
# Whisper sul nostro server, l'audio non esce mai da qui e non si salva.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HF_HUB_DISABLE_TELEMETRY=1
WORKDIR /app
RUN pip install --no-cache-dir "faster-whisper==1.2.0" "fastapi==0.115.6" "uvicorn==0.34.0" "python-multipart==0.0.20" "requests==2.32.3"

# Il modello dentro l'immagine: all'avvio niente download, e niente rete.
ARG WHISPER_MODEL=small
ENV WHISPER_MODEL=${WHISPER_MODEL} WHISPER_MODELS_DIR=/models
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('${WHISPER_MODEL}', device='cpu', compute_type='int8', download_root='/models')"
ENV HF_HUB_OFFLINE=1

COPY app.py .
EXPOSE 8001
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
