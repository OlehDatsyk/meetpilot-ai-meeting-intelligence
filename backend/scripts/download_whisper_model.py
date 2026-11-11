"""Download the local Whisper model at build time so the server never downloads it at runtime.

Usage: python scripts/download_whisper_model.py [model] [target_dir]
Defaults: LOCAL_WHISPER_MODEL (tiny) and LOCAL_WHISPER_MODEL_DIR (./models).
"""

from __future__ import annotations

import os
import sys


def main() -> None:
    model = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("LOCAL_WHISPER_MODEL", "tiny")
    target = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("LOCAL_WHISPER_MODEL_DIR", "./models")
    from faster_whisper import WhisperModel  # downloads from the Hugging Face Hub (Systran/faster-whisper-*)
    WhisperModel(model, device="cpu", compute_type="int8", download_root=target)
    print(f"Whisper model '{model}' is available in {os.path.abspath(target)}")


if __name__ == "__main__":
    main()
