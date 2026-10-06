FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY services ./services
COPY infra ./infra
COPY knowledge ./knowledge
COPY evals ./evals
ENV PYTHONPATH=/app/services
USER 65534:65534
CMD ["uvicorn","siteproof.api:app","--host","0.0.0.0","--port","8000"]
