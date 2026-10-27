FROM python:3.12-slim
# poppler for pdftotext (spec diff, passages), Pango libraries for WeasyPrint (PDF report)
RUN apt-get update && apt-get install -y --no-install-recommends \
        poppler-utils libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libffi8 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.8.4 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev --extra pdf --no-install-project
COPY . .
ENV PATH="/app/.venv/bin:$PATH" DATA_DIR=/app/data
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
