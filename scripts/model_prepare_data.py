"""Copy local CSVs only after exact pinned hash validation, permitting Git CRLF to LF conversion."""
import argparse
from pathlib import Path
import sys
import hashlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src_improvement.neu_esc_improvement import DATASETS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=("neu", "vsfc"), required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.source.resolve() == args.out.resolve():
        raise ValueError("source and prepared output must be separate directories")
    prepared = {}
    for name, expected in DATASETS[args.dataset]["files"].items():
        data = (args.source / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            data = data.replace(b"\r\n", b"\n")
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(f"{name}: cannot match pinned hash (no outputs written)")
        prepared[name] = data
    args.out.mkdir(parents=True, exist_ok=True)
    for name, data in prepared.items():
        (args.out / name).write_bytes(data)
    print(f"Prepared and hash-verified {len(prepared)} files in {args.out}")


if __name__ == "__main__":
    main()
