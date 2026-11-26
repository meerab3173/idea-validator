# syntax=docker/dockerfile:1
# Build from the REPOSITORY ROOT:  docker build -f services/scouts/Dockerfile -t scouts:<sha> .
FROM python:3.12.6-slim AS build
WORKDIR /app
COPY services/scouts/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12.6-slim
RUN useradd -m -u 10001 app
WORKDIR /app
ENV PYTHONPATH=/app PYTHONUNBUFFERED=1
COPY --from=build /install /usr/local
COPY libs/common/common ./common
COPY rubrics /rubrics
COPY services/scouts/src ./src
COPY data/snapshot /app/snapshot
USER 10001
EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
