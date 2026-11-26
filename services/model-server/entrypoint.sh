#!/bin/sh
set -e
ollama serve &
PID=$!
until ollama list >/dev/null 2>&1; do sleep 1; done
ollama create scorer-lora -f /models/Modelfile
wait $PID
