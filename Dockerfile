FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    USE_TF=0 \
    HF_HOME=/models \
    INTELLIDOC_CONFIG=/app/config.yaml

# Tesseract is Docling's OCR engine for scanned PDFs (set parsing.ocr: false to skip);
# libgl1/libglib2.0-0 are needed by OpenCV, which Docling pulls in.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-deu tesseract-ocr-eng libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# CPU-only torch keeps the image ~2 GB smaller. For NVIDIA GPUs build with
#   --build-arg TORCH_INDEX=https://download.pytorch.org/whl/cu124
ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir torch --index-url ${TORCH_INDEX}

COPY pyproject.toml ./
COPY src ./src
# engine API image: api + worker extras; [laya] adds the optional zero-shot classifier
# (a Document API-only image needs just ".[api]", no torch)
RUN pip install --no-cache-dir ".[api,worker,laya]"

COPY config.example.yaml /app/config.yaml

EXPOSE 8080
VOLUME ["/models"]
CMD ["uvicorn", "intellidoc.engine.api.app:app_from_env", "--factory", "--host", "0.0.0.0", "--port", "8080"]
