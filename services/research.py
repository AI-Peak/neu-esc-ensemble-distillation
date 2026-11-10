"""Historical multi-seed benchmark summary sourced from audited CSV reports; never used as an inference predictor."""
from __future__ import annotations

import csv
import hashlib
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SETUP_ORDER = ("single", "mtl", "mtl_smart", "mtl_mlm", "mtl_mlm_smart", "mtl_ed")
SETUP_LABELS = {
    "single": "Single-task",
    "mtl": "MTL",
    "mtl_smart": "MTL + SMART",
    "mtl_mlm": "MTL + MLM",
    "mtl_mlm_smart": "MTL + MLM + SMART",
    "mtl_ed": "ED (MTL + OOF Distillation)",
}


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _compute_oof_ablation() -> list[dict]:
    """Compute OOF vs in-sample teacher ablation means/stds from audited NEU-ESC per-run CSVs."""
    oof_path = ROOT / "reports/improvement/per_run.csv"
    ins_path = ROOT / "reports/improvement/insample_per_run.csv"
    oof_sha = _file_sha256(oof_path)
    ins_sha = _file_sha256(ins_path)

    oof_groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    with oof_path.open(encoding="utf-8-sig", newline="") as handle:
        for entry in csv.DictReader(handle):
            if entry["setup"] == "mtl_ed":
                oof_groups[(entry["backbone"], entry["task"])].append(entry)

    ins_groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    with ins_path.open(encoding="utf-8-sig", newline="") as handle:
        for entry in csv.DictReader(handle):
            ins_groups[(entry["bb"], entry["task"])].append(entry)

    # Holm-adjusted p-values across the 8 NEU-ESC ablation tests (Table 5 in paper.tex).
    holm_p = {
        ("phobert", "sentiment", "accuracy"): "<0.001",
        ("phobert", "sentiment", "macro_f1"): "0.061",
        ("phobert", "topic", "accuracy"): "<0.001",
        ("phobert", "topic", "macro_f1"): "0.061",
        ("visobert", "sentiment", "accuracy"): "<0.001",
        ("visobert", "sentiment", "macro_f1"): "0.726",
        ("visobert", "topic", "accuracy"): "<0.001",
        ("visobert", "topic", "macro_f1"): "0.876",
    }

    rows = []
    for backbone in ("phobert", "visobert"):
        for task in ("sentiment", "topic"):
            oof_runs = oof_groups[(backbone, task)]
            ins_runs = ins_groups[(backbone, task)]
            if len({int(x["seed"]) for x in oof_runs}) != len(oof_runs) or len(oof_runs) != 15:
                raise ValueError("Unexpected OOF seed count in reports/improvement/per_run.csv")
            if len({int(x["seed"]) for x in ins_runs}) != len(ins_runs) or len(ins_runs) != 15:
                raise ValueError("Unexpected in-sample seed count in reports/improvement/insample_per_run.csv")
            for metric, column in (("accuracy", "acc"), ("macro_f1", "mf1")):
                oof_vals = [float(x[column]) for x in oof_runs]
                ins_vals = [float(x[column]) for x in ins_runs]
                oof_mean = statistics.mean(oof_vals)
                ins_mean = statistics.mean(ins_vals)
                rows.append({
                    "backbone": backbone,
                    "task": task,
                    "metric": metric,
                    "in_sample_mean": ins_mean,
                    "in_sample_std": statistics.stdev(ins_vals),
                    "oof_mean": oof_mean,
                    "oof_std": statistics.stdev(oof_vals),
                    "delta": oof_mean - ins_mean,
                    "holm_adjusted_p": holm_p[(backbone, task, metric)],
                    "seeds": 15,
                    "sources": [
                        "reports/improvement/insample_per_run.csv",
                        "reports/improvement/per_run.csv",
                    ],
                    "source_sha256": {
                        "reports/improvement/insample_per_run.csv": ins_sha,
                        "reports/improvement/per_run.csv": oof_sha,
                    },
                })
    return rows


def get_research_summary() -> dict:
    rows = []

    # 1. NEU-ESC five baselines per backbone (15 seeds: 42-56).
    neu_base_source = ROOT / "reports/baseline_reproduce/metrics/summary.csv"
    neu_base_sha = _file_sha256(neu_base_source)
    with neu_base_source.open(encoding="utf-8-sig", newline="") as handle:
        for entry in csv.DictReader(handle):
            setup = entry["setup"]
            if setup not in {"single", "mtl", "mtl_smart", "mtl_mlm", "mtl_mlm_smart"}:
                continue
            for metric in ("accuracy", "macro_f1"):
                rows.append({
                    "dataset": "neu",
                    "backbone": entry["backbone"],
                    "setup": setup,
                    "setup_label": SETUP_LABELS[setup],
                    "task": entry["task"],
                    "metric": metric,
                    "mean": float(entry[f"{metric}_mean"]),
                    "std": float(entry[f"{metric}_std"]),
                    "seeds": int(entry["n"]),
                    "seed_ids": [int(s) for s in entry["seeds"].split()],
                    "source": neu_base_source.relative_to(ROOT).as_posix(),
                    "source_sha256": neu_base_sha,
                })

    # 2. NEU-ESC ED (15 seeds: 42-56) and UIT-VSFC four baselines + ED (10 seeds: 42-51).
    for dataset, relative, allowed_setups in (
        ("neu", "reports/improvement/per_run.csv", {"mtl_ed"}),
        ("uit", "reports/uit_vsfc/per_run.csv", {"mtl", "mtl_smart", "mtl_mlm", "mtl_mlm_smart", "mtl_ed"}),
    ):
        source = ROOT / relative
        source_sha = _file_sha256(source)
        groups = defaultdict(list)
        with source.open(encoding="utf-8-sig", newline="") as handle:
            for entry in csv.DictReader(handle):
                if entry["setup"] not in allowed_setups:
                    continue
                groups[(entry["backbone"], entry["setup"], entry["task"])].append(entry)
        for (backbone, setup, task), group in sorted(
            groups.items(),
            key=lambda item: (item[0][0], SETUP_ORDER.index(item[0][1]), item[0][2]),
        ):
            if len({int(x["seed"]) for x in group}) != len(group):
                raise ValueError(f"Duplicate benchmark seeds in {relative}")
            for metric, column in (("accuracy", "acc"), ("macro_f1", "mf1")):
                values = [float(x[column]) for x in group]
                rows.append({
                    "dataset": dataset,
                    "backbone": backbone,
                    "setup": setup,
                    "setup_label": SETUP_LABELS[setup],
                    "task": task,
                    "metric": metric,
                    "mean": statistics.mean(values),
                    "std": statistics.stdev(values) if len(values) > 1 else 0.0,
                    "seeds": len(group),
                    "seed_ids": sorted(int(x["seed"]) for x in group),
                    "source": relative,
                    "source_sha256": source_sha,
                })

    rows.sort(key=lambda r: (
        0 if r["dataset"] == "neu" else 1,
        r["backbone"],
        SETUP_ORDER.index(r["setup"]),
        r["task"],
        r["metric"],
    ))

    return {
        "rows": rows,
        "oof_ablation": _compute_oof_ablation(),
        "unit": "percent",
        "selection": "validation macro-F1",
        "note": (
            "Kết quả test lịch sử (mean ± sample std qua nhiều seed, chọn epoch bằng validation macro-F1). "
            "Không phải chất lượng bảo đảm của checkpoint seed 42 đang cài hoặc từng câu mới."
        ),
        "method_summary": {
            "teacher_models": 30,
            "teacher_structure": "2 backbones (PhoBERT-base-v2, ViSoBERT) × 3 seeds (42, 43, 44) × 5 folds",
            "held_out_predictions_per_train_row": 6,
            "student_architecture": "1 plain MTL model (Linear -> SiLU -> LayerNorm -> 2 linear heads; gamma = 1, w_t = 0.5)",
            "inference_cost": "Chỉ chạy 1 student duy nhất lúc suy luận; không chạy ensemble 30 model, SMART hay MLM.",
            "training_cost": "Teacher cần khoảng 15,65 GPU giờ trên NEU-ESC (3,79 GPU giờ trên UIT-VSFC); mỗi student ED mất ~0,65 GPU giờ trên NEU-ESC.",
        },
        "statistical_protocol": {
            "test": "Two-sided Welch's t-test with Holm-Bonferroni correction (alpha = 0.05)",
            "families": {
                "neu_ed_vs_baselines": 40,
                "uit_ed_vs_baselines": 32,
                "neu_oof_vs_insample_ablation": 8,
            },
            "logit_bias_policy": "Post-hoc logit bias là phân tích phụ (uncorrected paired tests) và không bật trong suy luận chính.",
        },
        "findings": [
            {
                "id": "neu-overall",
                "title": "NEU-ESC (15 seeds, 42–56): ED vượt cả 5 baseline sau Holm correction",
                "detail": (
                    "Trên NEU-ESC, ED đạt trung bình cao nhất ở cả hai backbone và cả hai tác vụ về Accuracy và Macro-F1 "
                    "(toàn bộ 40 phép so sánh Welch + Holm đều có p hiệu chỉnh <= 0,022). Với PhoBERT, ED đạt "
                    "83,51% ± 0,24 (Sentiment Acc), 77,91% ± 0,28 (Sentiment Macro-F1), 79,65% ± 0,27 (Topic Acc) "
                    "và 63,57% ± 0,40 (Topic Macro-F1)."
                ),
            },
            {
                "id": "neu-toxic",
                "title": "Giới hạn lớp hiếm Toxic trên NEU-ESC",
                "detail": (
                    "F1 lớp hiếm Toxic (2,5% dữ liệu huấn luyện) của ED là 83,28% (PhoBERT) và 82,94% (ViSoBERT), "
                    "thấp hơn các thiết lập SMART (85,35% và 84,49%) và Single-task (85,32% và 83,39%). "
                    "Do đó nhãn Toxic chỉ dùng hỗ trợ rà soát, không dùng để tự động kết luận hay kỷ luật."
                ),
            },
            {
                "id": "uit-generalization",
                "title": "UIT-VSFC (10 seeds, 42–51): Cải thiện rõ Topic, Sentiment không khác biệt có ý nghĩa",
                "detail": (
                    "UIT-VSFC chạy 4 baseline MTL (không chạy Single-task). Trong 32 kiểm định Holm, 21 cặp có ý nghĩa "
                    "và ED không thua kém có ý nghĩa ở cặp nào: Topic Accuracy tăng lên 89,71% ± 0,11 (PhoBERT) và "
                    "89,32% ± 0,16 (ViSoBERT, p hiệu chỉnh <= 0,002), trong khi Sentiment Accuracy và Macro-F1 không "
                    "khác biệt có ý nghĩa so với MTL + MLM (p hiệu chỉnh >= 0,121)."
                ),
            },
            {
                "id": "oof-ablation",
                "title": "Ablation OOF vs In-sample teacher trên NEU-ESC (8 kiểm định Holm)",
                "detail": (
                    "Teacher out-of-fold cho Accuracy cao hơn in-sample teacher từ +0,33 đến +0,70 điểm phần trăm "
                    "ở cả 4 ô (p hiệu chỉnh < 0,001), trong khi chênh lệch Macro-F1 không có ý nghĩa thống kê sau "
                    "hiệu chỉnh (p hiệu chỉnh >= 0,061)."
                ),
            },
        ],
    }
