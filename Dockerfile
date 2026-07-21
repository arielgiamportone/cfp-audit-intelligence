# ── Stage 1: build deps ───────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencias del servicio web (SIN torch/chromadb/anthropic: la imagen es ligera;
# las páginas de KB/Auditoría IA degradan con aviso vía `import_guard`).
# NOTA: mantener alineado con requirements-deploy.txt (mismas versiones mínimas).
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir \
        "fastapi>=0.111.0" \
        "uvicorn[standard]>=0.30.0" \
        "httpx>=0.27.0" \
        "streamlit>=1.36.0" \
        "pandas>=2.1.0" \
        "numpy>=1.26.0" \
        "pydantic>=2.5.0" \
        "pydantic-settings>=2.1.0" \
        "loguru>=0.7.0" \
        "tenacity>=8.2.0" \
        "requests>=2.31.0" \
        "beautifulsoup4>=4.12.0" \
        "lxml>=4.9.0" \
        "spacy>=3.7.0" \
        "reportlab>=4.0.0" \
        "networkx>=3.2.0" \
        "pyvis>=0.3.2" \
        "plotly>=5.18.0" \
        "altair>=5.2.0" \
        "matplotlib>=3.7.0" \
        "scipy>=1.10.0" \
        "scikit-learn>=1.3.0" \
        "openpyxl>=3.1.0" \
        "python-dotenv>=1.0.0" \
        "PyYAML>=6.0.0" \
        "python-dateutil>=2.8.0" \
        "tqdm>=4.66.0" \
        "rich>=13.7.0" \
        "SQLAlchemy>=2.0.0"

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# System runtime deps: tesseract (OCR), poppler (PDF render)
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-spa \
        poppler-utils \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Download Spanish spaCy model (ignore failure — fallback to blank model)
RUN python -m spacy download es_core_news_sm || echo "spaCy model not available, blank model fallback active"

# Copy application source
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY config/ ./config/

# Create runtime data directories (actual data is mounted via volume)
RUN mkdir -p data/raw data/processed data/reports logs

# Non-root user for security
RUN useradd -m -u 1000 cfp && chown -R cfp:cfp /app
USER cfp

EXPOSE 8000 8501

# Default: run the API
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
