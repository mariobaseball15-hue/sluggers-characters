"""CREDITS.md is the one source of our credits (Nick: "rather too much credit than too little"). The patcher window's
Credits tab, each tab's credit line and the download's README all come from here, so they can't drift apart.

  import credits
  credits.text()               # the whole file as plain text (the Credits tab, README.txt)
  credits.text(edition)        # an edition's (the beta): only what it has, everyone else thanked in one line
  credits.tab_line("Captains") # that tab's line from "Thanks, part by part", or None
  credits.page_line()          # the Characters Beta page's line (its "### Page"), or None
  credits.sections()           # {heading: plain text}

  python scripts/credits.py [tab name]    # print the plain text, or one tab's line
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "CREDITS.md"
TABS = "Thanks, part by part"
BETA = "In the Characters Beta"         # an edition's own versions of some sections (text(edition))
REPLACED = ("Thanks, part by part", "Extra Innings", "Models and sounds", "Music", "Software")   # by BETA's


def plain(md):
    """Markdown -> plain text: **bold** and `code` lose their marks, [text](url) becomes "text (url)"; paragraphs are
    joined into single lines (bullets keep their "- ")."""
    md = re.sub(r"\*\*(.+?)\*\*", r"\1", md, flags=re.S)
    md = re.sub(r"`([^`]+)`", r"\1", md)
    md = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", md)
    out, para = [], []
    for line in md.splitlines() + [""]:
        s = line.strip()
        if not s or s.startswith("- "):
            if para:
                out.append(" ".join(para))
                para = []
            if s:
                para = [s]
            elif out and out[-1] != "":
                out.append("")
        else:
            para.append(s)
    return "\n".join(out).strip()


def sections(path=SOURCE):
    """{heading: plain text} in file order (the title's own paragraph under "")."""
    md = Path(path).read_text(encoding="utf8")
    parts, head, body = {}, "", []
    for line in md.splitlines():
        if line.startswith("## "):
            parts[head] = plain("\n".join(body))
            head, body = line[3:].strip(), []
        elif not line.startswith("# "):
            body.append(line)
    parts[head] = plain("\n".join(body))
    return parts


def _block(md, title):
    """The markdown of one "## title" section, heading included ("" if there's none)."""
    i = md.find(f"\n## {title}\n")
    if i < 0:
        return ""
    j = md.find("\n## ", i + 1)
    return md[i:j if j >= 0 else len(md)]


def _subsections(md):
    """{title: markdown} of BETA's "### " subsections."""
    out, head, body = {}, None, []
    for line in _block(md, BETA).splitlines():
        if line.startswith("### "):
            if head:
                out[head] = "\n".join(body).strip()
            head, body = line[4:].strip(), []
        elif head:
            body.append(line)
    if head:
        out[head] = "\n".join(body).strip()
    return out


def bold_names(md):
    """The **bold** names in some CREDITS.md markdown (the people we thank), in order, each once."""
    return list(dict.fromkeys(re.sub(r"\s+", " ", m) for m in re.findall(r"\*\*(.+?)\*\*", md, re.S)))


def _format(parts):
    out = ["Credits", "======="]
    for head, body in parts.items():
        if head:
            out += ["", head, "-" * len(head)]
        out += ["", body] if body else []
    return "\n".join(out).strip() + "\n"


def text(edition=None, path=SOURCE):
    """CREDITS.md as plain text, headings underlined (without BETA: that's the editions'). edition (an edition dict,
    edition.load()): the edition's credits (Nick: "NO REFERENCES TO FUTURE FEATURES", and more credit, not less):
    BETA's subsections in place of REPLACED (a REPLACED section it has no version of is left out), only the part-by-part
    lines it lists, and one line thanking everyone named anywhere in CREDITS.md whom that text doesn't name, so nobody
    disappears."""
    parts = sections(path)
    parts.pop(BETA, None)
    if not edition:
        return _format(parts)
    md = Path(path).read_text(encoding="utf8")
    sub = _subsections(md)
    keep = [t.strip() for t in sub.get("Part by part", "").split(",") if t.strip()]
    keep = [(t.partition("=")[0].strip(), (t.partition("=")[2] or t).strip()) for t in keep]   # "Shown = Tab":
    lines = tab_lines(path)                             # a tab's line under the edition's own name (the beta's Items)
    out = {}
    for head, body in parts.items():
        if head == TABS:
            out[head] = "\n".join(f"- {shown}: {lines[t]}" for shown, t in keep if t in lines)
        elif head in REPLACED:
            if head in sub:
                out[head] = plain(sub[head])
        else:
            out[head] = body
    said = _format(out)
    everyone = bold_names(md.replace(_block(md, BETA), ""))
    missing = [n for n in everyone if n not in said]
    if missing:
        names = ", ".join(missing[:-1]) + (" and " if len(missing) > 1 else "") + missing[-1]
        items = list(out.items())
        at = next((i for i, (h, _) in enumerate(items) if h == "Thank you"), len(items))
        items.insert(at, ("Thanks also", f"Thanks also to {names} for years of Sluggers research, codes, tools, rips "
                                         f"and music."))
        out = dict(items)
    return _format(out)


def tab_lines(path=SOURCE):
    """{tab name: its credit line}, from the "Thanks, part by part" bullets ("- Tab: line"). Each line is a whole
    sentence ("Thanks to ..."): the window shows it as it is (Nick: "built on" read as if we took people's code)."""
    body = sections(path).get(TABS, "")
    return {m.group(1).strip(): m.group(2).strip() for m in re.finditer(r"^- ([^:]+): (.+)$", body, re.M)}


def tab_line(name, path=SOURCE):
    return tab_lines(path).get(name)


def page_line(path=SOURCE):
    """The Characters Beta page's own credit line (BETA's "### Page"): a whole "Thanks to ..." sentence, or None."""
    line = plain(_subsections(Path(path).read_text(encoding="utf8")).get("Page", ""))
    return line or None


if __name__ == "__main__":
    print(tab_line(sys.argv[1]) if len(sys.argv) > 1 else text())
