"""Explicit software-test double. This is not a trained model or inference evidence."""
import hashlib
import json
from pathlib import Path

from services.inference.registry import ModelIdentityChanged, ModelUnavailable

PROFILES = {p["id"]: p for p in json.loads((Path(__file__).resolve().parents[1] / "services/profiles.json").read_text(encoding="utf-8"))}


class TestOnlyRegistry:
    __test__ = False

    def __init__(self):
        self.available = True
        self.model_id = "TEST-DOUBLE-NOT-A-MODEL"
        self.model_version = "software-test-only-v1"
        self.manifest_sha256 = None
        self.preprocessing_sha256 = None
        self.preprocessing_tag = "default"
        self.fail = False
        self.hook = None
        self.bad = None
        self.keep_order = False
        self.pair_fail = False
        self.pair_identity_mismatch = False
        self.pair_hook = None
        self.pair_bad = None
        self.pair_keep_order = False
        self.pair_input_equal_override = None
        self.pair_input_equal_fn = None
        self.pair_returned_identity = None
        self.pair_result_override = None

    def status(self, profile):
        schema_id = PROFILES.get(profile, {}).get("schema_id", "unknown")
        if profile not in PROFILES or not self.available:
            return {
                "available": False,
                "reason": "Artifact missing" if profile in PROFILES else f"Unknown profile: {profile}",
                "model_id": None,
                "model_version": None,
                "schema_id": schema_id,
            }
        return {
            "available": True,
            "reason": None,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "schema_id": PROFILES[profile]["schema_id"],
        }

    def execution_identity(self, profile):
        if profile not in PROFILES:
            raise ModelUnavailable(f"Unknown profile: {profile}")
        if not self.available:
            raise ModelUnavailable("Model unavailable: Artifact missing")
        manifest_sha = self.manifest_sha256 or hashlib.sha256(
            f"{profile}:{self.model_id}:{self.model_version}:manifest".encode("utf-8")
        ).hexdigest()
        preprocessing_sha = self.preprocessing_sha256 or hashlib.sha256(
            f"{profile}:{self.preprocessing_tag}:preprocessing".encode("utf-8")
        ).hexdigest()
        return {
            "profile": profile,
            "schema_id": PROFILES[profile]["schema_id"],
            "model_id": self.model_id,
            "model_version": self.model_version,
            "manifest_sha256": manifest_sha,
            "preprocessing_sha256": preprocessing_sha,
            "mode": "cpu-fp32-eval",
        }

    def predict(self, profile, items):
        if self.hook:
            self.hook()
        if self.fail:
            raise self.fail if isinstance(self.fail, Exception) else RuntimeError("PRIVATE INPUT MUST NOT BE PERSISTED")
        st = self.status(profile)
        if not st["available"]:
            raise ModelUnavailable(st["reason"] or "Model unavailable")
        outputs = []
        for item in items:
            prediction = {k: st[k] for k in ("model_id", "model_version", "schema_id")}
            for task in ("sentiment", "topic"):
                count = len(PROFILES[profile][task])
                winner = sum(map(ord, item["text"])) % count
                scores = [0.1 / (count - 1)] * count
                scores[winner] = 0.9
                prediction[task] = {"label_id": winner, "scores": scores}
            token_count = len(item["text"].split()) + 2
            prediction.update(
                item_id=item["item_id"],
                revision_id=item["revision_id"],
                duration_ms=0.01,
                token_count_before_truncation=token_count,
                truncated=token_count > 128,
                warnings=["INPUT_TRUNCATED"] if token_count > 128 else [],
            )
            if self.bad:
                self.bad(prediction)
            outputs.append(prediction)
        # Deliberately reverse output by default to verify the worker joins by stable IDs.
        return outputs if self.keep_order else outputs[::-1]

    def predict_pair(self, profile, items, expected_identity):
        if not isinstance(items, list) or len(items) != 2 or not isinstance(expected_identity, dict):
            raise ValueError("Pair inference requires 2 items and expected_identity")
        actual_identity = self.execution_identity(profile)
        if self.pair_identity_mismatch or actual_identity != expected_identity:
            raise ModelIdentityChanged("Model execution identity changed before pair inference.")
        if self.pair_hook:
            try:
                self.pair_hook(profile, items, expected_identity)
            except TypeError:
                self.pair_hook()
        if self.pair_fail:
            raise self.pair_fail if isinstance(self.pair_fail, Exception) else RuntimeError(
                f"PRIVATE INPUT MUST NOT BE PERSISTED: {items[0]['text']}"
            )
        prev_keep_order = self.keep_order
        try:
            self.keep_order = self.pair_keep_order
            predictions = self.predict(profile, items)
        finally:
            self.keep_order = prev_keep_order
        if self.pair_bad:
            self.pair_bad(predictions, items)
        if self.pair_input_equal_override is not None:
            model_input_equal = self.pair_input_equal_override
        elif self.pair_input_equal_fn is not None:
            model_input_equal = self.pair_input_equal_fn(items)
        else:
            model_input_equal = items[0]["text"] == items[1]["text"]
        result = {
            "predictions": predictions,
            "execution_identity": self.pair_returned_identity if self.pair_returned_identity is not None else actual_identity,
            "model_input_equal": model_input_equal,
        }
        if self.pair_result_override:
            result = self.pair_result_override(result, profile, items, expected_identity)
        return result
