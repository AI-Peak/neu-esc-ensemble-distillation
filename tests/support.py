"""Explicit software-test double. This is not a trained model or inference evidence."""
import json
from pathlib import Path

PROFILES = {p["id"]: p for p in json.loads((Path(__file__).resolve().parents[1] / "services/profiles.json").read_text(encoding="utf-8"))}


class TestOnlyRegistry:
    __test__ = False

    def status(self, profile):
        return {"available": True, "reason": None, "model_id": "TEST-DOUBLE-NOT-A-MODEL",
                "model_version": "software-test-only-v1", "schema_id": PROFILES[profile]["schema_id"]}

    def predict(self, profile, items):
        outputs = []
        for item in items:
            prediction = {k: self.status(profile)[k] for k in ("model_id", "model_version", "schema_id")}
            for task in ("sentiment", "topic"):
                count = len(PROFILES[profile][task])
                winner = sum(map(ord, item["text"])) % count
                scores = [0.1 / (count - 1)] * count
                scores[winner] = 0.9
                prediction[task] = {"label_id": winner, "scores": scores}
            token_count = len(item["text"].split()) + 2
            prediction.update(item_id=item["item_id"], revision_id=item["revision_id"],
                              duration_ms=0.01, token_count_before_truncation=token_count,
                              truncated=token_count > 128,
                              warnings=["INPUT_TRUNCATED"] if token_count > 128 else [])
            outputs.append(prediction)
        # Deliberately reverse output to verify the worker joins by stable IDs.
        return outputs[::-1]
