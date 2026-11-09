"""Word-Serienbrief (MERGEFIELD/IF-Felder) direkt mit Werten füllen.

Ergebnis ist ein normales Word-Dokument ohne Verknüpfung zur Excel-Datenquelle.
Andere Felder (Kontrollkästchen, Textfelder, REF) bleiben unverändert.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
Q = lambda tag: f"{{{W}}}{tag}"  # noqa: E731


def norm(name: str) -> str:
    """Feldname normalisieren: „1. Name“ == „M_1_Name“, „Kunde Haus-Nr“ == „Kunde_HausNr“."""
    name = re.sub(r"^M_(?=\d)", "", str(name))
    return re.sub(r"[^a-z0-9äöüß]", "", name.lower())


@dataclass
class _Field:
    begin: etree._Element
    parts: list = field(default_factory=list)
    phase: str = "i"
    sep: etree._Element | None = None
    end: etree._Element | None = None
    kids: list = field(default_factory=list)


_TOKEN = re.compile(r'"([^"]*)"|(<=|>=|<>|=|<|>)|([^\s"<>=]+)')


def _compare(a: str, op: str, b: str) -> bool:
    num = re.compile(r"^\s*-?[\d.,]+\s*$")
    if num.match(a) and num.match(b):
        try:
            x, y = float(a.replace(",", ".")), float(b.replace(",", "."))
            c = (x > y) - (x < y)
        except ValueError:
            c = (a.lower() > b.lower()) - (a.lower() < b.lower())
    else:
        c = (a.lower() > b.lower()) - (a.lower() < b.lower())
    return {"=": c == 0, "<>": c != 0, "<": c < 0, ">": c > 0, "<=": c <= 0, ">=": c >= 0}[op]


@dataclass
class MergeResult:
    data: bytes
    done: int
    skipped: int
    missing: list[str]


def _merge_xml(xml: bytes, values: dict[str, str], missing: set[str]) -> tuple[bytes, int, int]:
    root = etree.fromstring(xml, etree.XMLParser(huge_tree=True, remove_blank_text=False))
    stack: list[_Field] = []
    top: list[_Field] = []
    for r in root.iter(Q("r")):
        for c in r:
            if c.tag == Q("fldChar"):
                ty = c.get(Q("fldCharType"))
                if ty == "begin":
                    f = _Field(begin=r)
                    if stack:
                        p = stack[-1]
                        p.kids.append(f)
                        if p.phase == "i":
                            p.parts.append(f)
                    else:
                        top.append(f)
                    stack.append(f)
                elif ty == "separate" and stack:
                    stack[-1].phase = "r"
                    stack[-1].sep = r
                elif ty == "end" and stack:
                    stack.pop().end = r
            elif c.tag == Q("instrText") and stack:
                f = stack[-1]
                if f.phase == "i":
                    f.parts.append(c.text or "")

    def instr_of(f: _Field) -> str:
        s, quotes = "", 0
        for p in f.parts:
            if isinstance(p, str):
                s += p
                quotes += p.count('"')
            else:
                v = eval_field(p)
                txt = "" if v is None else v.replace('"', "")
                s += txt if quotes % 2 else f'"{txt}"'
        return s.strip()

    def eval_field(f: _Field) -> str | None:
        ins = instr_of(f)
        typ = (ins.split() or [""])[0].upper()
        if typ == "MERGEFIELD":
            m = re.match(r'^MERGEFIELD\s+("([^"]+)"|(\S+))(.*)$', ins, re.S | re.I)
            if not m:
                return ""
            name, rest = m.group(2) or m.group(3), m.group(4) or ""
            key = norm(name)
            if key in values:
                v = values[key]
            else:
                missing.add(name)
                v = ""
            if v:
                b = re.search(r'\\b\s+"([^"]*)"', rest)
                a = re.search(r'\\f\s+"([^"]*)"', rest)
                v = (b.group(1) if b else "") + v + (a.group(1) if a else "")
            return v
        if typ == "IF":
            tk = [
                {"v": m.group(1)} if m.group(1) is not None else ({"op": m.group(2)} if m.group(2) else {"v": m.group(3)})
                for m in _TOKEN.finditer(ins[2:])
            ]
            i, left = 0, ""
            if not tk or "op" not in tk[0]:
                left = (tk[0] if tk else {}).get("v", "")
                i = 1
            nxt = lambda: tk[i] if i < len(tk) else {}  # noqa: E731
            op = nxt().get("op", "=")
            i += 1
            right = nxt().get("v", "")
            i += 1
            yes = nxt().get("v", "")
            i += 1
            no = nxt().get("v", "")
            return yes if _compare(left, op, right) else no
        return None

    done = skipped = 0

    def replace(f: _Field) -> None:
        nonlocal done, skipped
        v = eval_field(f)
        if v is None:
            for k in f.kids:
                replace(k)
            return
        if f.end is None or f.begin.getparent() is not f.end.getparent():
            skipped += 1
            return
        parent = f.begin.getparent()
        fmt = None
        if f.sep is not None:
            n = f.sep.getnext()
            while n is not None and n is not f.end:
                if n.tag == Q("r") and n.find(Q("t")) is not None:
                    fmt = n
                    break
                n = n.getnext()
        fmt = fmt if fmt is not None else f.begin
        rpr = fmt.find(Q("rPr"))
        idx = parent.index(f.begin)
        if v != "":
            run = etree.Element(Q("r"))
            if rpr is not None:
                run.append(etree.fromstring(etree.tostring(rpr)))
            for li, line in enumerate(re.split(r"\r?\n", v)):
                if li:
                    etree.SubElement(run, Q("br"))
                t = etree.SubElement(run, Q("t"))
                t.set(f"{{{XML_NS}}}space", "preserve")
                t.text = line
            parent.insert(idx, run)
        n = f.begin
        while n is not None:
            nx = n.getnext()
            parent.remove(n)
            if n is f.end:
                break
            n = nx
        done += 1

    for f in top:
        replace(f)
    out = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    return out, done, skipped


_PARTS = re.compile(r"^word/(document|header\d*|footer\d*|footnotes|endnotes)\.xml$")


def fill_docx(template: bytes, values: dict[str, str]) -> MergeResult:
    """Alle Serienbrieffelder der Vorlage mit `values` (Excel-Spaltennamen -> Text) füllen."""
    data = {norm(k): ("" if v is None else str(v)) for k, v in values.items()}
    missing: set[str] = set()
    done = skipped = 0
    src = zipfile.ZipFile(io.BytesIO(template))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            raw = src.read(info.filename)
            if _PARTS.match(info.filename) and b"MERGEFIELD" in raw:
                raw, d, s = _merge_xml(raw, data, missing)
                done += d
                skipped += s
            elif info.filename == "word/settings.xml":
                raw = re.sub(rb"<w:mailMerge>.*?</w:mailMerge>", b"", raw, flags=re.S)
            elif info.filename == "word/_rels/settings.xml.rels":
                raw = re.sub(rb"<Relationship [^>]*mailMerge[^>]*/>", b"", raw, flags=re.I)
            dst.writestr(info, raw)
    return MergeResult(buf.getvalue(), done, skipped, sorted(missing))


def count_fields(template: bytes) -> int:
    try:
        with zipfile.ZipFile(io.BytesIO(template)) as z:
            return z.read("word/document.xml").count(b"MERGEFIELD")
    except (zipfile.BadZipFile, KeyError):
        return -1
