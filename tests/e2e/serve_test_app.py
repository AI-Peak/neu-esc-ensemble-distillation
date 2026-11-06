"""Standalone test-only harness. Production has no double/fixture flag."""
import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--without-model", action="store_true")
    parser.add_argument("--varying-predictions", action="store_true")
    args = parser.parse_args()
    os.environ["FEEDBACK_RUNTIME"] = args.runtime
    from services.api.main import create_app
    from tests.support import TestOnlyRegistry
    import uvicorn

    class VaryingTestOnlyRegistry(TestOnlyRegistry):
        """One-row test runs intentionally disagree; never used by production."""
        calls = 0

        def predict(self, profile, items):
            self.calls += 1
            outputs = super().predict(profile, items)
            for output in outputs:
                winner = 1 if self.calls == 1 else 2
                scores = [0.05] * len(output['sentiment']['scores'])
                scores[winner] = 1 - 0.05 * (len(scores) - 1)
                output['sentiment'] = {'label_id': winner, 'scores': scores}
            return outputs

    registry = VaryingTestOnlyRegistry() if args.varying_predictions else TestOnlyRegistry()
    app = create_app(args.runtime, registry=None if args.without_model else registry, start_worker=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False, log_level="error")


if __name__ == "__main__":
    main()
