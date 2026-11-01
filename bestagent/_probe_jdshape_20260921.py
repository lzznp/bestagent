# -*- coding: utf-8 -*-
"""只读探针：看老板粘贴的 jd.txt 到底长什么样（页头噪音 / 职位编号 / 真实岗位名在哪一行）。
不改任何文件；输出 UTF-8 到 _probe_jdshape_20260921.out.txt。
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHAT = HERE / "data" / "chat"
OUT = HERE / "_probe_jdshape_20260921.out.txt"
L = []


def o(s=""):
    L.append(str(s))


def main():
    assert CHAT.exists()
    for d in sorted(CHAT.iterdir()):
        p = d / "jd.txt"
        if not d.is_dir() or not p.exists():
            continue
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        o("=" * 72)
        o(f"[{d.name}] jd.txt 共 {len(lines)} 行, {p.stat().st_size} 字节")
        o("  -- 前 20 行 --")
        for i, ln in enumerate(lines[:20], 1):
            o(f"   {i:3}: {ln!r}")
        idx = [i for i, ln in enumerate(lines, 1) if "职位编号" in ln]
        o(f"  含『职位编号』的行号: {idx}")
        for i in idx:
            for j in range(i, min(i + 3, len(lines) + 1)):
                o(f"     {j:3}: {lines[j - 1]!r}")
        o("  -- 含『职能分类/所属行业/工作城市/学历要求』的行 --")
        for i, ln in enumerate(lines, 1):
            if any(k in ln for k in ("职能分类", "所属行业", "工作城市", "学历要求", "年薪范围")):
                o(f"   {i:3}: {ln!r}")
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("OK ->", OUT.name, "lines:", len(L))


if __name__ == "__main__":
    main()
