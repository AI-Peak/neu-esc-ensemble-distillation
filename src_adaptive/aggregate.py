"""Aggregate completed Adaptive Interaction run directories without imputing missing runs."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import pandas as pd

def collect(root):
    rows=[]
    for path in sorted(Path(root).glob("*/metrics.json")):
        data=json.loads(path.read_text(encoding="utf-8"))
        if data.get("status") != "COMPLETED" or data.get("config",{}).get("smoke"):
            continue
        test=data.get("test",{}); cfg=data.get("config",{})
        rows.append({"run":path.parent.name,"variant":cfg.get("variant"),"seed":cfg.get("seed"),
                     "sentiment_macro_f1":test.get("sentiment",{}).get("macro_f1"),"sentiment_accuracy":test.get("sentiment",{}).get("accuracy"),
                     "topic_macro_f1":test.get("topic",{}).get("macro_f1"),"topic_accuracy":test.get("topic",{}).get("accuracy"),
                     "trainable_parameters":data.get("parameters",{}).get("trainable"),"wall_seconds":data.get("wall_seconds")})
    return pd.DataFrame(rows)

def main():
    p=argparse.ArgumentParser(); p.add_argument("runs"); p.add_argument("--out",required=True); a=p.parse_args()
    out=Path(a.out); out.mkdir(parents=True,exist_ok=True); df=collect(a.runs); df.to_csv(out/"adaptive_completed_runs.csv",index=False)
    if not df.empty:
        summary=df.groupby("variant").agg({"sentiment_macro_f1":["mean","std"],"topic_macro_f1":["mean","std"],"wall_seconds":["mean","std"]}).reset_index()
        summary.to_csv(out/"adaptive_summary.csv",index=False)
    print(df.to_string(index=False) if not df.empty else "No reportable completed runs found")
if __name__ == "__main__": main()
