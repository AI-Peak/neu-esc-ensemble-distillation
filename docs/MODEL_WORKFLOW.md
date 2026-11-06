# Offline model workflow

Checked 2026-11-06. The repository, including ignored files, contains **no fine-tuned weights,
OOF targets, teacher runs or per-run logits** (`.pt`, `.pth`, `.ckpt`, `.bin`, `.safetensors`, `.npz`).
No other artifact location was supplied. The known Hugging Face cache contains backbone resources;
these do not restore the trained ED student. Historical report metrics remain available, but both
live model profiles correctly return unavailable. Real student accuracy, reload parity and CPU
latency have **not** been measured in this checkout.

The app never trains or downloads models in a request. Production has no fake predictor, random
model fallback or fixture environment switch. The tests use small random models solely to verify
export/loading mechanics. Their generated weights stay in pytest temporary directories.

## Runtime and interface

Use Python 3.10 or 3.11 and install `requirements-model.txt`. The reproducible dependency target is
PyTorch 2.14.1, Transformers 4.44.2, NumPy 2.2.6, safetensors 0.8.0 and SentencePiece 0.2.1, with the
remaining dependencies pinned in that file. Select the CPU or CUDA PyTorch wheel for the actual
machine. A fresh isolated Python 3.10 `.venv-modelcheck` installation from public indexes passed
the offline inference suite using these exact pins (torch resolves to 2.14.1+cpu). No model weights
were downloaded. The same suite also passed in the original global environment.
Upgrade pip before installing so old metadata normalization does not reject current wheels:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements-model.txt --extra-index-url https://download.pytorch.org/whl/cpu
```

`services.inference.registry.ModelRegistry(model_root: Path)` exposes `status(profile)` and
`predict(profile, items)`. It reads canonical labels from `services/profiles.json`; `neu` means
4 sentiment/10 topic labels, and `uit` means 3/4. Runner dataset name `vsfc` maps to app profile
`uit`. These checkpoints cannot substitute for one another.

Status is metadata/hash readiness and does not import torch or load weights. First prediction
loads exactly one encoder/tokenizer on CPU, with no network, and checks every encoder/head key
and shape. Proven artifact format/tensor/schema failures are retained in status until the
artifact changes (or an explicit direct prediction reload succeeds). Runtime inference failures
are reported with a sanitized phase/type message and leave artifact availability retryable;
successful load/prediction clears the appropriate failure state. Input text and exception
messages from inference are never retained in registry diagnostics. API and worker normally
run in separate processes with independent registries: API readiness does not assert worker
runtime health. Explicit job retry uses the same pinned model version and can succeed in the
existing worker after a transient inference failure without replacing the bundle. Allocation
and other runtime errors during lazy model load are also retryable; malformed safetensors,
incompatible tensor keys/shapes and output schema defects remain blocked. Switching profiles
evicts the previous encoder. The registry serializes model calls. Hash validation runs once per
directory/file-stat inventory; later calls check size/mtime/member changes and rehash on change.
Treat published bundles as immutable. Status cannot prove statistical quality or the truth of
training provenance, and an unsigned hash inventory is integrity evidence, not a trusted signer.

Input rows contain `item_id`, `revision_id`, and nonblank raw `text`. Output preserves IDs/order,
contains the canonical schema/model/version and two task softmax score vectors, original token
count (including special tokens), truncation flag/warning and amortized call duration in ms.
Softmax scores are not calibrated probabilities. Tokenization is slow ViSoBERT, special tokens,
maximum 128 tokens, dynamic batch padding; the original lengths are measured before truncation.
The only supported deploy architecture is the runner's plain shared encoder, first-token vector,
Linear → SiLU → LayerNorm → two Linear heads. MLM/ST/PhoBERT are deliberately rejected by this
export path. OOF PhoBERT teachers still use their original processed text during GPU training.

The worker must compare each prediction's `model_id`/`model_version` with the run's pinned identity
before committing. A `current.json` replacement during a run must never mix predictions from two
versions. `ModelUnavailable` signals missing, corrupt or incompatible bundles.

```powershell
python scripts/model_status.py --model-root runtime/models
# Exit 2 means at least one profile is unavailable; a single installed profile is valid app usage.
python scripts/model_status.py --model-root runtime/models --load
```

## Recover artifacts first

If teammates recover a full already exported bundle, copy its `neu/` or `uit/` directory under
`runtime/models`, retaining `current.json` and `versions/`. Run `model_status.py --load` before
starting the worker. If only an old logits/report directory is recovered, it is insufficient to
export a model: this runner historically discarded best weights. If old OOF teacher runs and
targets are recovered, validate them with the command below before student training. The strict
workflow requires the original 2 backbones × seeds 42/43/44 × 5 folds = 30 completed teacher runs.

## GPU training when recovery is impossible

These are concrete PowerShell commands for a CUDA machine. They are documented, **not executed**
on this local CPU machine. They require Internet only for the explicit fetch/prefetch stages.
Use a clean training environment with a CUDA PyTorch wheel matching that GPU, then install the
other pinned requirements. A full teacher rebuild is substantial work; no CPU teacher job is
started by setup or app startup.

```powershell
python -m src_improvement.neu_esc_improvement fetch --dataset neu --data-dir data/cache/neu
python -m src_improvement.neu_esc_improvement prefetch --backbones phobert visobert
```

NEU fetch retrieves all six pinned original files, including processed files absent from this
checkout. It writes to a separate prepared directory. Git raw CSVs may have CRLF line endings;
the runner verifies exact original SHA-256, so do not change its expected hashes.

For UIT use the committed files, in a separate prepared directory. The helper accepts either
the exact bytes or CRLF→LF bytes only when the resulting pinned SHA-256 matches every file;
it leaves source files untouched and writes nothing on verification failure.

```powershell
python scripts/model_prepare_data.py --dataset vsfc --source data/UIT-VSFC --out data/cache/vsfc
```

Choose one dataset per pass. The following is NEU; for UIT change `$dataset` to `vsfc` and
`$dataPath` to `data/cache/vsfc`. Keep output roots separate for each dataset.

```powershell
$dataset = 'neu'
$dataPath = 'data/cache/neu'
$teacherRoot = "runs/$dataset-teachers"
$studentRoot = "runs/$dataset-students"
$targetsPath = "artifacts/$dataset-ensemble-targets.npz"
foreach ($backbone in @('phobert', 'visobert')) {
  foreach ($seed in @(42, 43, 44)) {
    foreach ($fold in 0..4) {
      python -m src_improvement.neu_esc_improvement train --dataset $dataset --backbone $backbone --setup mtl --seed $seed --fold $fold --num-folds 5 --data-dir $dataPath --out-dir $teacherRoot
      if ($LASTEXITCODE -ne 0) { throw 'Teacher training failed' }
    }
  }
}
$teacherDirs = @(Get-ChildItem -LiteralPath $teacherRoot -Directory | ForEach-Object { $_.FullName })
python -m src_improvement.neu_esc_improvement ensemble-targets --dataset $dataset --out $targetsPath @teacherDirs
if ($LASTEXITCODE -ne 0) { throw 'Target assembly failed' }
python scripts/model_oof.py --dataset $dataset --targets $targetsPath --runs @teacherDirs
if ($LASTEXITCODE -ne 0) { throw 'OOF validation failed' }
python -m src_improvement.neu_esc_improvement train --dataset $dataset --backbone visobert --setup mtl_ed --seed 42 --data-dir $dataPath --out-dir $studentRoot --ens-targets $targetsPath --export-model-root runtime/models
if ($LASTEXITCODE -ne 0) { throw 'Student training/export failed' }
```

The OOF audit verifies pinned dataset/revisions, all expected seeds/folds, completed full runs,
validation selection criterion, exact held-out rows, file hashes, head shapes, finite logits,
exact six-prediction coverage and target probabilities reconstructed by averaging softmax (not
logits). It writes `<targets>.validation.json`. The target hash and audit hash become student
provenance. Targets alone without the 30 source runs cannot pass this strict audit. The audit
does not rerun model training; it checks consistency of the recovered evidence.

The audit supports float32 targets from `ensemble-targets` and historical float16 archives.
It reconstructs every probability from the six held-out predictions using float64 softmax and
averaging, casts to float32 exactly as target assembly does, then casts to each stored task's
dtype. Stored values must equal that reconstruction exactly. There is no widened epsilon;
float16 row sums may differ from one solely because each reconstructed probability was rounded
to float16. Other dtypes, nonfinite/out-of-range values, changed probabilities and invalid
teacher/fold/hash/row provenance are rejected. Keep all 30 source directories when recovering
historical archives; source names must remain the names recorded in the archive. Reconstruction
uses the archive's recorded source order, independently of the CLI directory argument order.

The audit records `target_dtypes` for each task, `training_target_dtype: float32` and its
reconstruction procedure. Historical research used float16 target files; student training
promotes their already quantized values to `torch.float32`, which does not recover discarded
precision. Newly assembled targets are stored as float32 and loaded as `torch.float32`.
Recovering and auditing a historical float16 archive preserves its original target hash and
precision; it does not silently replace it with newly reconstructed float32 targets.

The fixed deployment seed is 42; no test-score seed selection occurs. Every full student run
selects its best epoch by mean validation macro-F1 across the two tasks. Export rejects debug,
fold, model-path overrides, preprocessing differences and unvalidated OOF targets. If a prior
completed run has no exported weights, it must be rerun with `--force`; its lost RAM state cannot
be recovered from metrics. Do not substitute base-backbone weights.

## Publication, verification and rollback

`--export-model-root` hooks immediately after loading `best_state`. It writes all encoder and
head tensors as safetensors, encoder config, the slow tokenizer, training config, OOF audit,
parity report and a manifest into a staging directory. It reloads with local-only APIs and
strict state keys; compares training vs reloaded token IDs; and compares CPU FP32 logits at
batch sizes 1, 2, 8 plus reversed input order. Ten private probes from validation and a long
synthetic truncation probe exercise uneven lengths. Tolerances are atol=2e-5, rtol=1e-4.
This is CPU reload parity for the selected weights, not a claim of bitwise FP16 GPU parity.
An additional local-only test uses the real cached pinned tokenizer with a tiny random
XLM-RoBERTa encoder. This confirms the backbone's actual `xlm-roberta` config and deliberate
15004 encoder embeddings versus 15002 tokenizer entries survive saving/loading. It is not
fine-tuned model evidence, and skips when those tokenizer resources are absent locally.

Only after successful checks is staging renamed to an immutable version directory and
`current.json` atomically replaced. A failed check leaves the prior pointer untouched. Prior
versions remain available for manual rollback by an atomic pointer replacement while workers
are stopped. No successful artifact is silently overwritten. Layout:

```text
runtime/models/neu/current.json             {"version":"<version>"}
runtime/models/neu/versions/<version>/manifest.json
runtime/models/neu/versions/<version>/model.safetensors
runtime/models/neu/versions/<version>/encoder/config.json
runtime/models/neu/versions/<version>/tokenizer/...
runtime/models/neu/versions/<version>/training_config.json
runtime/models/neu/versions/<version>/oof_validation.json
runtime/models/neu/versions/<version>/parity.json
```

The manifest records architecture, exact ordered canonical label IDs/keys, raw preprocessing,
backbone revision, seed, selected epoch/criterion/score, runner hash/git revision, all three data
hashes, OOF target/audit hashes and teacher coverage, environment and every bundle file hash.
Different schemas, missing/unlisted files, modified hashes and incompatible state keys fail closed.
Manifests are not signed; use artifacts from a trusted training machine.

After a real model is installed, measure cold startup, warm single and batches 10/100/500 with
private example lines (only timing/memory and truncation counts are saved):

```powershell
python scripts/model_benchmark.py --model-root runtime/models --profile neu --text-file private-probes.txt --out runtime/benchmarks/neu.json
python -m pytest tests/inference -q
```

The benchmark runs all requested sizes, records wall time/throughput/RSS and Windows process peak
working set (null on platforms without that counter). Internal inference microbatches are eight.
CPU latency is currently **not measured**, because no deployable model exists here. The synthetic
test suite is not a performance or model-quality benchmark.
