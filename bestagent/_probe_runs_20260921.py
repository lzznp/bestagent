# -*- coding: utf-8 -*-
"""只读探针：把运行台账 runs.jsonl 按 session 配成"起-止"，算每次 run 的时长。
不改任何文件；输出 _probe_runs_20260921.txt（UTF-8）。
"""
import json
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = HERE / "data" / "usage" / "runs.jsonl"
OUT = HERE / "_probe_runs_20260921.txt"
L = []


def o(s=""):
    L.append(str(s))


def main():
    rows = []
    for ln in RUNS.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            rows.append(json.loads(ln))
        except Exception:
            pass
    o(f"[runs.jsonl] 共 {len(rows)} 条记录")
    sess = {}
    for r in rows:
        s = r.get("session") or "?"
        d = sess.setdefault(s, {})
        d[r.get("status") or "?"] = r
    recs = []
    for s, d in sess.items():
        run, done = d.get("running"), (d.get("done") or d.get("error"))
        if not run:
            continue
        t0 = datetime.strptime(run["ts"], "%Y-%m-%d %H:%M:%S")
        if done:
            t1 = datetime.strptime(done["ts"], "%Y-%m-%d %H:%M:%S")
            dur = (t1 - t0).total_seconds()
        else:
            dur = None
        recs.append({
            "job": run.get("job_code"), "action": run.get("action"), "start": run["ts"],
            "end": (done or {}).get("ts"), "sec": dur,
            "finish": (done or {}).get("finish_reason"),
            "new": len((done or {}).get("new_files") or []),
        })
    recs.sort(key=lambda x: (x["sec"] if x["sec"] is not None else 1e9), reverse=True)
    o("\n[按耗时降序]  start | action | 秒 | 分钟 | finish | new_files")
    for r in recs:
        sec = r["sec"]
        o(f"  {r['start']} | {r['action']:<12} | {sec if sec is not None else 'NA':>8} | "
          f"{(round(sec/60,1) if sec is not None else 'NA'):>6} | {r['finish']} | {r['new']}")
    done = [r for r in recs if r["sec"] is not None]
    o("")
    o(f"[统计] 有起止的 run {len(done)} 次；未收尾 {len(recs)-len(done)} 次")
    for th in (60, 300, 600, 1200, 3600):
        n = len([r for r in done if r["sec"] >= th])
        o(f"  >= {th:>5}s ({th//60:>3}分): {n} 次")
    o("")
    o("[按动作分组的耗时]")
    bya = {}
    for r in done:
        bya.setdefault(r["action"], []).append(r["sec"])
    for a, v in sorted(bya.items(), key=lambda kv: -max(kv[1])):
        o(f"  {a:<12} n={len(v):<3} max={max(v):>7.1f}s  avg={sum(v)/len(v):>7.1f}s")
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("OK ->", OUT.name, "lines:", len(L))


if __name__ == "__main__":
    main()
