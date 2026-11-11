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
    parser.add_argument("--mock-explanation", action="store_true")
    parser.add_argument("--uit-available", action="store_true")
    parser.add_argument("--provider-control")
    parser.add_argument("--fail-first-quick", action="store_true")
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

    class DemoTestOnlyRegistry(TestOnlyRegistry):
        """Registry double for sentence demo: NEU available, UIT model missing."""
        def __init__(self):
            super().__init__()
            self.quick_calls = 0

        def predict(self, profile, items):
            import time
            self.quick_calls += 1
            control = Path(args.provider_control) if args.provider_control else None
            if control:
                (control / 'quick-entered').write_text(str(self.quick_calls))
                while (control / 'quick-hold').exists():
                    time.sleep(.01)
            if args.fail_first_quick and self.quick_calls == 1:
                raise RuntimeError('Controlled first quick inference failure')
            return super().predict(profile, items)

        def status(self, profile):
            if profile == "uit" and not args.uit_available:
                return {
                    "available": False,
                    "reason": "Chưa có checkpoint cho hệ nhãn UIT.",
                    "model_id": None,
                    "model_version": None,
                    "schema_id": "uit-v1",
                }
            return super().status(profile)

    if args.varying_predictions:
        registry = VaryingTestOnlyRegistry()
    elif args.mock_explanation:
        registry = DemoTestOnlyRegistry()
    else:
        registry = TestOnlyRegistry()

    explanation_provider = None
    if args.mock_explanation:
        from services.explanation import ExplanationProvider
        import asyncio
        import json
        import time

        class E2EMockExplanationProvider(ExplanationProvider):
            async def explain(self, prompt_context: dict) -> dict[str, str]:
                control = Path(args.provider_control) if args.provider_control else None
                def record(event):
                    if control:
                        with (control / 'events.jsonl').open('a', encoding='utf-8') as output:
                            output.write(json.dumps({'event': event, 'time': time.monotonic(),
                                                     'context': prompt_context}, ensure_ascii=False) + '\n')
                record('start')
                while control and (control / 'hold').exists():
                    await asyncio.sleep(0.01)
                delay_str = os.environ.get("MOCK_EXPLANATION_DELAY", "0.4")
                try:
                    delay = float(delay_str)
                except ValueError:
                    delay = 0.4
                if delay > 0:
                    await asyncio.sleep(delay)
                record('end')
                return {
                    "reading": "Phản hồi thể hiện sự không hài lòng về dịch vụ, phù hợp với nhãn dự đoán của mô hình.",
                    "caution": "Cần xem xét thêm ý kiến chi tiết của sinh viên để có giải pháp cải thiện cụ thể.",
                }

        explanation_provider = E2EMockExplanationProvider()

    app = create_app(
        args.runtime,
        registry=None if args.without_model else registry,
        start_worker=True,
        explanation_provider=explanation_provider,
    )
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False, log_level="error")


if __name__ == "__main__":
    main()
