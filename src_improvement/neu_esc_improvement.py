"""Group 5 improvement runner: src_baseline/neu_esc_kaggle.py (the baseline, left untouched) plus

  mtl_ed       ED (Ensemble Distillation): plain mtl plus a fixed teacher, an ensemble of out-of-fold
               predictions on the training set, distilled from epoch 1 on (gamma * KL(ensemble || model)).
               Its targets come from `train --fold k --num-folds N` runs (each trains on the other folds
               and predicts its own fold) and `ensemble-targets`, which averages their probabilities
               per training row.

The baseline setups (st_sentiment, st_topic, mtl, mtl_smart, mtl_mlm, mtl_mlm_smart) run here give
the same results as in the baseline runner. Changes to the baseline code: the setup and constants
above, the fold split, the ED loss term in train(), predict() restoring the model's mode,
and the extra output oof.npz.

Baseline docstring:
Lean NEU-ESC reproduction runner for Kaggle T4, following the authors' public code.

Reference: hung20gg/multi-task-bert @ b5637cc0 (copies in reports/method/reference/).
Deliberate deviations from that code, all recorded in each run's config.json:
  - fp16 autocast + GradScaler (T4 has no bf16; the authors trained in fp32).
  - Batch 128 is split into micro-batches with gradient accumulation, padded per micro-batch.
  - SMART skips the authors' first perturbed forward: its noise gradient is always None
    because `.long()` cuts the graph, so that forward never changes the result.
  - MTL selection uses the best mean validation macro-F1 over both tasks; the authors saved
    every epoch from 4 on and picked one by hand.
By default best weights stay in CPU RAM. With --export-model-root a full pinned ViSoBERT ED
student is saved, reloaded and parity-verified before atomic deployment publication.

Subcommands:
  fetch     download the authors' CSV splits and check SHA-256
  prefetch  download pinned model/tokenizer revisions into the HF cache
  train     one run: --backbone {phobert,visobert} --setup {st_sentiment,st_topic,mtl,mtl_smart,
            mtl_mlm,mtl_mlm_smart,mtl_ed} --seed N [--fold k --num-folds N]
  ensemble-targets  average out-of-fold train predictions of fold runs into an mtl_ed target file
  --dataset vsfc    run any of the above on UIT-VSFC instead of NEU-ESC (same hyperparameters)
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import random
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np

# Kaggle images ship TensorFlow; keep transformers on PyTorch only. PhoBERT's pinned revision
# has only pytorch_model.bin, and without this flag transformers fetches a safetensors copy from
# an auto-conversion PR branch, which is a different revision than the pinned one.
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("DISABLE_SAFETENSORS_CONVERSION", "1")

AUTHOR_COMMIT = "b5637cc0a8a7b5e88e794d180c11902405548eb5"
DATA_URL = f"https://raw.githubusercontent.com/hung20gg/multi-task-bert/{AUTHOR_COMMIT}/dataset/{{name}}"
# Hashes from reports/source/download_ledger.json.
DATA_FILES = {
    "train_set.csv": "8a18a73ca21105e0b424829cc41395719be98dd7f01bf3d962eca86e7a1501ec",
    "val_set.csv": "0b2567fe5374cf9b8d22de92ce71d3f9bfa036dffac46fa6f7a5650e85c81169",
    "test_set.csv": "cdd81b2c7b96752f9f45d05e231682fcd6c380f40273dac521425ceff71ab312",
    "train_set_processed.csv": "7ca23b39e8e917de5c81745b0be2f4bb0e085fdc6173882479ecb2ed8e9ebe96",
    "val_set_processed.csv": "948578e4b92df56117fd38d8edaee8d98f11adbd38611d6faee655008adea626",
    "test_set_processed.csv": "bf850a67db6f9dd48df2adc5aa181e63e052e526361a1e9f0e6179bf582dc2e4",
}
SPLIT_SIZES = {"train": 23048, "val": 3305, "test": 6613}
NUM_LABELS = {"sentiment": 4, "topic": 10}
TASKS = ("sentiment", "topic")
# Second dataset (generalisation check): UIT-VSFC (Nguyen et al., KSE 2018), official
# train/dev/test split from the UIT-NLP Google Drive files used by the HF loader
# uitnlp/vietnamese_students_feedback@7b56c6cb. Built by data/UIT-VSFC/README.md into the same CSV
# layout (text, sentiment, classification); the _processed copies are word-segmented with
# underthesea 9.5.0 for PhoBERT. No download URL: the CSVs ship with the repo / kernel.
DATASETS = {
    "neu": {"files": DATA_FILES, "url": DATA_URL, "split_sizes": SPLIT_SIZES, "num_labels": NUM_LABELS},
    "vsfc": {"files": {
        "train_set.csv": "3d636af567e2ddc2c0aa3f93b7a87755526974a57a070ff15b8fa9512bdbbf50",
        "val_set.csv": "a5e07e9d95e0b2fa08c033a49d80ca22b2a40e7a122539e92b3674636e0eb801",
        "test_set.csv": "b3e7a59945d7ca49f135bb857ab01c4ffb5c7c0d73db825ae5a05fed9cc7beb5",
        "train_set_processed.csv": "9b96dca185a8a54e2073a84762054f0e619e514292adee3b447a687c7af1db5c",
        "val_set_processed.csv": "e9431f5d3cb577270062816950fd07e611f80f8d6ed53c34205b4c55664730b3",
        "test_set_processed.csv": "7439de60438951aa9db58ee379d315840c386d070ee259502116c65b1c5c7163",
    }, "url": None, "split_sizes": {"train": 11426, "val": 1583, "test": 3166},
        "num_labels": {"sentiment": 3, "topic": 4}},
}
DATASET = "neu"


def use_dataset(name):
    """Point the module-level data constants at one dataset (NEU-ESC unless --dataset says otherwise)."""
    global DATASET, DATA_FILES, DATA_URL, SPLIT_SIZES, NUM_LABELS
    DATASET = name
    spec = DATASETS[name]
    DATA_FILES, DATA_URL, SPLIT_SIZES, NUM_LABELS = (spec["files"], spec["url"], spec["split_sizes"],
                                                     spec["num_labels"])

# Revisions pinned on 2026-10-11 (docs/FINDINGS.md). PhoBERT reads the authors' pre-segmented CSVs,
# exactly as train.py / trainmultihead.py do for any model name containing "vinai".
BACKBONES = {
    "phobert": {"model_id": "vinai/phobert-base-v2",
                "revision": "86cd7fd4c148980922ac11a2cf5e257f2ba639e1", "processed": True},
    "visobert": {"model_id": "uitnlp/visobert",
                 "revision": "196a62afad9cbe4f52a54aabad828b13f0eec59a", "processed": False},
}

# Hyperparameters from trainer/base_trainer.py + train.py (ST) and
# Trainer/head_trainer.py + trainmultihead.py (MTL).
SETUPS = {
    "st_sentiment": {"tasks": ("sentiment",), "epochs": 15, "adam_eps": 1e-8, "lr_end": 0.2,
                     "patience": 4, "smart": False, "micro_batch": 64},
    "st_topic": {"tasks": ("topic",), "epochs": 15, "adam_eps": 1e-8, "lr_end": 0.2,
                 "patience": 4, "smart": False, "micro_batch": 64},
    "mtl": {"tasks": TASKS, "epochs": 20, "adam_eps": 5e-9, "lr_end": 0.1,
            "patience": None, "smart": False, "micro_batch": 64},
    "mtl_smart": {"tasks": TASKS, "epochs": 20, "adam_eps": 5e-9, "lr_end": 0.1,
                  "patience": None, "smart": True, "micro_batch": 32},
    # Trainer/mlm_3head_trainer.py (= trainer/mlm_head_trainer.py) run by trainmultihead.py with
    # epochs=20: loss L_s + L_t + L_MLM / avg_mask (weights 1/1), LinearLR to (0.15 / 20) * 30 = 0.225.
    # That trainer always adds SMART (its `if self.is_smart` is commented out); mtl_mlm is the row
    # Table 6 reports without SMART, i.e. the same trainer with SMART switched off.
    "mtl_mlm": {"tasks": TASKS, "epochs": 20, "adam_eps": 5e-9, "lr_end": 0.225,
                "patience": None, "smart": False, "micro_batch": 32, "mlm": True},
    "mtl_mlm_smart": {"tasks": TASKS, "epochs": 20, "adam_eps": 5e-9, "lr_end": 0.225,
                      "patience": None, "smart": True, "micro_batch": 16, "mlm": True},
}
COMMON = {"lr": 2e-5, "weight_decay": 0.01, "batch_size": 128, "max_length": 128,
          "eval_batch_size": 128, "mtl_task_weight": 0.5}
# utils/loss_function.py SMARTLoss defaults as used by head_trainer (weight 0.02).
SMART = {"weight": 0.02, "noise_var": 1e-5, "norm_eps": 1e-6, "num_steps": 1}
# utils/dataloader.py DataCollatorHandMade + architecture/bert3head_mlm/model.py.
MLM = {"mask_prob": 0.3, "head_vocab": 64001, "random_ids": 64000}

# ED: plain mtl plus the ensemble KD term. The teacher is ready from the first step, so it runs from epoch 1.
SETUPS["mtl_ed"] = {**SETUPS["mtl"], "ens_kd": True}
ED = {"gamma": 1.0}
FOLD_SEED = 2026  # fold assignment is fixed across training seeds and backbones


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def code_provenance():
    """Hash of this file (the only code that changes results) and the git commit when there is one.

    Runs copied in from a Kaggle Dataset have no git metadata; runner_sha256 still identifies them.
    """
    here = Path(__file__).resolve()
    info = {"runner_sha256": sha256_file(here), "git_commit": None, "git_dirty": None}
    try:
        def git(*args):
            return subprocess.run(["git", "-C", str(here.parent), *args],
                                  capture_output=True, text=True, timeout=10)
        head = git("rev-parse", "HEAD")
        if head.returncode == 0:
            info["git_commit"] = head.stdout.strip()
            # Untracked or modified runner counts as dirty: the commit alone does not identify it.
            info["git_dirty"] = bool(git("status", "--porcelain", "--", str(here)).stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return info


# ---------------------------------------------------------------- data

def fetch_data(data_dir):
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    for name, expected in DATA_FILES.items():
        target = data_dir / name
        if not target.exists() or sha256_file(target) != expected:
            if DATA_URL is None:
                raise RuntimeError(f"{target} missing or changed; {DATASET} has no download URL")
            log(f"download {name}")
            urllib.request.urlretrieve(DATA_URL.format(name=name), target)
        actual = sha256_file(target)
        if actual != expected:
            raise RuntimeError(f"SHA-256 mismatch for {name}: {actual}")
    log(f"data OK in {data_dir}")


def load_split(data_dir, split, processed):
    import pandas as pd
    name = f"{split}_set{'_processed' if processed else ''}.csv"
    path = Path(data_dir) / name
    if sha256_file(path) != DATA_FILES[name]:
        raise RuntimeError(f"{path} does not match the pinned author CSV; run fetch")
    frame = pd.read_csv(path)
    labels = {}
    for task, column in (("sentiment", "sentiment"), ("topic", "classification")):
        values = frame[column].to_numpy(dtype=float)
        if not np.all(np.isfinite(values)) or not np.all(values == np.round(values)):
            raise ValueError(f"{name}: non-integer {column} labels")
        labels[task] = values.astype(np.int64)
        if labels[task].min() < 0 or labels[task].max() >= NUM_LABELS[task]:
            raise ValueError(f"{name}: {column} label out of range")
    texts = frame["text"].astype(str).tolist()
    if len(texts) != SPLIT_SIZES[split]:
        raise ValueError(f"{name}: expected {SPLIT_SIZES[split]} rows, got {len(texts)}")
    return texts, labels, name


def sample_ids(split, count):
    """IDs in the format of the repo's data pipeline (docs/FINDINGS.md), e.g. test:000000:cdd81b2c7b96:
    split, zero-based CSV row, then the raw CSV's SHA-256 prefix. The authors' _processed.csv files are
    row-aligned with the raw ones, so PhoBERT and ViSoBERT runs share the same IDs."""
    prefix = DATA_FILES[f"{split}_set.csv"][:12]
    name = "validation" if split == "val" else split
    return np.array([f"{name}:{row:06d}:{prefix}" for row in range(count)])


def fold_rows(num_train, fold, num_folds):
    """Training rows held out in `fold`: every num_folds-th row of one fixed permutation."""
    return np.sort(np.random.RandomState(FOLD_SEED).permutation(num_train)[fold::num_folds])


def encode_texts(tokenizer, texts, max_length):
    # Same call shape as utils/dataloader.py (special tokens, truncation at 128), but without
    # padding: each micro-batch is padded to its own longest row. Logits do not change because
    # padded positions are masked out of attention.
    encoded = tokenizer(texts, add_special_tokens=True, truncation=True, max_length=max_length)
    return [np.asarray(ids, dtype=np.int64) for ids in encoded["input_ids"]]


def collate(sequences, indices, pad_id):
    import torch
    width = max(len(sequences[i]) for i in indices)
    ids = torch.full((len(indices), width), pad_id, dtype=torch.long)
    mask = torch.zeros((len(indices), width), dtype=torch.long)
    for row, index in enumerate(indices):
        seq = sequences[index]
        ids[row, :len(seq)] = torch.from_numpy(seq)
        mask[row, :len(seq)] = 1
    return ids, mask


# ---------------------------------------------------------------- model

def build_model(backbone_cfg, setup_cfg, model_path):
    import torch
    from torch import nn
    from transformers import AutoModel, AutoModelForSequenceClassification

    source = model_path or backbone_cfg["model_id"]
    kwargs = {"output_loading_info": True}
    if not model_path:
        kwargs["revision"] = backbone_cfg["revision"]
    tasks = setup_cfg["tasks"]

    if len(tasks) == 1:
        encoder, info = AutoModelForSequenceClassification.from_pretrained(
            source, num_labels=NUM_LABELS[tasks[0]], **kwargs)

        class SingleTask(nn.Module):
            def __init__(self):
                super().__init__()
                self.encoder = encoder

            def forward(self, input_ids, attention_mask):
                return (self.encoder(input_ids=input_ids, attention_mask=attention_mask).logits,)

        return SingleTask(), info

    encoder, info = AutoModel.from_pretrained(source, **kwargs)
    hidden = encoder.config.hidden_size

    mlm = setup_cfg.get("mlm", False)

    class Linear2Head(nn.Module):
        """architecture/bert2head/model.py: BertLinear2HEAD. Its Dropout(0.2) layers are
        declared but never called in forward, so they are left out here.

        With mlm (architecture/bert3head_mlm/model.py: BertLinear3HEAD) a second encoder pass over
        the masked input feeds Linear -> SiLU -> LayerNorm -> Linear(64001) on every token; only the
        masked positions enter the loss, so the head is applied to those rows alone (same values)."""

        def __init__(self):
            super().__init__()
            self.encoder = encoder
            self.fc_input = nn.Linear(hidden, hidden)
            self.activation = nn.SiLU()
            self.ln1 = nn.LayerNorm(hidden)
            self.out_sent = nn.Linear(hidden, NUM_LABELS["sentiment"])
            self.out_clas = nn.Linear(hidden, NUM_LABELS["topic"])
            if mlm:
                self.fc_input2 = nn.Linear(hidden, hidden)
                self.ln2 = nn.LayerNorm(hidden)
                self.mlm_out = nn.Linear(hidden, MLM["head_vocab"])

        def forward(self, input_ids, attention_mask, mlm_ids=None, mlm_positions=None):
            cls = self.encoder(input_ids=input_ids,
                               attention_mask=attention_mask).last_hidden_state[:, 0, :]
            embedded = self.ln1(self.activation(self.fc_input(cls)))
            outputs = (self.out_sent(embedded), self.out_clas(embedded))
            if mlm_ids is None:
                return outputs
            states = self.encoder(input_ids=mlm_ids, attention_mask=attention_mask).last_hidden_state
            picked = states[mlm_positions]
            return outputs + (self.mlm_out(self.ln2(self.activation(self.fc_input2(picked)))),)

    return Linear2Head(), info


def author_mlm_rows(rows, mask_token_id, random_ids):
    """DataCollatorHandMade.random_label for a list of token-id rows (unpadded, special tokens
    included, as the authors count them through attention_mask). Per row: int(0.3 * length) draws of
    a position with replacement are set to <mask>; every <mask> position gets the original token as
    label; then, per draw in order, 10% put the original token back and 10% put a random ID. Returns
    masked rows, label rows (-100 = no label) and the number of draws (the authors' total_mask)."""
    import torch
    masked, labels, draws = [], [], 0
    for row in rows:
        original = torch.from_numpy(row)
        length = len(row)
        count = int(length * MLM["mask_prob"])
        draws += count
        positions = torch.randint(0, length, size=(count,), dtype=torch.int32).long()
        out = original.clone()
        out[positions] = mask_token_id
        label = original.clone()
        label[out != mask_token_id] = -100
        lucky = torch.randint(1, 11, size=(count,), dtype=torch.int32)
        for i, value in enumerate(lucky.tolist()):
            if value % 8 == 0:
                out[positions[i]] = original[positions[i]]
            elif value % 7 == 0:
                out[positions[i]] = torch.randint(0, random_ids, size=(1,))[0]
        masked.append(out.numpy())
        labels.append(label.numpy())
    return masked, labels, draws


def sym_kl_sum(perturbed, clean):
    """utils/loss_function.py sym_kl_loss(input=perturbed, target=clean, reduction='sum')."""
    import torch.nn.functional as F
    perturbed, clean = perturbed.float(), clean.float()
    return (F.kl_div(F.log_softmax(perturbed, dim=-1), F.softmax(clean.detach(), dim=-1),
                     reduction="sum")
            + F.kl_div(F.log_softmax(clean, dim=-1), F.softmax(perturbed.detach(), dim=-1),
                       reduction="sum"))


def author_smart_ids(input_ids):
    """Perturbed IDs exactly as the authors' SMARTLoss produces them for num_steps=1.

    The noise is added to integer token IDs and cast back with `.long()`, so its gradient is
    None and the ascent step reduces to `noise / (inf_norm(noise) + eps)`. Values in (-1, 0)
    truncate to id - 1, which shifts about half of the tokens to the previous vocabulary ID.
    """
    import torch
    noise = torch.randn(input_ids.shape, device=input_ids.device) * SMART["noise_var"]
    noise = noise / (noise.abs().amax(dim=-1, keepdim=True) + SMART["norm_eps"])
    return (input_ids + noise).long()


# ---------------------------------------------------------------- metrics

def task_metrics(y_true, logits):
    from sklearn.metrics import accuracy_score, confusion_matrix, f1_score
    y_pred = logits.argmax(axis=-1)
    labels = list(range(logits.shape[-1]))
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, average="macro")),
        "weighted_f1": float(f1_score(y_true, y_pred, average="weighted")),
        # Trainer/head_trainer.py calls f1_score(pred, true): weighted F1 then uses predicted
        # supports. Accuracy and macro-F1 are symmetric, so only this one differs.
        "weighted_f1_author_mtl": float(f1_score(y_pred, y_true, average="weighted")),
        "per_class_f1": [float(x) for x in f1_score(y_true, y_pred, average=None, labels=labels,
                                                    zero_division=0)],
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=labels).tolist(),
    }


def predict(model, sequences, pad_id, device, batch_size, use_amp):
    import torch
    order = sorted(range(len(sequences)), key=lambda i: len(sequences[i]))
    outputs = None
    was_training = model.training
    model.eval()
    with torch.no_grad():
        for start in range(0, len(order), batch_size):
            chunk = order[start:start + batch_size]
            ids, mask = collate(sequences, chunk, pad_id)
            with torch.autocast(device.type, dtype=torch.float16, enabled=use_amp):
                logits = model(ids.to(device), mask.to(device))
            if outputs is None:
                outputs = [np.zeros((len(sequences), head.shape[-1]), dtype=np.float32) for head in logits]
            for out, value in zip(outputs, logits):
                out[chunk] = value.float().cpu().numpy()
    model.train(was_training)
    return outputs


# ---------------------------------------------------------------- training

def seed_everything(seed):
    import torch
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def environment(device):
    import torch
    import transformers
    import sklearn
    env = {"python": sys.version.split()[0], "platform": platform.platform(),
           "torch": torch.__version__, "transformers": transformers.__version__,
           "sklearn": sklearn.__version__, "cuda": torch.version.cuda, "device": device.type,
           "gpu": torch.cuda.get_device_name(device) if device.type == "cuda" else None,
           "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES")}
    try:
        import sentencepiece
        env["sentencepiece"] = sentencepiece.__version__
    except ImportError:
        env["sentencepiece"] = None
    return env


def write_json(path, payload):
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def train(args):
    import torch
    import torch.nn.functional as F
    from transformers import AutoTokenizer

    backbone = BACKBONES[args.backbone]
    setup = dict(SETUPS[args.setup])
    if args.epochs is not None:
        setup["epochs"] = args.epochs
    micro_batch = args.micro_batch or setup["micro_batch"]
    if COMMON["batch_size"] % micro_batch:
        raise ValueError("--micro-batch must divide 128")
    tasks = setup["tasks"]
    debug = bool(args.max_steps_per_epoch or args.limit_eval or args.epochs is not None
                 or args.model_path or args.fp32)

    if (args.fold is None) != (args.num_folds is None) or (args.fold is not None
                                                             and not 0 <= args.fold < args.num_folds):
        raise ValueError("--fold and --num-folds go together, with 0 <= fold < num_folds")
    if setup.get("ens_kd") and not args.ens_targets:
        raise ValueError(f"{args.setup} needs --ens-targets (see the ensemble-targets command)")
    if args.export_model_root:
        if (args.backbone != "visobert" or args.setup != "mtl_ed" or args.fold is not None or debug):
            raise ValueError("export requires a full pinned raw ViSoBERT MTL-ED student run")
        validation = Path(args.ens_targets).with_suffix(".validation.json")
        checked = json.loads(validation.read_text(encoding="utf-8"))
        if (not checked.get("validated") or checked.get("targets_sha256") != sha256_file(args.ens_targets)
                or checked.get("dataset") != DATASET):
            raise ValueError("validate OOF targets with scripts/model_oof.py before deployment training")
    run_name = f"{args.backbone}-{args.setup}-s{args.seed}"
    if DATASET != "neu":
        run_name = f"{DATASET}-{run_name}"
    if args.fold is not None:
        run_name += f"-f{args.fold}of{args.num_folds}"
    run_dir = Path(args.out_dir) / run_name
    metrics_path = run_dir / "metrics.json"
    if metrics_path.exists() and not args.force:
        status = json.loads(metrics_path.read_text(encoding="utf-8")).get("status")
        if status == "COMPLETED":
            log(f"{run_name} already COMPLETED, skipping (use --force to rerun)")
            return 0
    run_dir.mkdir(parents=True, exist_ok=True)
    for stale in ("epochs.jsonl", "metrics.json", "logits.npz", "predictions.csv", "oof.npz"):
        (run_dir / stale).unlink(missing_ok=True)
    code = code_provenance()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    use_amp = device.type == "cuda" and not args.fp32
    seed_everything(args.seed)

    # ---- data
    processed = backbone["processed"]
    data = {split: load_split(args.data_dir, split, processed) for split in ("train", "val", "test")}
    token_source = args.model_path or backbone["model_id"]
    token_kwargs = {} if args.model_path else {"revision": backbone["revision"]}
    tokenizer = AutoTokenizer.from_pretrained(token_source, use_fast=False, **token_kwargs)
    pad_id = tokenizer.pad_token_id
    started = time.perf_counter()
    sequences = {split: encode_texts(tokenizer, data[split][0], COMMON["max_length"]) for split in data}
    tokenize_seconds = time.perf_counter() - started
    labels = {split: data[split][1] for split in data}
    eval_index = {}
    for split in ("val", "test"):
        keep = list(range(len(sequences[split])))
        if args.limit_eval:
            keep = keep[:args.limit_eval]
        eval_index[split] = keep
    eval_ids = {split: sample_ids(split, len(sequences[split]))[eval_index[split]] for split in eval_index}
    held_out = (fold_rows(len(sequences["train"]), args.fold, args.num_folds)
                if args.fold is not None else np.array([], dtype=np.int64))
    train_rows = np.setdiff1d(np.arange(len(sequences["train"])), held_out)
    ens_probs = None
    if setup.get("ens_kd"):
        targets_file = np.load(args.ens_targets)
        # Keyed by the raw train CSV; PhoBERT's _processed.csv is row-aligned with it.
        if str(targets_file["train_csv_sha256"]) != DATA_FILES["train_set.csv"]:
            raise ValueError(f"{args.ens_targets} was built from another train CSV")
        ens_probs = {task: torch.tensor(targets_file[task], dtype=torch.float32) for task in tasks}
    lengths = np.array([len(s) for s in sequences["train"]])
    log(f"{run_name}: tokenized in {tokenize_seconds:.0f}s, train tokens mean {lengths.mean():.1f}, "
        f"truncated {(lengths >= COMMON['max_length']).mean():.1%}")

    # ---- model and optimizer (AdamW defaults otherwise: betas 0.9/0.999, weight_decay 0.01)
    model, loading_info = build_model(backbone, setup, args.model_path)
    # The authors draw random replacement IDs in [0, 64000), sized for PhoBERT's 64001-token vocab.
    # ViSoBERT's vocab is smaller, so those IDs would index past its embedding table; they are drawn
    # within the encoder's own vocab instead (a recorded deviation; PhoBERT is unchanged).
    mlm_random_ids = (min(MLM["random_ids"], model.encoder.get_input_embeddings().num_embeddings)
                      if setup.get("mlm") else None)
    model.to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=COMMON["lr"], eps=setup["adam_eps"],
                                  weight_decay=COMMON["weight_decay"])
    scheduler = torch.optim.lr_scheduler.LinearLR(optimizer, start_factor=1.0,
                                                  end_factor=setup["lr_end"],
                                                  total_iters=setup["epochs"])
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)

    config = {
        "run_name": run_name, "dataset": DATASET, "backbone": args.backbone, "setup": args.setup, "seed": args.seed,
        "code": code, "model_id": backbone["model_id"], "revision": None if args.model_path else backbone["revision"],
        "model_path_override": args.model_path, "text_source": ("author " if DATASET == "neu" else f"{DATASET} ")
        + ("_processed.csv" if processed else "raw .csv"), "data_files": {data[s][2]: DATA_FILES[data[s][2]] for s in data},
        "tasks": list(tasks), "epochs": setup["epochs"], "adam_eps": setup["adam_eps"],
        "lr_end_factor": setup["lr_end"], "early_stopping_patience": setup["patience"],
        "smart": SMART if setup["smart"] else None, **COMMON, "micro_batch": micro_batch,
        "mlm": {**MLM, "random_ids_used": mlm_random_ids, "loss": "L_s + L_t + L_MLM / avg_mask",
                "mask_token_id": tokenizer.mask_token_id} if setup.get("mlm") else None,
        "precision": "fp16_autocast" if use_amp else "fp32",
        "selection": "val macro-F1" if len(tasks) == 1 else "mean val macro-F1 over both tasks",
        "max_steps_per_epoch": args.max_steps_per_epoch, "limit_eval": args.limit_eval,
        "benchmark_eligible": not debug, "environment": environment(device),
        "loading_info": {k: [str(x) for x in v] for k, v in loading_info.items()},
        "tokenize_seconds": tokenize_seconds,
        "ensemble_teacher": {"targets": args.ens_targets, "gamma": ED["gamma"],
                             "sources": [str(x) for x in targets_file["sources"]]} if ens_probs else None,
        "fold": {"fold": args.fold, "num_folds": args.num_folds, "fold_seed": FOLD_SEED,
                 "held_out_rows": int(len(held_out))} if args.fold is not None else None,
    }
    write_json(run_dir / "config.json", config)

    if ens_probs is not None:
        ens_log = {task: probs.clamp_min(1e-8).log().to(device) for task, probs in ens_probs.items()}

    # ---- loop
    task_columns = {task: torch.from_numpy(labels["train"][task]) for task in tasks}
    n_train = len(train_rows)
    generator = torch.Generator().manual_seed(args.seed)
    best = {"score": -math.inf, "epoch": None, "state": None, "val_logits": None}
    val_history = {task: [] for task in tasks}
    test_history = {task: [] for task in tasks}
    epochs_without_gain = 0
    step_times = []
    status = "COMPLETED"

    def evaluate(split):
        keep = eval_index[split]
        logits = predict(model, [sequences[split][i] for i in keep], pad_id, device,
                         COMMON["eval_batch_size"], use_amp)
        result = {task: task_metrics(labels[split][task][keep], logits[k])
                  for k, task in enumerate(tasks)}
        return logits, result

    model.train()
    for epoch in range(1, setup["epochs"] + 1):
        if device.type == "cuda":
            torch.cuda.reset_peak_memory_stats(device)
        epoch_start = time.perf_counter()
        order = train_rows[torch.randperm(n_train, generator=generator).numpy()].tolist()
        batches = [order[i:i + COMMON["batch_size"]] for i in range(0, n_train, COMMON["batch_size"])]
        if args.max_steps_per_epoch:
            batches = batches[:args.max_steps_per_epoch]
        loss_sum = 0.0
        for step, batch in enumerate(batches, start=1):
            step_start = time.perf_counter()
            optimizer.zero_grad(set_to_none=True)
            batch_loss = 0.0
            if setup.get("mlm"):
                # Masked once per 128-row batch: L_MLM is a mean over the batch's labelled positions
                # and avg_mask = draws / 128, as in the authors' unsplit batch.
                mlm_rows, mlm_labels, draws = author_mlm_rows([sequences["train"][i] for i in batch],
                                                              tokenizer.mask_token_id, mlm_random_ids)
                labelled = sum(int((label != -100).sum()) for label in mlm_labels)
                avg_mask = draws / len(batch)
            for m in range(0, len(batch), micro_batch):
                chunk = batch[m:m + micro_batch]
                share = len(chunk) / len(batch)
                ids, mask = collate(sequences["train"], chunk, pad_id)
                ids, mask = ids.to(device), mask.to(device)
                targets = [task_columns[task][chunk].to(device) for task in tasks]
                if setup.get("mlm"):
                    local = list(range(m, m + len(chunk)))
                    mlm_ids, _ = collate(mlm_rows, local, pad_id)
                    mlm_target, _ = collate(mlm_labels, local, -100)
                    mlm_ids, mlm_target = mlm_ids.to(device), mlm_target.to(device)
                with torch.autocast(device.type, dtype=torch.float16, enabled=use_amp):
                    outputs = (model(ids, mask, mlm_ids, mlm_target != -100) if setup.get("mlm")
                               else model(ids, mask))
                    if setup.get("mlm"):
                        # mlm_3head_trainer.py: L_s + L_t (+ 0.02 * SMART each) + L_MLM / avg_mask.
                        loss = 0.0
                        for k, task in enumerate(tasks):
                            task_loss = F.cross_entropy(outputs[k].float(), targets[k]) * share
                            if setup["smart"]:
                                perturbed = model(author_smart_ids(ids), mask)[k]
                                task_loss = task_loss + SMART["weight"] * sym_kl_sum(perturbed, outputs[k])
                            loss = loss + task_loss
                        mlm_sum = F.cross_entropy(outputs[2].float(), mlm_target[mlm_target != -100],
                                                  reduction="sum")
                        loss = loss + mlm_sum / labelled / avg_mask
                    elif len(tasks) == 1:
                        # base_trainer.py: CrossEntropyLoss (mean) over the 128-row batch.
                        loss = F.cross_entropy(outputs[0].float(), targets[0]) * share
                    else:
                        # head_trainer.py: loss_i = CE_i + 0.02 * SMART_i, then 0.5/0.5.
                        # CE is a batch mean, so it is scaled by this micro-batch's share;
                        # sym-KL uses reduction='sum', so micro-batch sums add up unscaled.
                        loss = 0.0
                        for k, task in enumerate(tasks):
                            task_loss = F.cross_entropy(outputs[k].float(), targets[k]) * share
                            if setup["smart"]:
                                # The authors draw independent noise for each task's call.
                                perturbed = model(author_smart_ids(ids), mask)[k]
                                task_loss = task_loss + SMART["weight"] * sym_kl_sum(perturbed, outputs[k])
                            if ens_probs is not None:
                                # mtl_ed: gamma * KL(ensemble || model), row sums divided by the
                                # 128-row batch, so micro-batches add up to the batch mean.
                                task_loss = task_loss + ED["gamma"] * F.kl_div(
                                    F.log_softmax(outputs[k].float(), dim=-1), ens_log[task][chunk],
                                    log_target=True, reduction="sum") / len(batch)
                            loss = loss + COMMON["mtl_task_weight"] * task_loss
                scaler.scale(loss).backward()
                batch_loss += float(loss.detach())
            scaler.step(optimizer)
            scaler.update()
            loss_sum += batch_loss
            if device.type == "cuda":
                torch.cuda.synchronize(device)
            step_times.append(time.perf_counter() - step_start)
            if step % 50 == 0:
                log(f"{run_name} epoch {epoch} step {step}/{len(batches)} loss {batch_loss:.4f}")
        train_seconds = time.perf_counter() - epoch_start
        scheduler.step()  # base_trainer / head_trainer step LinearLR once per epoch

        eval_start = time.perf_counter()
        val_logits, val_metrics = evaluate("val")
        val_seconds = time.perf_counter() - eval_start
        for k, task in enumerate(tasks):
            val_history[task].append(val_logits[k])
        score = float(np.mean([val_metrics[t]["macro_f1"] for t in tasks]))
        record = {"epoch": epoch, "train_loss": loss_sum / len(batches), "steps": len(batches),
                  "lr_next": optimizer.param_groups[0]["lr"], "train_seconds": train_seconds,
                  "val_seconds": val_seconds, "selection_score": score,
                  "val": {t: {k: v for k, v in val_metrics[t].items() if k != "confusion_matrix"}
                          for t in tasks},
                  "peak_vram_gb": torch.cuda.max_memory_allocated(device) / 2**30
                  if device.type == "cuda" else None}
        if args.test_every_epoch:
            test_logits, test_metrics = evaluate("test")
            for k, task in enumerate(tasks):
                test_history[task].append(test_logits[k])
            record["test"] = {t: {k: v for k, v in test_metrics[t].items() if k != "confusion_matrix"}
                              for t in tasks}
        with open(run_dir / "epochs.jsonl", "a", encoding="utf-8") as stream:
            stream.write(json.dumps(record) + "\n")
        summary = " ".join(f"{t}: acc {val_metrics[t]['accuracy']:.4f} mF1 {val_metrics[t]['macro_f1']:.4f}"
                           for t in tasks)
        log(f"{run_name} epoch {epoch}/{setup['epochs']} train {train_seconds:.0f}s "
            f"val {val_seconds:.0f}s | {summary}")

        # base_trainer.py keeps a checkpoint only when the metric strictly improves.
        if score > best["score"]:
            best.update(score=score, epoch=epoch, val_logits=val_logits,
                        state={k: v.detach().to("cpu", copy=True) for k, v in model.state_dict().items()})
            epochs_without_gain = 0
        else:
            epochs_without_gain += 1
            if setup["patience"] and epochs_without_gain >= setup["patience"]:
                log(f"{run_name}: early stop after epoch {epoch} (patience {setup['patience']})")
                break

    # ---- test with the selected weights
    model.load_state_dict(best["state"])
    if args.export_model_root:
        # Training may be invoked by file path; make the root package importable explicitly.
        root = str(Path(__file__).resolve().parents[1])
        if root not in sys.path:
            sys.path.insert(0, root)
        from services.inference.export import export_selected
        probes = [data["val"][0][i] for i in (7, 0, 3, 1, 12, 2, 20, 4, 30)]
        probes.append("kiểm tra " * 200)  # Exercise real tokenizer truncation as well as padding.
        exported = export_selected(model, tokenizer, config, best, args.export_model_root,
                                   probes, args.ens_targets)
        log(f"published verified student artifact: {exported}")
    test_start = time.perf_counter()
    test_logits, test_metrics = evaluate("test")
    test_seconds = time.perf_counter() - test_start
    val_metrics = {t: task_metrics(labels["val"][t][eval_index["val"]], best["val_logits"][k])
                   for k, t in enumerate(tasks)}

    arrays = {"val_ids": eval_ids["val"], "test_ids": eval_ids["test"]}
    for k, task in enumerate(tasks):
        arrays[f"val_{task}"] = best["val_logits"][k]
        arrays[f"test_{task}"] = test_logits[k]
        arrays[f"val_labels_{task}"] = labels["val"][task][eval_index["val"]]
        arrays[f"test_labels_{task}"] = labels["test"][task][eval_index["test"]]
        arrays[f"val_by_epoch_{task}"] = np.stack(val_history[task])
        if test_history[task]:
            arrays[f"test_by_epoch_{task}"] = np.stack(test_history[task])
    np.savez_compressed(run_dir / "logits.npz", **arrays)
    if args.save_model:
        # Runs after test, so it uses no RNG and leaves every other output of the run unchanged.
        model_dir = run_dir / "model"
        model_dir.mkdir(exist_ok=True)
        torch.save(best["state"], model_dir / "model.pt")
        tokenizer.save_pretrained(model_dir / "tokenizer")
        write_json(model_dir / "model_info.json", {
            "run_name": run_name, "backbone": args.backbone, "setup": args.setup, "seed": args.seed,
            "model_id": backbone["model_id"], "revision": backbone["revision"],
            "best_epoch": best["epoch"], "max_length": COMMON["max_length"],
            "num_labels": {task: NUM_LABELS[task] for task in tasks}})
    if args.save_train_preds:
        # In-sample teacher for the out-of-fold ablation: predictions on the rows this model trained on,
        # in the same file format, so ensemble-targets reads them unchanged.
        all_rows = np.arange(len(sequences["train"]))
        insample_logits = predict(model, list(sequences["train"]), pad_id, device,
                                  COMMON["eval_batch_size"], use_amp)
        np.savez_compressed(run_dir / "oof.npz", rows=all_rows,
                            train_csv_sha256=DATA_FILES[data["train"][2]],
                            **{f"oof_{task}": insample_logits[k] for k, task in enumerate(tasks)})
    if args.fold is not None:
        oof_logits = predict(model, [sequences["train"][i] for i in held_out], pad_id, device,
                             COMMON["eval_batch_size"], use_amp)
        np.savez_compressed(run_dir / "oof.npz", rows=held_out,
                            train_csv_sha256=DATA_FILES[data["train"][2]],
                            **{f"oof_{task}": oof_logits[k] for k, task in enumerate(tasks)})

    # The selected epoch's predictions keyed by sample ID; logits.npz holds the same rows in the same order.
    with open(run_dir / "predictions.csv", "w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["sample_id", "split"] + [f"{t}_{kind}" for t in tasks for kind in ("true", "pred")])
        for split, logits in (("val", best["val_logits"]), ("test", test_logits)):
            for row, sample_id in enumerate(eval_ids[split]):
                cells = []
                for k, task in enumerate(tasks):
                    cells += [int(labels[split][task][eval_index[split][row]]), int(logits[k][row].argmax())]
                writer.writerow([sample_id, split] + cells)

    times = np.array(step_times[3:] or step_times)
    steps_full_epoch = math.ceil(n_train / COMMON["batch_size"])
    write_json(metrics_path, {
        "status": status, "run_name": run_name, "benchmark_eligible": not debug,
        "runner_sha256": code["runner_sha256"], "best_epoch": best["epoch"], "epochs_run": len(val_history[tasks[0]]),
        "selection_score": best["score"], "val": val_metrics, "test": test_metrics,
        "oof_accuracy": {task: float((oof_logits[k].argmax(-1) == labels["train"][task][held_out]).mean())
                         for k, task in enumerate(tasks)} if args.fold is not None else None,
        "timing": {"step_seconds_mean": float(times.mean()), "step_seconds_median": float(np.median(times)),
                   "steps_timed": int(len(times)),
                   "projected_train_epoch_seconds": float(times.mean() * steps_full_epoch),
                   "test_seconds": test_seconds,
                   "wall_seconds": time.perf_counter() - started},
    })
    log(f"{run_name}: best epoch {best['epoch']} | " + " ".join(
        f"test {t}: acc {test_metrics[t]['accuracy']:.4f} mF1 {test_metrics[t]['macro_f1']:.4f}"
        for t in tasks))
    return 0


def ensemble_targets(args):
    """Average softmax probabilities of out-of-fold predictions per training row (any mix of
    backbones and seeds). PhoBERT reads train_set_processed.csv and ViSoBERT train_set.csv; the two are
    row-aligned, so rows match across them and the targets are keyed by the raw CSV's SHA-256."""
    train_csvs = {DATA_FILES["train_set.csv"], DATA_FILES["train_set_processed.csv"]}
    sums, counts, sources = {}, np.zeros(SPLIT_SIZES["train"], dtype=np.int64), []
    for run_dir in args.runs:
        path = Path(run_dir) / "oof.npz"
        if not path.exists():
            raise FileNotFoundError(f"{path}: not a finished --fold run")
        oof = np.load(path)
        if str(oof["train_csv_sha256"]) not in train_csvs:
            raise ValueError(f"{path}: built from an unknown train CSV")
        rows = oof["rows"]
        for task in TASKS:
            logits = oof[f"oof_{task}"].astype(np.float64)
            probs = np.exp(logits - logits.max(axis=1, keepdims=True))
            probs /= probs.sum(axis=1, keepdims=True)
            sums.setdefault(task, np.zeros((SPLIT_SIZES["train"], NUM_LABELS[task])))[rows] += probs
        counts[rows] += 1
        sources.append(str(Path(run_dir).name))
    if counts.min() == 0:
        raise ValueError(f"{int((counts == 0).sum())} training rows have no "
                         "out-of-fold prediction; pass every fold of at least one fold set")
    out = {task: (sums[task] / counts[:, None]).astype(np.float32) for task in TASKS}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.out, train_csv_sha256=DATA_FILES["train_set.csv"], sources=np.array(sources),
                        counts=counts, **out)
    log(f"wrote {args.out}: {len(sources)} runs, {counts.min()}-{counts.max()} predictions per row")
    return 0


def prefetch(args):
    from transformers import AutoModel, AutoTokenizer
    for name in args.backbones:
        backbone = BACKBONES[name]
        AutoTokenizer.from_pretrained(backbone["model_id"], revision=backbone["revision"], use_fast=False)
        AutoModel.from_pretrained(backbone["model_id"], revision=backbone["revision"])
        log(f"cached {backbone['model_id']}@{backbone['revision'][:8]}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_fetch = sub.add_parser("fetch", help="download and verify the authors' CSV splits")
    p_fetch.add_argument("--data-dir", required=True)
    p_fetch.add_argument("--dataset", default="neu", choices=list(DATASETS))

    p_prefetch = sub.add_parser("prefetch", help="cache pinned models/tokenizers")
    p_prefetch.add_argument("--backbones", nargs="+", default=list(BACKBONES), choices=list(BACKBONES))

    p_ens = sub.add_parser("ensemble-targets", help="average out-of-fold train predictions for mtl_ed")
    p_ens.add_argument("runs", nargs="+", help="run directories of finished --fold runs")
    p_ens.add_argument("--out", required=True, help="output .npz")
    p_ens.add_argument("--dataset", default="neu", choices=list(DATASETS))

    p_train = sub.add_parser("train", help="run one backbone/setup/seed")
    p_train.add_argument("--backbone", required=True, choices=list(BACKBONES))
    p_train.add_argument("--setup", required=True, choices=list(SETUPS))
    p_train.add_argument("--seed", required=True, type=int)
    p_train.add_argument("--data-dir", required=True)
    p_train.add_argument("--out-dir", required=True)
    p_train.add_argument("--dataset", default="neu", choices=list(DATASETS),
                         help="neu = NEU-ESC (default), vsfc = UIT-VSFC; non-default runs are named <dataset>-...")
    p_train.add_argument("--micro-batch", type=int, help="default 64, or 32 for mtl_smart")
    p_train.add_argument("--test-every-epoch", action="store_true",
                         help="also save test logits each epoch (post-hoc analysis only; never select on test)")
    p_train.add_argument("--force", action="store_true", help="rerun even if metrics.json is COMPLETED")
    p_train.add_argument("--fold", type=int, help="hold out this fold of the training set and save "
                         "its out-of-fold predictions (oof.npz)")
    p_train.add_argument("--num-folds", type=int)
    p_train.add_argument("--ens-targets", help="ensemble-targets output, required by mtl_ed")
    p_train.add_argument("--export-model-root", help="publish verified selected ViSoBERT ED student under this model root")
    p_train.add_argument("--save-model", action="store_true",
                         help="save the selected weights and tokenizer to <run>/model (for inference/demo)")
    p_train.add_argument("--save-train-preds", action="store_true",
                         help="save predictions on the training rows to oof.npz (in-sample teacher ablation)")
    debug = p_train.add_argument_group("smoke/debug (marks the run benchmark_eligible=false)")
    debug.add_argument("--epochs", type=int)
    debug.add_argument("--max-steps-per-epoch", type=int)
    debug.add_argument("--limit-eval", type=int)
    debug.add_argument("--model-path", help="local model+tokenizer dir instead of the pinned HF revision")
    debug.add_argument("--fp32", action="store_true")

    args = parser.parse_args(argv)
    use_dataset(getattr(args, "dataset", "neu"))
    if args.command == "fetch":
        fetch_data(args.data_dir)
        return 0
    if args.command == "prefetch":
        return prefetch(args)
    if args.command == "ensemble-targets":
        return ensemble_targets(args)
    return train(args)


if __name__ == "__main__":
    raise SystemExit(main())
