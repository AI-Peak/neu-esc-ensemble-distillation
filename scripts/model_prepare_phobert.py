"""Prepare and verify the pinned PhoBERT-base-v2 encoder config for offline checkpoint import."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.inference.registry import PHOBERT_REVISION, sha256
from services.inference.phobert_config import (EXPECTED_PHOBERT_CONFIG,
                                              PHOBERT_CONFIG_CONTRACT,
                                              PHOBERT_MODEL_ID,
                                              verify_phobert_config_object)


def prepare_phobert_config(
    out_dir: Path,
    source: Path | None = None,
    local_files_only: bool = False,
    cache_dir: Path | None = None,
) -> dict:
    """Fetch only config.json from the pinned PhoBERT revision, verify compatibility, and save locally."""
    from huggingface_hub import hf_hub_download
    from transformers import AutoConfig, AutoTokenizer

    out_dir = Path(out_dir).resolve()
    download_kwargs = {
        "repo_id": PHOBERT_MODEL_ID,
        "filename": "config.json",
        "revision": PHOBERT_REVISION,
        "local_files_only": local_files_only,
    }
    if cache_dir is not None:
        download_kwargs["cache_dir"] = str(Path(cache_dir).resolve())

    try:
        downloaded_path = Path(hf_hub_download(**download_kwargs))
    except Exception as exc:
        mode = "offline cache" if local_files_only else "Hugging Face Hub"
        raise RuntimeError(
            f"Failed to obtain config.json for {PHOBERT_MODEL_ID}@{PHOBERT_REVISION} from {mode}: {exc}"
        ) from exc

    with tempfile.TemporaryDirectory(prefix="phobert-prepare-") as tmp:
        stage = Path(tmp)
        staged_cfg = stage / "config.json"
        shutil.copyfile(downloaded_path, staged_cfg)
        cfg = AutoConfig.from_pretrained(
            str(stage),
            local_files_only=True,
            trust_remote_code=False,
        )
        verify_phobert_config_object(cfg)
        config_sha = sha256(staged_cfg)

        checkpoint_verified = False
        checkpoint_sha = None
        if source is not None and Path(source).exists():
            source_path = Path(source).resolve()
            model_info_path = source_path / "model_info.json"
            if model_info_path.is_file():
                info = json.loads(model_info_path.read_text(encoding="utf-8"))
                if info.get("model_id") != PHOBERT_MODEL_ID or info.get("revision") != PHOBERT_REVISION:
                    raise ValueError(
                        f"Source model_info.json expects {info.get('model_id')}@{info.get('revision')}, "
                        f"not {PHOBERT_MODEL_ID}@{PHOBERT_REVISION}"
                    )

            tokenizer_dir = source_path / "tokenizer"
            if tokenizer_dir.is_dir():
                tokenizer = AutoTokenizer.from_pretrained(
                    str(tokenizer_dir),
                    use_fast=False,
                    local_files_only=True,
                    trust_remote_code=False,
                )
                if len(tokenizer) != cfg.vocab_size or tokenizer.pad_token_id != cfg.pad_token_id:
                    raise ValueError("Source tokenizer is incompatible with prepared PhoBERT config")

            checkpoint_path = source_path / "model.pt"
            if checkpoint_path.is_file():
                import torch
                from services.inference.architecture import build_model

                checkpoint_sha = sha256(checkpoint_path)
                num_labels = {"sentiment": 4, "topic": 10}
                if model_info_path.is_file():
                    info = json.loads(model_info_path.read_text(encoding="utf-8"))
                    if isinstance(info.get("num_labels"), dict):
                        num_labels = info["num_labels"]
                model = build_model(cfg, num_labels)
                raw_state = torch.load(str(checkpoint_path), map_location="cpu", weights_only=True)
                if not isinstance(raw_state, dict):
                    raise ValueError("Checkpoint did not deserialize to a state dict")
                expected_state = model.state_dict()
                if set(raw_state) != set(expected_state):
                    raise ValueError("Checkpoint tensor keys do not match prepared PhoBERT config")
                for key, expected_tensor in expected_state.items():
                    if raw_state[key].shape != expected_tensor.shape:
                        raise ValueError(f"Checkpoint tensor shape mismatch at {key}")
                checkpoint_verified = True

        provenance = {
            "model_id": PHOBERT_MODEL_ID,
            "revision": PHOBERT_REVISION,
            "source_url": f"https://huggingface.co/{PHOBERT_MODEL_ID}/resolve/{PHOBERT_REVISION}/config.json",
            "config_sha256": config_sha,
            "semantic_contract": PHOBERT_CONFIG_CONTRACT,
            "inference_config": {**EXPECTED_PHOBERT_CONFIG, "_attn_implementation": "eager"},
            "model_type": cfg.model_type,
            "vocab_size": cfg.vocab_size,
            "hidden_size": cfg.hidden_size,
            "num_hidden_layers": cfg.num_hidden_layers,
            "num_attention_heads": cfg.num_attention_heads,
            "intermediate_size": cfg.intermediate_size,
            "max_position_embeddings": cfg.max_position_embeddings,
            "pad_token_id": cfg.pad_token_id,
            "prepared_at": datetime.now(timezone.utc).isoformat(),
            "checkpoint_verified": checkpoint_verified,
            "checkpoint_sha256": checkpoint_sha,
        }
        out_dir.mkdir(parents=True, exist_ok=True)
        tmp_cfg = out_dir / "config.json.tmp"
        tmp_prov = out_dir / "config_provenance.json.tmp"
        shutil.copyfile(staged_cfg, tmp_cfg)
        tmp_prov.write_text(json.dumps(provenance, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp_cfg, out_dir / "config.json")
        os.replace(tmp_prov, out_dir / "config_provenance.json")

    return {
        "status": "prepared",
        "out_dir": str(out_dir),
        "config_path": str(out_dir / "config.json"),
        **provenance,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("runtime/cache/phobert-base-v2"),
        help="Destination directory for verified PhoBERT config.json",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("demo"),
        help="Optional checkpoint directory to verify config compatibility against model.pt and tokenizer/",
    )
    parser.add_argument(
        "--local-files-only",
        action="store_true",
        help="Do not access network; require config.json to exist in local Hugging Face cache",
    )
    args = parser.parse_args()
    try:
        report = prepare_phobert_config(
            out_dir=args.out,
            source=args.source if args.source and args.source.exists() else None,
            local_files_only=args.local_files_only,
        )
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
