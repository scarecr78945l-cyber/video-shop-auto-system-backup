# -*- coding: utf-8 -*-
"""只读解析 盈亏表T.xlsx 的 cid盈亏表 列头与前几行公式（不修改任何文件）。"""
import zipfile, re, sys, json
from xml.etree import ElementTree as ET

XLSX = r"E:\新建文件夹 (6)\视频号小店全自动系统-方案文档\_experiment\_interop\evidence\盈亏表T.xlsx"
NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
}

def col_name(ref):
    m = re.match(r"([A-Z]+)", ref or "")
    return m.group(1) if m else "?"

def main():
    z = zipfile.ZipFile(XLSX)
    names = z.namelist()
    print("== zip entries (filtered) ==")
    for n in names:
        if any(k in n.lower() for k in ("xl/worksheets/sheet", "workbook.xml", "sharedstrings", "workbook.xml.rel")):
            print(n, z.getinfo(n).file_size)
    # workbook.xml -> sheet name -> rId
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    sheets = {}
    for s in wb.findall(".//main:sheet", NS):
        sheets[s.get("name")] = s.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
    print("\n== sheets ==", sheets)
    # workbook rels -> rId -> target
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    rid2target = {}
    for r in rels.findall("pr:Relationship", NS):
        rid2target[r.get("Id")] = r.get("Target")
    print("\n== rid map ==")
    for rid, tgt in rid2target.items():
        if "sheet" in tgt.lower():
            print(rid, tgt)
    # find cid sheet
    target_sheet = None
    for name, rid in sheets.items():
        if "cid" in name.lower():
            target_sheet = name
            break
    print("\n== target sheet ==", target_sheet)
    if target_sheet is None:
        print("cid sheet not found; sheets=", list(sheets.keys()))
        return
    rid = sheets[target_sheet]
    tgt = rid2target.get(rid, "")
    if tgt.startswith("/"):
        tgt = tgt.lstrip("/")
    else:
        # relative to xl/
        tgt = "xl/" + tgt.lstrip("/")
    print("sheet path:", tgt)
    # shared strings
    sst = []
    if "xl/sharedStrings.xml" in names:
        ss = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in ss.findall("main:si", NS):
            txt = "".join(t.text or "" for t in si.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"))
            sst.append(txt)
    print("\n== sharedStrings count ==", len(sst))
    # parse sheet rows: first 8 rows, show cell ref, value (inline or shared), formula
    sheet_root = ET.fromstring(z.read(tgt))
    rows = sheet_root.findall(".//main:sheetData/main:row", NS)
    print("total rows:", len(rows))
    for r in rows[:8]:
        rn = r.get("r")
        cells = []
        for c in r.findall("main:c", NS):
            ref = c.get("r")
            t = c.get("t")
            v = c.find("main:v", NS)
            f = c.find("main:f", NS)
            val = v.text if v is not None else ""
            if t == "s" and val.isdigit() and int(val) < len(sst):
                val = sst[int(val)]
            fm = f.text if f is not None else ""
            cells.append(f"{ref}({t}):{val[:28]}{' ['+fm[:40]+']' if fm else ''}")
        print(f"row {rn}: " + " | ".join(cells))

if __name__ == "__main__":
    main()
