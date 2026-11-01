# -*- coding: utf-8 -*-
"""只读探针：看看 PM 给的岗位表 智库交付侧岗位需求及说明.xlsx 里到底有什么列。
不改任何文件；输出 UTF-8 到 _probe_xlsx_20260921.out.txt。
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent          # ...\bestagent
WS = HERE.parent                                 # ...\studybessagent 工作区根
XLSX = WS / "智库交付侧岗位需求及说明.xlsx"
OUT = HERE / "_probe_xlsx_20260921.out.txt"
L = []


def o(s=""):
    L.append(str(s))


def main():
    o(f"[xlsx] {XLSX}  exists={XLSX.exists()}  size={XLSX.stat().st_size if XLSX.exists() else 'NA'}")
    try:
        import openpyxl
        o(f"[openpyxl] version = {getattr(openpyxl, '__version__', '?')}")
    except Exception as e:
        o(f"[openpyxl] 不可用: {e!r}")
        OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
        print("OK(no openpyxl) ->", OUT.name)
        return

    wb = openpyxl.load_workbook(XLSX, data_only=True)
    o(f"[sheets] {wb.sheetnames}")
    for ws in wb.worksheets:
        o("=" * 72)
        o(f"[sheet] {ws.title}  dims={ws.dimensions}  max_row={ws.max_row} max_col={ws.max_column}")
        for r in range(1, min(ws.max_row, 40) + 1):
            vals = []
            for c in range(1, min(ws.max_column, 12) + 1):
                v = ws.cell(row=r, column=c).value
                if v is None:
                    continue
                sv = str(v).replace("\n", "\\n")
                vals.append(f"{openpyxl.utils.get_column_letter(c)}{r}={sv[:160]!r}")
            if vals:
                o("  " + " | ".join(vals))
        if ws.max_row > 40:
            o(f"  ...（共 {ws.max_row} 行，上面只打了前 40 行）")

    o("=" * 72)
    o("[全表搜索关键词]")
    for kw in ("FAE", "电气设计", "机械工程师", "电气工程师", "远景", "智库"):
        hits = []
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    if cell.value is not None and kw in str(cell.value):
                        hits.append(f"{ws.title}!{cell.coordinate}")
                        if len(hits) >= 12:
                            break
        o(f"  {kw}: {hits if hits else '（没找到）'}")

    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("OK ->", OUT.name, "lines:", len(L))


if __name__ == "__main__":
    main()
