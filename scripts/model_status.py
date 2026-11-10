"""Inspect locally installed artifacts without downloading or training anything."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.inference.registry import ModelRegistry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-root", type=Path, default=Path("runtime/models"))
    parser.add_argument("--profile", choices=("neu", "uit", "all"), default="all",
                        help="Profile to inspect (default: all)")
    parser.add_argument("--load", action="store_true", help="also load weights/tokenizer and predict a private probe")
    args = parser.parse_args()
    target_profiles = ("neu", "uit") if args.profile == "all" else (args.profile,)
    registry = ModelRegistry(args.model_root)
    rows = []
    for profile in target_profiles:
        row = dict(profile=profile, **registry.status(profile))
        if args.load and row["available"]:
            try:
                registry.predict(profile, [dict(item_id="probe", revision_id="probe", text="Kiểm tra mô hình.")])
                row["load_verified"] = True
            except Exception as exc:
                row.update(available=False, reason=str(exc), load_verified=False)
        rows.append(row)
    print(json.dumps(rows, indent=2, ensure_ascii=False))
    return 0 if all(row["available"] for row in rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
