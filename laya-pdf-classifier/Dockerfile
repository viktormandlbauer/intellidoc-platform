FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    USE_TF=0 \
    HF_HOME=/models \
    PDFCLF_CONFIG=/app/config.yaml

# Tesseract is Docling's OCR engine for scanned PDFs (set extraction.ocr: false to skip);
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
COPY pdfclf ./pdfclf
RUN pip install --no-cache-dir .

COPY config.example.yaml /app/config.yaml

EXPOSE 8080
VOLUME ["/models"]
CMD ["uvicorn", "pdfclf.server:app_from_env", "--factory", "--host", "0.0.0.0", "--port", "8080"]
