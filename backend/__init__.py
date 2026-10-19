"""AfriSearch AI backend."""
import os
from pathlib import Path

__version__ = "0.2.0"

# Unless HF_HOME is set explicitly, keep model weights in a dedicated cache
# directory (~/.cache/hf_models) instead of the default ~/.cache/huggingface.
# Set here because huggingface_hub reads it when first imported.
os.environ.setdefault("HF_HOME", str(Path.home() / ".cache" / "hf_models"))
