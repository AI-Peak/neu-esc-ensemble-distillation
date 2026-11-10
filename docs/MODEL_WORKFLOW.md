# Offline model workflow

Updated 2026-11-10 on branch `webapp`. A local fine-tuned **PhoBERT MTL-ED** checkpoint (`demo/model.pt`, `phobert-mtl_ed-s42`, seed 42, best epoch 10, `vinai/phobert-base-v2@86cd7fd4c148980922ac11a2cf5e257f2ba639e1`) is available locally (gitignored) and imported into `runtime/models/neu` (`neu-phobert-mtl-ed-s42`, manifest `format_version: 2`). Profile `uit` has no fine-tuned checkpoint yet and remains `unavailable` (manual import, review, and CSV export still work).

The app never trains or downloads models in a request. Production has no fake predictor, random model fallback, or fixture environment switch. Unit tests use small synthetic models solely to verify export/import/loading mechanics in temporary directories; real-checkpoint acceptance tests are separated under `@pytest.mark.real_model`.

## Runtime and interface

Use Python 3.10 or 3.11 and install `requirements-model.txt` (or the pinned Windows lockfile `requirements-model.lock.txt`). The reproducible dependency target includes PyTorch 2.14.1, Transformers 4.44.2, NumPy 2.2.6, safetensors 0.8.0, SentencePiece 0.2.1, and `underthesea==9.5.0`:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-model.lock.txt --extra-index-url https://download.pytorch.org/whl/cpu
```

`services.inference.registry.ModelRegistry(model_root: Path)` exposes `status(profile)` and `predict(profile, items)`. It reads canonical labels from `services/profiles.json`:
- `neu` (`neu-v1`): 4 sentiment labels (`Neutral`, `Positive`, `Negative`, `Toxic`) and 10 topic labels.
- `uit` (`uit-v1`): 3 sentiment labels and 4 topic labels (runner dataset name `vsfc`).

`status(profile)` performs lightweight metadata, file-inventory SHA-256, dependency spec, and preprocessing resource checks **without importing `torch` or `underthesea`**. First `predict()` lazily loads at most one encoder/tokenizer/preprocessor on CPU with `local_files_only=True` and `trust_remote_code=False`, verifying every encoder and classification head tensor key, shape, and finiteness.

## Supported artifact formats

1. **Format 1 (`format_version: 1` — ViSoBERT raw)**:
   - Backbone: `uitnlp/visobert@196a62afad9cbe4f52a54aabad828b13f0eec59a` (`xlm-roberta`, `vocab_size - len(tokenizer) in (0, 2)`).
   - Preprocessing: `{"kind": "raw", "use_fast": false, "max_length": 128}`.
   - Provenance: requires audited 30-teacher OOF validation (`oof_validation.json` with `validated: true`, `source_count: 30`, `predictions_per_row: 6`).
2. **Format 2 (`format_version: 2` — Imported PhoBERT MTL-ED)**:
   - Backbone: `vinai/phobert-base-v2@86cd7fd4c148980922ac11a2cf5e257f2ba639e1` (`roberta`, exact `len(tokenizer) == config.vocab_size == 64001`).
   - Preprocessing (`services/inference/preprocessing.py`): `underthesea==9.5.0` (`word_tokenize(text, format="text")`, `use_fast=False`, `max_length=128`), pinned by SHA-256 of `ws_crf_vlsp2013_20230727/{dictionary.bin,features.bin,models.bin}`. Marked `equivalence: "approximate"` because the authors' original NEU segmentation pipeline was not published; raw user text is preserved unchanged in SQLite and CSV exports.
   - Provenance: records `original_checkpoint_sha256`, historical `runner_sha256`, `importer_sha256`, split hashes, and honest OOF status (`status: "reported"`, `audited: false` — never fabricated `validated: true` when the 30 teacher checkpoints/archive are absent).

## Importing and inspecting PhoBERT checkpoints

On a clean machine with an empty Hugging Face cache, prepare the pinned `vinai/phobert-base-v2@86cd7fd4c148980922ac11a2cf5e257f2ba639e1` encoder `config.json` once (downloads only `config.json`, never pretrained weights, and verifies tensor/tokenizer compatibility if `--source demo` is present):

```powershell
.\.venv\Scripts\python.exe scripts\model_prepare_phobert.py --out runtime\cache\phobert-base-v2 --source demo
```

Then import `demo/model.pt` into `runtime/models/neu` offline using the prepared encoder config:

```powershell
.\.venv\Scripts\python.exe scripts\model_import_phobert.py --source demo --encoder-config runtime\cache\phobert-base-v2 --model-root runtime\models --profile neu
.\.venv\Scripts\python.exe scripts\model_status.py --model-root runtime\models --profile neu --load
.\.venv\Scripts\python.exe scripts\model_status.py --model-root runtime\models --profile all
```

### Verification modes and supplementary dataset checks

The preparation script, every importer config resolution path (explicit directory/file,
`source/encoder`, and the pinned local HF cache), and format 2 model loading share
`services/inference/phobert_config.py::verify_phobert_config_object`. The importer
validates before constructing a model, creating staging files, or reusing an
existing version. A mismatch raises `ValueError` with the field, expected/actual
values and preparation command; the CLI exits nonzero.

The `phobert-base-v2-inference-v1` contract compares normalized configuration values
against the pinned revision's specification, independently of the candidate hash:

| Fields | Required values |
|---|---|
| Encoder and dimensions | `model_type=roberta`, `vocab_size=64001`, `hidden_size=768`, `num_hidden_layers=12`, `num_attention_heads=12`, `intermediate_size=3072` |
| Embeddings and token IDs | `max_position_embeddings=258`, `type_vocab_size=1`, `position_embedding_type=absolute`, `pad_token_id=1`, `bos_token_id=0`, `eos_token_id=2` |
| Encoder operations | `hidden_act=gelu`, `layer_norm_eps=1e-5`, `hidden_dropout_prob=0.1`, `attention_probs_dropout_prob=0.1` |
| Normalized encoder defaults | `is_decoder=false`, `add_cross_attention=false`, `is_encoder_decoder=false`, `cross_attention_hidden_size=null`, `tie_encoder_decoder=false`, `use_cache=true` |
| Construction and output defaults | `pruned_heads={}`, `chunk_size_feed_forward=0`, `return_dict=true`, `torchscript=false`, `output_attentions=false`, `output_hidden_states=false` |
| Attention implementation | Normalized `_attn_implementation=eager` (absent and explicit eager are equivalent) |

These include operations that tensor shape checks cannot identify, especially
head splitting, activation, normalization, and bidirectional versus causal masks.
Implicit defaults were checked against the installed supported Transformers
4.44.2 `RobertaConfig`, `PretrainedConfig`, `RobertaModel` and construction code.
That version's `RobertaModel` does not support SDPA/Flash; overrides are rejected.
`use_cache=true` is the pinned serialized setting, but the non-decoder forward
disables KV caching. Import and format 2 reload explicitly use CPU FP32, `eval()`
and `torch.inference_mode()` for inference. The serialized `torch_dtype` does not
override that execution mode. Initialization-only fields (`initializer_range`),
unused MLM/classifier settings, and descriptive fields (`architectures`,
`_name_or_path`, version strings) do not define this encoder's loaded forward.

Whitespace/order and supported `save_pretrained` variants are accepted; byte
identity is recorded for provenance rather than used as the semantic trust anchor.
An adjacent provenance file remains optional; when present, model ID, revision and
config checksum must match. A wrong config with a newly computed matching checksum
still fails the contract. Full serialized config, source/saved hashes, contract ID,
validator source hash and execution settings are retained in version provenance;
the validator hash also participates in pipeline identity.

Small synthetic encoders are restricted to test fixtures that substitute a
generic mechanics validator. Production has no tiny-model exception or bypass.
Separate tests exercise the actual contract on every resolution path, including
an empty isolated HF cache, and opt-in `real_model` tests verify the real checkpoint
offline and browser/API/worker persistence.

- **Default import (no `--data-dir`)**: runs strict checkpoint tensor/key/finiteness checks, tokenizer roundtrip, reload batch/order parity, and offline socket-blocked `underthesea` smoke tests. Records `dataset_verification.status = "not_requested"` (never claims historical or raw comparison was executed).
- **Dataset-verified import (`--data-dir data\cache\neu`)**: requires all pinned processed splits (`train_set_processed.csv`, `val_set_processed.csv`, `test_set_processed.csv`), `val_set.csv`, and `demo\run\logits.npz` to exist and pass SHA-256, row/ID/label alignment, CPU FP32 vs historical FP16 parity, and raw-adapter comparison checks. Any missing file, hash mismatch, or alignment error aborts the import with a non-zero exit code without publishing or changing `current.json`.
- **Supplementary verification on an already-imported model**: published bundle directories under `runtime/models/neu/versions/<version>/` are immutable. Running `model_import_phobert.py --source demo --encoder-config runtime\cache\phobert-base-v2 --data-dir data\cache\neu --model-root runtime\models --profile neu --report-out runtime\validation\phobert-neu-verification.json` executes the dataset verifier, publishes a new immutable bundle version containing the dataset verification report in `versions/<new-version>/verification.json` and `manifest.json`, and atomically updates `current.json` (or use `--verify-only` to write `--report-out` without modifying `runtime/models`).
- **`--verify-only` and `--stage-only`**: `--verify-only` runs all requested checks in a temporary directory without writing to `runtime/models` or touching `current.json`; `--stage-only` writes and validates `versions/<version>` without updating `current.json`. There is no `--skip-validation` flag. Re-importing an identical source and verification input set is idempotent and preserves existing versions.

Bundle layout under `runtime/models/neu/` (gitignored):

```text
runtime/models/neu/current.json
runtime/models/neu/versions/<version>/
  manifest.json
  model.safetensors
  encoder/config.json
  tokenizer/...
  preprocessing.json
  training_config.json
  source_model_info.json
  source_metrics.json
  parity.json
  verification.json
```

To roll back to a previous version, stop the worker (`.\scripts\stop-local.ps1`), atomically replace `runtime/models/neu/current.json` with `{"version": "<previous-version>"}`, verify with `model_status.py --profile neu --load`, and restart (`.\scripts\start-local.ps1`). When moving the app to another machine, copy both the `runtime/models/neu` bundle and ensure the exact `underthesea==9.5.0` environment is installed.

## CPU benchmarking

Measure cold startup, warm single-item latency, and batches 10/100/500 (including preprocessing and tokenization) with non-sensitive probe lines:

```powershell
.\.venv\Scripts\python.exe scripts\model_benchmark.py --model-root runtime\models --profile neu --text-file probes.txt --out runtime\validation\phobert-neu-benchmark.json
```

## GPU training & OOF audit (when training new artifacts)

GPU training commands (`src_improvement.neu_esc_improvement` + `scripts/model_oof.py`) remain unchanged for CUDA environments when training new ViSoBERT format 1 or PhoBERT students from scratch.
