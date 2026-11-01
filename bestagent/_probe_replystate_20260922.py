import sys, pathlib, sqlite3
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
db = pathlib.Path(r"D:\study\bestagent\bestagent\data\chat\J-CHAT-20260921-143843\job.db")
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
print("表:", [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")])
for t in ("candidate_events", "events", "greet_log", "replies"):
    try:
        n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t}: {n} 行")
    except Exception as e:
        print(f"  {t}: 无此表（{e}）")
con.close()
