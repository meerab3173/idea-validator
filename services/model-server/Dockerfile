# Fine-tuned scorer (M10) served by Ollama (OpenAI-compatible API on :11434).
# The merged + quantised GGUF is NOT in git: Jenkins downloads it from the
# GitHub release before `docker build` (scripts/fetch_model.sh) and passes it in.
FROM ollama/ollama:0.3.12
ARG MODEL_FILE=scorer-q4_k_m.gguf
COPY services/model-server/Modelfile /models/Modelfile
COPY models/${MODEL_FILE} /models/scorer.gguf
COPY --chmod=755 services/model-server/entrypoint.sh /entrypoint.sh
RUN useradd -m -u 10001 app && mkdir -p /home/app/.ollama && chown -R 10001 /models /home/app
USER 10001
ENV OLLAMA_HOST=0.0.0.0:11434 HOME=/home/app
EXPOSE 11434
ENTRYPOINT ["/entrypoint.sh"]
