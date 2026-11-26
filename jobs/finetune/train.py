"""Step 4 — QLoRA fine-tune on a free GPU (Colab / Kaggle T4).

Colab:
  !git clone https://github.com/<you>/idea-validator && cd idea-validator
  !pip install "unsloth[colab-new]" trl==0.11.4 datasets pyyaml
  !python jobs/finetune/train.py
  # then: !python jobs/finetune/export.py   (merge + GGUF)
Watch eval_loss each `eval_every_steps`; stop if it rises while train loss falls.
"""
from pathlib import Path

import yaml
from datasets import load_dataset
from transformers import TrainingArguments
from trl import SFTTrainer
from unsloth import FastLanguageModel

ROOT = Path(__file__).resolve().parents[2]
C = yaml.safe_load((Path(__file__).parent / "config.yaml").read_text())

model, tok = FastLanguageModel.from_pretrained(C["base_model"], max_seq_length=C["max_seq_length"],
                                               load_in_4bit=C["load_in_4bit"])
model = FastLanguageModel.get_peft_model(model, r=C["lora"]["r"], lora_alpha=C["lora"]["alpha"],
                                         lora_dropout=C["lora"]["dropout"],
                                         target_modules=C["lora"]["target_modules"], random_state=C["train"]["seed"])

ds = load_dataset("json", data_files={"train": str(ROOT / "data/finetune/train.jsonl"),
                                      "test": str(ROOT / "data/finetune/test.jsonl")})
fmt = lambda ex: {"text": tok.apply_chat_template(ex["messages"], tokenize=False)}  # noqa: E731
ds = ds.map(fmt, remove_columns=["messages", "meta"])

t = C["train"]
trainer = SFTTrainer(
    model=model, tokenizer=tok, train_dataset=ds["train"], eval_dataset=ds["test"],
    dataset_text_field="text", max_seq_length=C["max_seq_length"],
    args=TrainingArguments(output_dir=str(ROOT / "jobs/finetune/outputs"), num_train_epochs=t["epochs"],
                           learning_rate=t["learning_rate"], per_device_train_batch_size=t["per_device_batch_size"],
                           gradient_accumulation_steps=t["gradient_accumulation"], warmup_ratio=t["warmup_ratio"],
                           eval_strategy="steps", eval_steps=t["eval_every_steps"], logging_steps=5,
                           save_strategy="steps", save_steps=t["eval_every_steps"], load_best_model_at_end=True,
                           seed=t["seed"], fp16=True, report_to="none"))
trainer.train()
model.save_pretrained(str(ROOT / "jobs/finetune/outputs/adapter"))
tok.save_pretrained(str(ROOT / "jobs/finetune/outputs/adapter"))
Path(ROOT / "jobs/finetune/outputs/log_history.json").write_text(__import__("json").dumps(trainer.state.log_history))
