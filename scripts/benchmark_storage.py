"""Measure local storage/import/export only; never reports these numbers as ML latency."""
import argparse
import csv
import io
import json
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.storage.db import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("runtime/validation/storage-benchmark.json"))
    arguments = parser.parse_args()
    import psutil
    cases = []
    with tempfile.TemporaryDirectory(prefix="feedback-benchmark-") as temp:
        store = Store(temp)
        for count in (1, 10, 100, 500):
            stream = io.StringIO(newline="")
            writer = csv.writer(stream, delimiter=";")
            writer.writerow(["text", "ghi_chu"])
            writer.writerows([[f"Phản hồi kiểm thử lưu trữ số {i}.\nGiữ tiếng Việt và metadata.", f"Ghi chú {i}"] for i in range(count)])
            measurement = {"rows": count}
            started = time.perf_counter()
            preview = store.preview(stream.getvalue().encode("utf-8-sig"))
            measurement["preview_ms"] = (time.perf_counter() - started) * 1000
            started = time.perf_counter()
            dataset = store.create_dataset({"name": f"Storage {count}", "profile": "neu",
                                             "preview_id": preview["preview_id"], "text_column": "text"})
            measurement["import_ms"] = (time.perf_counter() - started) * 1000
            started = time.perf_counter()
            summary = store.summary(dataset["id"], {})
            measurement["summary_ms"] = (time.perf_counter() - started) * 1000
            assert summary["total"] == count and summary["processed"] == 0
            started = time.perf_counter()
            exported = store.export(dataset["id"], {})
            measurement["export_ms"] = (time.perf_counter() - started) * 1000
            assert exported["row_count"] == count
            cases.append(measurement)
    memory = psutil.Process().memory_info()
    report = {"kind": "storage-only-no-model", "cases": cases, "rss_bytes": memory.rss,
              "peak_rss_bytes": getattr(memory, "peak_wset", None),
              "note": "One local measurement of SQLite utilities, synthetic Vietnamese CSV. "
                      "No trained model loaded. This is not inference latency or a service SLA."}
    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    arguments.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
