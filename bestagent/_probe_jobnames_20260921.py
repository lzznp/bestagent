# -*- coding: utf-8 -*-
"""只读探针：算出"老板现在在侧边栏下拉里实际看到什么标签"。
复刻 m3_chat.py 的 job_display_name 优先级（不改任何文件）。
输出写到 _probe_jobnames_20260921.out.txt（UTF-8），避免控制台编码把中文弄花。
用法：python _probe_jobnames_20260921.py
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHAT = HERE / "data" / "chat"
OUT = HERE / "_probe_jobnames_20260921.out.txt"
NOISE = ("禾蛙", "猎聘", "职位编号", "岗位职责", "")
LINES = []


def out(s=""):
    LINES.append(str(s))


def looks_like_job_title(s: str) -> bool:
    """复刻 m3_chat.py:553-568"""
    t = (s or "").split("\t")[0].strip()
    if not (4 <= len(t) <= 40):
        return False
    if any(t.startswith(n) for n in NOISE if n):
        return False
    if "：" in t or ":" in t:
        return False
    return not any(w in t for w in ("岗位职责", "职位职责", "任职要求", "工作职责",
                                    "职位描述", "薪资", "薪酬", "福利"))


def analyze_title(d: Path):
    """复刻"最新一份 analyze_*.json 里的 jd_extracted.job_title"（按 mtime）"""
    cands = sorted(d.glob("analyze_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not cands:
        return "", None
    p = cands[0]
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
        return ((data.get("jd_extracted") or {}).get("job_title") or "").strip(), p.name
    except Exception as e:
        return f"<读取失败 {e}>", p.name


def jd_pick(d: Path) -> str:
    """复刻 m3_chat.py:627-635：挑中后取 tab 前那段，再截 40 字加省略号"""
    p = d / "jd.txt"
    if not p.exists():
        return ""
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if looks_like_job_title(line):
            t = line.split("\t")[0].strip()
            return t[:40] + ("…" if len(t) > 40 else "")
    return ""


def main():
    assert CHAT.exists(), f"目录不存在：{CHAT}"
    out(f"[chat dir] {CHAT}")
    for d in sorted(CHAT.iterdir()):
        if not d.is_dir():
            continue
        out("=" * 72)
        out(f"[目录名] {d.name}")
        meta = {}
        mp = d / "meta.json"
        if mp.exists():
            meta = json.loads(mp.read_text(encoding="utf-8"))
        else:
            out("  [警告] 没有 meta.json")
        out(f"  meta.display_name = {meta.get('display_name', '')!r}")
        out(f"  meta.title        = {meta.get('title', '')!r}")
        out(f"  meta.created_at   = {meta.get('created_at', '')!r}")
        ana_jt, ana_name = analyze_title(d)
        out(f"  analyze 报告      = {ana_name!r} -> job_title = {ana_jt!r}")
        jdp = jd_pick(d)
        out(f"  jd.txt 挑中       = {jdp!r}")
        jd_p = d / "jd.txt"
        if jd_p.exists():
            head = jd_p.read_text(encoding="utf-8", errors="replace").splitlines()[:6]
            out(f"  jd.txt 前6行      = {head!r}")

        dn = (meta.get("display_name") or "").strip()
        t = (meta.get("title") or "").strip()
        if dn:
            shown, src = dn, "①display_name"
        elif t and not t.startswith("岗位 J-"):
            shown, src = t, "②title"
        elif ana_jt:
            shown, src = ana_jt, "③分析报告"
        elif jdp:
            shown, src = jdp, "④jd.txt首行"
        else:
            shown, src = d.name, "⑤退回岗位号"
        out(f"  >>> 下拉里看到的 = 「{shown}　{d.name}」   [来自 {src}]")
        rep = d / "reports"
        out(f"  reports 文件数   = {len([p for p in rep.iterdir() if p.is_file()]) if rep.exists() else 0}")

    OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    print("OK ->", OUT.name, "lines:", len(LINES))


if __name__ == "__main__":
    main()
