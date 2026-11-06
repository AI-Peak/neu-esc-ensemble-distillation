"""Small historical benchmark view; never used as an inference predictor."""
from __future__ import annotations

import csv
import hashlib
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def get_research_summary() -> dict:
    rows = []
    source = ROOT / "reports/baseline_reproduce/metrics/summary.csv"
    with source.open(encoding="utf-8-sig", newline="") as handle:
        for entry in csv.DictReader(handle):
            if entry["setup"] != "mtl":
                continue
            for metric in ("accuracy", "macro_f1"):
                rows.append({
                    "dataset": "neu", "backbone": entry["backbone"], "setup": "mtl",
                    "task": entry["task"], "metric": metric,
                    "mean": float(entry[f"{metric}_mean"]), "std": float(entry[f"{metric}_std"]),
                    "seeds": int(entry["n"]), "seed_ids": [int(s) for s in entry["seeds"].split()],
                    "source": source.relative_to(ROOT).as_posix(),
                    "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                })
    for dataset, relative in (("neu", "reports/improvement/per_run.csv"),
                              ("uit", "reports/uit_vsfc/per_run.csv")):
        source = ROOT / relative
        groups = defaultdict(list)
        with source.open(encoding="utf-8-sig", newline="") as handle:
            for entry in csv.DictReader(handle):
                # NEU MTL already has its audited aggregate above.
                if entry["setup"] not in ({"mtl_ed"} if dataset == "neu" else {"mtl", "mtl_ed"}):
                    continue
                groups[(entry["backbone"], entry["setup"], entry["task"])].append(entry)
        for (backbone, setup, task), group in sorted(groups.items()):
            if len({int(x["seed"]) for x in group}) != len(group):
                raise ValueError(f"Duplicate benchmark seeds in {relative}")
            for metric, column in (("accuracy", "acc"), ("macro_f1", "mf1")):
                values = [float(x[column]) for x in group]
                rows.append({
                    "dataset": dataset, "backbone": backbone, "setup": setup,
                    "task": task, "metric": metric, "mean": statistics.mean(values),
                    "std": statistics.stdev(values) if len(values) > 1 else 0,
                    "seeds": len(group), "seed_ids": sorted(int(x["seed"]) for x in group),
                    "source": relative, "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                })
    return {"rows": rows, "unit": "percent", "selection": "validation macro-F1",
            "note": "Kết quả test lịch sử, mean ± sample std qua nhiều seed. "
                    "Không phải chất lượng bảo đảm của checkpoint đang cài hoặc từng câu mới."}
