from services.research import get_research_summary


def test_reports_are_sourced_and_do_not_duplicate_baseline():
    report = get_research_summary()
    rows = report["rows"]
    keys = [(r["dataset"], r["backbone"], r["setup"], r["task"], r["metric"]) for r in rows]
    assert len(rows) == len(set(keys)) == 32
    neu = next(r for r in rows if (r["dataset"], r["backbone"], r["setup"], r["task"], r["metric"])
               == ("neu", "visobert", "mtl_ed", "sentiment", "accuracy"))
    assert round(neu["mean"], 2) == 83.25
    assert neu["seeds"] == 15
    assert neu["seed_ids"] == list(range(42, 57))
    assert all(r["source"] and len(r["source_sha256"]) == 64 for r in rows)
