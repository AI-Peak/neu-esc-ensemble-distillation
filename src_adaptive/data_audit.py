"""Dataset integrity checks used before any adaptive run."""
from __future__ import annotations
import hashlib, json, unicodedata
from pathlib import Path
from typing import Dict
import pandas as pd

EXPECTED = {"train": 23048, "val": 3305, "test": 6613}

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def audit(data_dir: str | Path) -> Dict:
    root = Path(data_dir)
    frames = {}
    hashes = {}
    for split, n in EXPECTED.items():
        path = root / f"{split}_set.csv"
        if not path.exists():
            raise FileNotFoundError(path)
        frame = pd.read_csv(path)
        if len(frame) != n:
            raise ValueError(f"{path}: expected {n}, got {len(frame)}")
        if frame[["text", "sentiment", "classification"]].isna().any().any():
            raise ValueError(f"{path}: missing values")
        if not frame.sentiment.astype(int).between(0, 3).all():
            raise ValueError(f"{path}: sentiment labels outside 0..3")
        if not frame.classification.astype(int).between(0, 9).all():
            raise ValueError(f"{path}: topic labels outside 0..9")
        frames[split], hashes[split] = frame, sha256(path)
    norm = lambda s: unicodedata.normalize("NFC", " ".join(str(s).split()))
    overlap = {}
    for left, right in (("train", "val"), ("train", "test"), ("val", "test")):
        a, b = set(frames[left].text.map(norm)), set(frames[right].text.map(norm))
        overlap[f"{left}_{right}"] = len(a & b)
    return {"row_counts": {k: len(v) for k, v in frames.items()}, "sha256": hashes,
            "overlap_normalized_text": overlap,
            "label_counts": {k: {"sentiment": v.sentiment.value_counts().sort_index().to_dict(),
                                 "topic": v.classification.value_counts().sort_index().to_dict()}
                             for k, v in frames.items()}}

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(); p.add_argument("data_dir"); p.add_argument("--out")
    args = p.parse_args(); result = audit(args.data_dir)
    text = json.dumps(result, indent=2, ensure_ascii=False)
    print(text)
    if args.out: Path(args.out).write_text(text, encoding="utf-8")
