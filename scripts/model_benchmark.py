"""Measure a real local artifact: cold first inference, warm single, batches 10/100/500."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.inference.registry import ModelRegistry


def _runtime_metadata() -> dict:
    import torch
    versions = {}
    for pkg in ("torch", "transformers", "safetensors", "sentencepiece", "underthesea", "numpy"):
        try:
            versions[pkg] = importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            versions[pkg] = None
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "torch_num_threads": torch.get_num_threads(),
        "torch_num_interop_threads": torch.get_num_interop_threads(),
        "dependencies": versions,
    }


def main():
    import psutil
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-root", type=Path, default=Path("runtime/models"))
    parser.add_argument("--profile", choices=("neu", "uit"), default="neu")
    parser.add_argument("--text-file", type=Path, required=True, help="private UTF-8 file, one sentence per line")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    texts = [x.strip() for x in args.text_file.read_text(encoding="utf-8-sig").splitlines() if x.strip()]
    if not texts:
        raise ValueError("text file is empty")
    registry = ModelRegistry(args.model_root)
    results = []
    for name, count in (("cold_first", 1), ("warm_single", 1), ("batch_10", 10),
                        ("batch_100", 100), ("batch_500", 500)):
        items = [dict(item_id=str(i), revision_id=str(i), text=texts[i % len(texts)]) for i in range(count)]
        started = time.perf_counter()
        predictions = registry.predict(args.profile, items)
        seconds = time.perf_counter() - started
        memory = psutil.Process().memory_info()
        results.append(dict(case=name, rows=count, wall_seconds=seconds,
                            rows_per_second=count / seconds, rss_bytes=memory.rss,
                            peak_rss_bytes=getattr(memory, "peak_wset", None),
                            truncated=sum(x["truncated"] for x in predictions)))
    report = dict(
        profile=args.profile,
        model=registry.status(args.profile),
        environment=_runtime_metadata(),
        definitions={
            "cold_first": "First predict() call on a fresh ModelRegistry instance (includes lazy model/tokenizer/segmenter load + inference).",
            "warm_single": "Second 1-row predict() call after model and segmenter are cached in memory.",
            "batch_10_100_500": "End-to-end predict() wall time including preprocessing, tokenization, dynamic length-sorted microbatches of 8, and softmax.",
        },
        measurements=results,
        note="Local CPU FP32; includes preprocessing and tokenization. Scores are uncalibrated. Texts not saved.",
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
