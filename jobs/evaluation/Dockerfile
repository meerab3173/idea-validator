# Build from the repository root: docker build -f jobs/evaluation/Dockerfile -t evaluation:<sha> .
FROM python:3.12.6-slim
RUN useradd -m -u 10001 app
WORKDIR /repo
COPY jobs/evaluation/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY eval ./eval
COPY jobs/evaluation ./jobs/evaluation
ENV REPO_ROOT=/repo
USER 10001
CMD ["python", "jobs/evaluation/harness.py"]
