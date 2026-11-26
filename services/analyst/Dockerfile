# syntax=docker/dockerfile:1
# Build from the REPOSITORY ROOT:  docker build -f services/analyst/Dockerfile -t analyst:<sha> .
FROM python:3.12.6-slim AS build
WORKDIR /app
COPY services/analyst/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12.6-slim
RUN useradd -m -u 10001 app
WORKDIR /app
ENV PYTHONPATH=/app PYTHONUNBUFFERED=1
COPY --from=build /install /usr/local
# Download the embedding/rerank models at build time so pods start offline.
ENV HF_HOME=/models
RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2'); CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')" && chown -R 10001 /models
COPY libs/common/common ./common
COPY rubrics /rubrics
COPY services/analyst/src ./src
USER 10001
EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
