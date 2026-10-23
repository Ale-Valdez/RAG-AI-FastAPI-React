FROM python:3.12-slim-bookworm AS runtime

RUN useradd --create-home --uid 10001 appuser
WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
COPY alembic.ini ./
COPY alembic ./alembic
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

FROM runtime AS worker

ENV DOCLING_ARTIFACTS_PATH=/opt/docling/models
ENV TIKTOKEN_CACHE_DIR=/opt/tiktoken
ENV OMP_NUM_THREADS=2
ENV MKL_NUM_THREADS=2
ENV OPENBLAS_NUM_THREADS=2
ENV NUMEXPR_NUM_THREADS=2
# Same CPU index for both. A PyPI torchvision wheel does not register
# torchvision::nms against this torch, and Docling's layout model fails to import.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
        torch torchvision \
    && pip install --no-cache-dir ".[worker]" \
    && python -c "import torchvision" \
    && mkdir -p "${DOCLING_ARTIFACTS_PATH}" "${TIKTOKEN_CACHE_DIR}" \
    && python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')" \
    && docling-tools models download --output-dir "${DOCLING_ARTIFACTS_PATH}" \
    && chown -R appuser:appuser /opt/docling /opt/tiktoken
USER appuser
CMD ["celery", "-A", "app.infrastructure.worker.celery_app:celery_app", "worker", "--loglevel=INFO", "--concurrency=1", "--max-tasks-per-child=1"]

FROM runtime AS api

USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.bootstrap.http:app", "--host", "0.0.0.0", "--port", "8000"]
