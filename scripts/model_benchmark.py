"""Measure a real local artifact: cold first inference, warm single, batches 10/100/500."""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.inference.registry import ModelRegistry


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
    report = dict(profile=args.profile, model=registry.status(args.profile), measurements=results,
                  note="Local CPU FP32; includes tokenization. Scores are uncalibrated. Texts not saved.")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
