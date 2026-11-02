"""Reproducible single-run driver for the Adaptive Interaction cohort.

On Kaggle, invoke this script once per ``(variant, seed)``.  It writes an atomic
config, validation-selected checkpoint, metrics, predictions, and a completion
manifest under a unique run directory.  ``--smoke`` uses a tiny encoder and does
not qualify as a reportable experiment.
"""
from __future__ import annotations
import argparse, json, os, platform, random, time
from pathlib import Path
import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset
try:
    from .adaptive_interaction import AdaptiveInteractionModel, InteractionConfig, count_parameters
except ImportError:  # direct Kaggle invocation: python src_adaptive/run_experiment.py
    from adaptive_interaction import AdaptiveInteractionModel, InteractionConfig, count_parameters

SEEDS = [42, 43, 44, 45, 46]
VARIANTS = ["baseline", "independent", "ungated", "adaptive"]

def seed_all(seed: int):
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    if torch.cuda.is_available(): torch.cuda.manual_seed_all(seed)

class EncodedDataset(Dataset):
    def __init__(self, encodings, sentiment, topic):
        self.encodings, self.sentiment, self.topic = encodings, sentiment, topic
    def __len__(self): return len(self.sentiment)
    def __getitem__(self, i):
        return {"input_ids": self.encodings["input_ids"][i], "attention_mask": self.encodings["attention_mask"][i],
                "sentiment": int(self.sentiment[i]), "topic": int(self.topic[i])}

def collate(rows):
    return {"input_ids": torch.stack([x["input_ids"] for x in rows]),
            "attention_mask": torch.stack([x["attention_mask"] for x in rows]),
            "sentiment": torch.tensor([x["sentiment"] for x in rows], dtype=torch.long),
            "topic": torch.tensor([x["topic"] for x in rows], dtype=torch.long)}

def metrics(y_true, logits):
    from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support
    pred = logits.argmax(-1)
    p, r, f, _ = precision_recall_fscore_support(y_true, pred, labels=list(range(logits.shape[1])), zero_division=0)
    return {"accuracy": float(accuracy_score(y_true, pred)), "macro_f1": float(f1_score(y_true, pred, average="macro")),
            "weighted_f1": float(f1_score(y_true, pred, average="weighted")), "per_class_precision": p.tolist(),
            "per_class_recall": r.tolist(), "per_class_f1": f.tolist(),
            "confusion_matrix": confusion_matrix(y_true, pred, labels=list(range(logits.shape[1]))).tolist()}

def evaluate(model, loader, device):
    model.eval(); sent, topic, ys, yt = [], [], [], []
    with torch.no_grad():
        for batch in loader:
            ids, mask = batch["input_ids"].to(device), batch["attention_mask"].to(device)
            out = model(ids, mask)
            sent.append(out[0].float().cpu().numpy()); topic.append(out[1].float().cpu().numpy())
            ys.append(batch["sentiment"].numpy()); yt.append(batch["topic"].numpy())
    a, b = np.concatenate(sent), np.concatenate(topic)
    return {"sentiment": metrics(np.concatenate(ys), a), "topic": metrics(np.concatenate(yt), b)}

def environment(device):
    return {"python": platform.python_version(), "torch": torch.__version__, "cuda": torch.version.cuda,
            "cuda_available": torch.cuda.is_available(), "device": str(device),
            "gpu": torch.cuda.get_device_name(device) if torch.cuda.is_available() else None,
            "vram_gb": (torch.cuda.get_device_properties(device).total_memory / 2**30) if torch.cuda.is_available() else None}

class TinyEncoder(torch.nn.Module):
    def __init__(self, vocab=128, hidden=32):
        super().__init__(); self.emb = torch.nn.Embedding(vocab, hidden); self.config = type("C", (), {"hidden_size": hidden})()
    def forward(self, input_ids, attention_mask=None):
        return type("O", (), {"last_hidden_state": self.emb(input_ids)})()

def train(args):
    seed_all(args.seed); started = time.perf_counter()
    device = torch.device("cuda" if torch.cuda.is_available() and not args.cpu else "cpu")
    out = Path(args.out_dir) / f"{args.variant}-s{args.seed}"; out.mkdir(parents=True, exist_ok=True)
    (out / "status.json").write_text(json.dumps({"status": "RUNNING"}), encoding="utf-8")
    if args.smoke:
        encoder, seq_len, vocab = TinyEncoder(), 16, 128
        n_train, n_val, n_test = 64, 24, 24
        rng = np.random.default_rng(args.seed)
        splits = [(n_train, rng.integers(0, vocab, (n_train, seq_len))), (n_val, rng.integers(0, vocab, (n_val, seq_len))), (n_test, rng.integers(0, vocab, (n_test, seq_len)))]
        datasets = [EncodedDataset({"input_ids": torch.tensor(x), "attention_mask": torch.ones_like(torch.tensor(x))}, rng.integers(0,4,n), rng.integers(0,10,n)) for n,x in splits]
    else:
        from transformers import AutoModel, AutoTokenizer
        import pandas as pd
        tokenizer = AutoTokenizer.from_pretrained(args.model_id, revision=args.revision or None, use_fast=False)
        encoder = AutoModel.from_pretrained(args.model_id, revision=args.revision or None)
        datasets = []
        for split in ("train", "val", "test"):
            suffix = "_processed" if args.processed else ""
            frame = pd.read_csv(Path(args.data_dir) / f"{split}_set{suffix}.csv")
            tok = tokenizer(frame.text.astype(str).tolist(), truncation=True, max_length=args.max_length, padding="max_length", return_tensors="pt")
            datasets.append(EncodedDataset(tok, frame.sentiment.to_numpy(), frame.classification.to_numpy()))
    cfg = InteractionConfig(hidden_size=encoder.config.hidden_size, projection_size=args.projection_size,
                           dropout=args.dropout, variant=args.variant)
    model = AdaptiveInteractionModel(encoder, cfg).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, eps=5e-9, weight_decay=0.01)
    loaders = [DataLoader(d, batch_size=args.batch_size, shuffle=(i == 0), collate_fn=collate) for i,d in enumerate(datasets)]
    best_score, best_state, best_epoch = -1.0, None, 0
    history = []
    amp = device.type == "cuda" and not args.fp32
    scaler = torch.amp.GradScaler("cuda", enabled=amp)
    for epoch in range(1, args.epochs + 1):
        model.train(); losses = []
        for batch in loaders[0]:
            opt.zero_grad(set_to_none=True)
            with torch.autocast(device.type, dtype=torch.float16, enabled=amp):
                logits = model(batch["input_ids"].to(device), batch["attention_mask"].to(device))
                loss = model.multitask_loss(logits, batch["sentiment"].to(device), batch["topic"].to(device))
            scaler.scale(loss).backward(); scaler.step(opt); scaler.update(); losses.append(float(loss.detach().cpu()))
        val = evaluate(model, loaders[1], device); score = (val["sentiment"]["macro_f1"] + val["topic"]["macro_f1"]) / 2
        history.append({"epoch": epoch, "loss": float(np.mean(losses)), "val": val})
        if score > best_score:
            best_score, best_epoch, best_state = score, epoch, {k: v.detach().cpu().clone() for k,v in model.state_dict().items()}
    model.load_state_dict(best_state); test = evaluate(model, loaders[2], device)
    config = {"status": "COMPLETED", "variant": args.variant, "seed": args.seed, "smoke": args.smoke,
              "selection": "mean validation sentiment/topic macro-F1", "best_epoch": best_epoch,
              "config": vars(args), "environment": environment(device), "parameters": count_parameters(model),
              "wall_seconds": time.perf_counter() - started, "history": history, "test": test}
    torch.save({"state_dict": best_state, "interaction_config": cfg.__dict__, "best_epoch": best_epoch}, out / "checkpoint.pt")
    tmp = out / "metrics.json.tmp"; tmp.write_text(json.dumps(config, indent=2), encoding="utf-8"); os.replace(tmp, out / "metrics.json")
    (out / "status.json").write_text(json.dumps({"status": "COMPLETED", "best_epoch": best_epoch}), encoding="utf-8")
    print(json.dumps({"run": str(out), "status": "COMPLETED", "test": test, "parameters": config["parameters"]}, indent=2))

def main():
    p = argparse.ArgumentParser(); p.add_argument("--variant", choices=VARIANTS, required=True); p.add_argument("--seed", type=int, required=True)
    p.add_argument("--data-dir", default="data/NEU"); p.add_argument("--out-dir", default="runs/adaptive_interaction"); p.add_argument("--processed", action="store_true")
    p.add_argument("--model-id", default="vinai/phobert-base-v2"); p.add_argument("--revision"); p.add_argument("--max-length", type=int, default=128)
    p.add_argument("--projection-size", type=int, default=None); p.add_argument("--dropout", type=float, default=0.2); p.add_argument("--lr", type=float, default=2e-5)
    p.add_argument("--batch-size", type=int, default=32); p.add_argument("--epochs", type=int, default=20); p.add_argument("--cpu", action="store_true"); p.add_argument("--fp32", action="store_true"); p.add_argument("--smoke", action="store_true")
    args = p.parse_args(); train(args)
if __name__ == "__main__": main()
