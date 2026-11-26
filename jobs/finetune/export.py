"""Step 5 — merge the LoRA adapter into the base model and export a
quantised GGUF that runs on CPU in the model-server container.
Upload the .gguf as a GitHub RELEASE ASSET (never commit weights to git).

  !python jobs/finetune/export.py
  # gh release create model-v1 jobs/finetune/outputs/gguf/scorer-q4_k_m.gguf
"""
from pathlib import Path

import yaml
from unsloth import FastLanguageModel

ROOT = Path(__file__).resolve().parents[2]
C = yaml.safe_load((Path(__file__).parent / "config.yaml").read_text())
model, tok = FastLanguageModel.from_pretrained(str(ROOT / "jobs/finetune/outputs/adapter"),
                                               max_seq_length=C["max_seq_length"], load_in_4bit=False)
out = ROOT / "jobs/finetune/outputs/gguf"
model.save_pretrained_gguf(str(out), tok, quantization_method=C["export"]["quantization"])
print("GGUF written to", out, "- rename to", C["export"]["gguf_name"])
