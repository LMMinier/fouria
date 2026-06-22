#!/usr/bin/env python3
"""
Training scaffold for FOURIA.

This script intentionally does not auto-download heavy training dependencies.
Use it as the entry point after installing a GPU training stack:

  pip install transformers peft datasets trl accelerate safetensors

Recommended fine-tune target:
  base model: Qwen/Qwen2.5-Coder-3B-Instruct or matching local 3B Qwen coder
  data: data/training/*.jsonl

Keep copyrighted FL Studio manuals and paid-course transcripts out of training
unless you have permission. Use RAG for reference docs.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "training"


def main():
    files = sorted(DATA.glob("*.jsonl"))
    print("FOURIA LoRA training scaffold")
    print(f"training files: {len(files)}")
    for f in files:
        print(f" - {f}")
    print()
    print("Next implementation step:")
    print(" - load JSONL messages")
    print(" - apply Qwen chat template")
    print(" - train LoRA adapters")
    print(" - export adapter and optionally create a GGUF/Ollama model")


if __name__ == "__main__":
    main()

