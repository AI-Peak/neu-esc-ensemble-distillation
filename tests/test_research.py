from services.research import get_research_summary


def test_reports_are_sourced_and_do_not_duplicate_baseline():
    report = get_research_summary()
    rows = report["rows"]
    keys = [(r["dataset"], r["backbone"], r["setup"], r["task"], r["metric"]) for r in rows]
    assert len(rows) == len(set(keys)) == 88

    neu_setups = {r["setup"] for r in rows if r["dataset"] == "neu"}
    uit_setups = {r["setup"] for r in rows if r["dataset"] == "uit"}
    assert neu_setups == {"single", "mtl", "mtl_smart", "mtl_mlm", "mtl_mlm_smart", "mtl_ed"}
    assert uit_setups == {"mtl", "mtl_smart", "mtl_mlm", "mtl_mlm_smart", "mtl_ed"}
    assert "single" not in uit_setups

    neu_pho = next(r for r in rows if (r["dataset"], r["backbone"], r["setup"], r["task"], r["metric"])
                   == ("neu", "phobert", "mtl_ed", "sentiment", "accuracy"))
    assert round(neu_pho["mean"], 2) == 83.51
    assert neu_pho["seeds"] == 15
    assert neu_pho["seed_ids"] == list(range(42, 57))

    neu_viso = next(r for r in rows if (r["dataset"], r["backbone"], r["setup"], r["task"], r["metric"])
                    == ("neu", "visobert", "mtl_ed", "sentiment", "accuracy"))
    assert round(neu_viso["mean"], 2) == 83.25
    assert neu_viso["seeds"] == 15

    uit_pho = next(r for r in rows if (r["dataset"], r["backbone"], r["setup"], r["task"], r["metric"])
                   == ("uit", "phobert", "mtl_ed", "topic", "accuracy"))
    assert round(uit_pho["mean"], 2) == 89.71
    assert uit_pho["seeds"] == 10
    assert uit_pho["seed_ids"] == list(range(42, 52))

    assert all(r["source"] and len(r["source_sha256"]) == 64 for r in rows)
    assert len(report["oof_ablation"]) == 8
    assert report["statistical_protocol"]["families"] == {
        "neu_ed_vs_baselines": 40,
        "uit_ed_vs_baselines": 32,
        "neu_oof_vs_insample_ablation": 8,
    }
