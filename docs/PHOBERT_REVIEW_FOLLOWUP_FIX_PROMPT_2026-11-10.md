# Gemini implementation prompt: remaining PhoBERT review fixes

You are working in `F:\DPL_NEU-ESC` on Windows / PowerShell. Implement the two fixes below, run the relevant verification, and report the results in Vietnamese. This is an execution request, not a request for another plan. If filesystem or terminal access is unavailable, state the limitation instead of claiming completion.

## 1. Scope and working-tree safety

The webapp already integrates a local PhoBERT MTL-ED checkpoint for NEU. Earlier fixes for missing offline config preparation, invalid explicitly requested verification data, and stale reuse of verification results are implemented. Preserve those fixes. This follow-up addresses only:

- F1 / P2: importer accepts an incorrect encoder config that has compatible tensor shapes but changes inference behavior.
- F2 / P3: the real-model acceptance test does not actually verify server-side export persistence after restart.

Start by reading applicable AGENTS.md instructions, `git status --short`, relevant diffs, and the code. The last reviewed branch was `webapp`, HEAD `0068fe6`; inspect current state rather than assuming it is unchanged. Many implementation files are modified or untracked and must be preserved.

Do not reset, clean, overwrite unrelated edits, commit, push, deploy, train, download pretrained weights, or change the paper. Do not redesign the UI. Do not run import against the production model root in an activating mode. Use temporary model roots, runtime databases, config directories, logs, and ports for tests. Stop only processes started by your tests.

Read these files first:

- `scripts/model_import_phobert.py`
- `scripts/model_prepare_phobert.py`
- `services/inference/architecture.py`
- `services/inference/registry.py`
- `tests/inference/test_phobert_import_and_preprocessing.py`
- `services/api/main.py` and `services/storage/db.py` export endpoints/storage
- `docs/MODEL_WORKFLOW.md`, `docs/VALIDATION_REPORT.md`, `pytest.ini`

For architectural context, read `docs/PHOBERT_WEBAPP_HANDOFF_2026-11-10.md`. The older `docs/PHOBERT_REVIEW_FIX_PROMPT_2026-11-10.md` describes previous work; do not treat all its findings as still open. Use this follow-up as the current scope.

## 2. Known artifacts and baseline evidence

- Checkpoint: `demo/model.pt`, 542458551 bytes.
- Checkpoint SHA256: `754892a782dec389b041abc5f923573c091b8e2801dd0f7be57f718ae88700a8`.
- Encoder: `vinai/phobert-base-v2` at revision `86cd7fd4c148980922ac11a2cf5e257f2ba639e1`.
- NEU sentiment/topic heads: 4 / 10 labels; seed 42, epoch 10, max_length 128.
- Prepared config: `runtime/cache/phobert-base-v2/config.json`, with adjacent `config_provenance.json`.
- Previously observed prepared config SHA256: `26d21a304fdea8fada88e7c6b7c7fef15c902c690bfb0fa47f60bdb61c68307a`. Verify provenance before using this as a trusted reference; a local observation alone is not an independent trust anchor.
- Last observed production bundle: `runtime/models/neu/versions/neu-phobert-mtl-ed-s42-e10-617f852a3fff`.
- Read and snapshot `runtime/models/neu/current.json` before work. Preserve the actual current pointer and its referenced bundle, even if different from the path above.

The previous reviewer ran:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest tests/inference tests/test_research.py -q
# 62 passed, 1 deselected
.\.venv\Scripts\python.exe -X utf8 -m pytest -m real_model -q
# 1 passed, 116 deselected
git diff --check
# passed, apart from line-ending warnings
```

These are baseline results, not results for your changes. The reviewer did not rerun the entire default suite in that review; the earlier implementer reported 116 passed, 1 deselected. Do not conflate those sources.

## 3. F1: validate the pinned encoder semantics before accepting a checkpoint

### Confirmed defect

`_load_local_config_dir` checks provenance only when the adjacent file exists. `_resolve_encoder_config` checks little more than `model_type == 'roberta'` and sufficient position capacity. The preparation script has a stronger `verify_phobert_config_object`, but the importer does not use it, and its field list is still incomplete.

The reviewer copied the valid prepared config to a temporary directory, changed only `num_attention_heads` from 12 to 6, omitted provenance, and invoked the real importer with `demo/model.pt` and `verify_only=True`. It returned:

```json
{
  "modified_heads": 6,
  "status": "verified_only",
  "verification_passed": true,
  "inference_ready": true,
  "parity_passed": true,
  "dataset_status": "not_requested"
}
```

This is a real-checkpoint reproduction. Splitting attention into 6 instead of 12 heads preserves weight shapes but changes the forward computation. Strict state_dict loading cannot catch it. Export/reload parity also cannot catch it because both models use the same wrong config. Dataset verification is optional, so it cannot be the required safety net.

### Required implementation

1. Establish a shared, explicit validation contract for the pinned PhoBERT inference configuration. Use it in preparation and in every importer resolution path: explicit directory/file, source encoder directory, and pinned local HF cache. Reject mismatches before building/exporting a model or returning an existing bundle as verified.
2. Validate all configuration values that can alter the actual encoder forward computation, including values that leave tensor shapes unchanged. Audit the installed model construction and Transformers behavior; do not stop at `num_attention_heads` alone.
3. Known pinned config values include:

   ```text
   model_type = roberta
   vocab_size = 64001
   hidden_size = 768
   num_hidden_layers = 12
   num_attention_heads = 12
   intermediate_size = 3072
   max_position_embeddings = 258
   type_vocab_size = 1
   pad_token_id = 1
   bos_token_id = 0
   eos_token_id = 2
   hidden_act = gelu
   layer_norm_eps = 1e-5
   position_embedding_type = absolute
   hidden_dropout_prob = 0.1
   attention_probs_dropout_prob = 0.1
   ```

   Also inspect normalized defaults such as decoder/cross-attention flags (`is_decoder`, `add_cross_attention`) and any runtime overrides relevant to this architecture. Confirm defaults from the pinned config and supported library behavior; do not invent undocumented values. Ensure the expected inference mode is enforced. Explain which fields form the contract and why.
4. A self-authored provenance file with a matching hash does not establish correctness. Do not fix this solely by requiring provenance to exist: an incorrect config plus a recomputed hash must still fail the pinned semantic contract. Preserve the existing model ID, revision, and checksum checks when provenance is present.
5. Prefer comparing normalized relevant values, so harmless JSON whitespace/order changes and descriptive metadata such as `_name_or_path` do not break a valid offline setup. If choosing a pinned checksum strategy instead, explain how its trusted value is established and how supported serialized config variants work. Do not use the candidate config itself to derive expected values.
6. Keep import and inference offline, with `trust_remote_code=False`. A valid explicitly supplied local config must work with an empty HF cache. No new production bypass flag, environment escape hatch, or special handling based on pytest being installed/running.
7. On mismatch, report the field, expected value, received value, and useful preparation guidance. CLI must fail nonzero; Python must raise a meaningful exception. Do not publish, activate, mutate existing bundles, or leave operation-owned staging artifacts on validation failure.
8. Keep complete config/version provenance. A changed config producing a new version ID is not sufficient if the config itself is incompatible with the pinned checkpoint.

### Required regressions

- Valid pinned config succeeds through the actual production validator.
- A same-shape config with 6 attention heads fails, both without provenance and with otherwise consistent provenance containing a recomputed candidate hash.
- At least `hidden_act`, `layer_norm_eps`, and decoder/cross-attention settings have relevant negative coverage; also retain wrong model type/dimension and missing-config coverage.
- All config resolution paths reach the same validator. Tests must not mock out the validator they claim to verify.
- Incorrect config fails before an existing-version shortcut can report success.
- Failure leaves a pre-existing temporary model pointer and bundles unchanged and does not publish another version.
- Correct local config works offline with isolated empty HF cache; do not clear the user's cache.
- Repeat the real-checkpoint 12-to-6-head reproduction using only a temporary config and temporary model root: it must now fail. Then run a valid real-checkpoint verify-only import successfully.

Existing tests use tiny synthetic Roberta configs for speed. Keep this isolation in test fixtures or a lower-level generic test seam; do not weaken the production PhoBERT contract to accept tiny encoders. Preserve separate direct tests of the real validator and real-checkpoint acceptance. The existing test near line 433 treats changing `layer_norm_eps` as an accepted version-identity change. Update this expectation for production imports, and keep any generic digest test separate from acceptance of a pinned PhoBERT config.

## 4. F2: prove export persistence by fetching from the restarted server

### Confirmed test gap

The real-model acceptance test downloads a full CSV to `tmp_path / 'full-export.csv'`, saves its bytes, restarts API/worker, then asserts:

```python
assert full_csv_path.read_bytes() == full_snapshot_bytes
```

That checks a previously downloaded client-side file. It passes even if the server loses the export. The review did not establish that production export persistence is broken; the confirmed issue is missing coverage.

Current implementation exposes `GET /api/v1/exports/{export_id}`. Export creation returns an `id` and `url`; exports are stored in the runtime database. Inspect the current API before editing tests.

### Required implementation and assertions

1. Preserve the existing real-model browser flow: quick inference, CSV import, batch inference, independent sentiment review, filtered export, full export, API/worker restart, persistence, new inference, desktop/mobile checks.
2. Before restart, capture the actual full export ID or relative download URL from the UI's creation response or download link, and record the response bytes. Capture the exact export created by that flow; do not manufacture a separate export that bypasses the UI path.
3. Stop and restart API and worker using the same isolated runtime/database, as the existing test does. It may use a different port.
4. Fetch the SAME export from the restarted API using its preserved ID/path and the new base URL. Assert HTTP 200, appropriate CSV response content, and byte-for-byte equality with the original downloaded snapshot. Do not accidentally use the old server origin or double-prefix `/api/v1`.
5. Parse the fetched bytes and assert the expected row count and at least the reviewed row's corrected/effective labels and model provenance. Keep the existing prediction and review persistence assertions.
6. Do not create a replacement export after restart to make this check pass. The downloaded local file may remain a baseline, but cannot be the evidence for server persistence.
7. The flow already adds a fourth item after restart. Fetch the original export again after that mutation and assert it still contains the original three-row snapshot with unchanged bytes. This verifies snapshot semantics without adding another expensive model flow.
8. If this reveals a real storage/API bug, fix the smallest affected code path and add a focused regression. Otherwise, keep F2 limited to tests and validation documentation.

## 5. Verification and completion criteria

Run, in order appropriate to your changes:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest tests/inference tests/test_research.py -q
.\.venv\Scripts\python.exe -X utf8 -m pytest -q
.\.venv\Scripts\python.exe -X utf8 -m pytest -m real_model -q
git diff --check
```

Inspect the real-model fixture first: ensure import and server processes target temporary storage and never activate against `runtime/models`. Tests use the real checkpoint as read-only input. Use temporary report outputs for additional verify-only checks. Do not change `runtime/cache/phobert-base-v2/config.json` for the negative reproduction; mutate a copy.

Run a frontend build only if your changes affect frontend code/build contracts or the acceptance harness requires a fresh build. No design changes are requested. Keep the real-model marker opt-in; do not skip/remove failing assertions to report success. If a required check cannot run, report the exact blocker and leave that completion criterion explicitly unverified.

Before finishing:

- Recheck production current.json against its initial snapshot; confirm the referenced bundle was not changed.
- Inspect the final diff for accidental changes and preservation of previous work.
- Update only relevant documentation with the config contract and actual fresh verification results.
- Preserve ViSoBERT format 1 compatibility, NEU format 2 behavior, UIT unavailable status, approximate underthesea preprocessing, and OOF provenance reported/not audited. Do not change paper claims or benchmark labels.

## 6. Final report to the user (Vietnamese)

Provide a concise report covering:

1. What changed for F1 and F2, with file references.
2. Evidence that the wrong 6-head config is rejected and the correct pinned config passes, including the real-checkpoint checks.
3. Evidence that the exact old export is fetched successfully after restart and remains unchanged after adding a new item.
4. Commands actually run, exact pass/fail/skipped counts, and any remaining limitations. Do not reuse the baseline counts as fresh results.
5. Confirmation that the production model pointer/bundle is unchanged, with any verification limits stated honestly.

Implement and verify these changes now; do not stop after proposing how to do them.
