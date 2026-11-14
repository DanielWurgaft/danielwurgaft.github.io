"""Rebuild the papers section of index.html from Semantic Scholar + arXiv.

Two lists, each spliced between <!-- name:start/end --> markers:
  selected — exactly papers.yaml `selected`, with figure-1 thumbnails pulled from
             the arXiv LaTeX source (first \\includegraphics inside a figure env)
  all      — every paper on the Semantic Scholar profile, minus `exclude`

    uv run python scripts/build_papers.py
"""
import gzip
import html
import io
import os
import re
import tarfile
import time
from pathlib import Path, PurePosixPath

import pymupdf
import requests
import yaml
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ME = "Wurgaft"
THUMB_WIDTH = 480
HEADERS = {"User-Agent": "academic-site-builder/0.1"}
VENUES = {
    "Neural Information Processing Systems": "NeurIPS",
    "International Conference on Learning Representations": "ICLR",
    "International Conference on Machine Learning": "ICML",
    "Cognitive Science Society": "CogSci",
    "Trans. Mach. Learn. Res.": "TMLR",
    "Conference on Language Modeling": "COLM",
    "Empirical Methods in Natural Language Processing": "EMNLP",
    "Association for Computational Linguistics": "ACL",
}


# --- Semantic Scholar ----------------------------------------------------------

def get(url, **params):
    for wait in [0, 5, 15, 30, 60]:  # Semantic Scholar rate-limits anonymous clients
        time.sleep(wait)
        r = requests.get(url, params=params, headers=HEADERS, timeout=60)
        if r.status_code != 429:
            break
    r.raise_for_status()
    return r


def fetch_papers(author_id):
    data = get(
        f"https://api.semanticscholar.org/graph/v1/author/{author_id}/papers",
        fields="title,year,venue,externalIds,authors,publicationDate",
        limit=500,
    ).json()["data"]
    papers = [
        {
            "id": p["externalIds"].get("ArXiv") or p["paperId"],
            "arxiv": p["externalIds"].get("ArXiv"),
            "doi": p["externalIds"].get("DOI"),
            "s2": p["paperId"],
            "title": p["title"],
            "venue": short_venue(p["venue"]),
            "year": p["year"],
            "date": p["publicationDate"] or str(p["year"] or ""),
            "authors": [a["name"] for a in p["authors"]],
        }
        for p in data
    ]
    return sorted(dedupe(papers), key=lambda p: p["date"], reverse=True)


def dedupe(papers):
    """Merge entries with the same title (e.g. an arXiv version and a conference version)."""
    by_title = {}
    for p in papers:
        k = re.sub(r"\W", "", p["title"].lower())
        if k not in by_title:
            by_title[k] = p
            continue
        q = by_title[k]
        q["arxiv"] = q["arxiv"] or p["arxiv"]
        q["id"] = q["arxiv"] or q["id"]
        if q["venue"] == "preprint":
            q["venue"], q["year"] = p["venue"], p["year"]
        q["date"] = max(q["date"], p["date"])
    return list(by_title.values())


def short_venue(venue):
    if venue in ("", "arXiv.org"):
        return "preprint"
    return next((v for k, v in VENUES.items() if k in venue), venue)


def selected(papers, cfg):
    return [p for p in papers if p["id"] in cfg["selected"]]


def full_list(papers, cfg):
    return [p for p in papers if p["id"] not in cfg["exclude"]]


# --- figure 1 ------------------------------------------------------------------

def strip_comments(s):
    return re.sub(r"(?<!\\)%.*", "", s)


def expand(name, tex, seen=()):
    body = strip_comments(tex[name])
    def sub(m):
        child = m.group(1).strip()
        child = child if child.endswith(".tex") else child + ".tex"
        return expand(child, tex, seen + (name,)) if child in tex and child not in seen else ""
    return re.sub(r"\\(?:input|include)\{([^}]+)\}", sub, body)


def find_figure1(tex):
    mains = [n for n, s in tex.items() if r"\documentclass" in strip_comments(s)]
    mains.sort(key=lambda n: r"\begin{document}" not in tex[n])
    for main in mains:
        body = expand(main, tex)
        for fig in re.finditer(r"\\begin\{figure\*?\}(.*?)\\end\{figure\*?\}", body, re.S):
            g = re.search(r"\\includegraphics\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}", fig.group(1))
            if g:
                return g.group(1).strip()
    return None


def resolve_graphic(name, files, tex):
    dirs = [""] + [d for s in tex.values() for gp in re.findall(r"\\graphicspath\{((?:\{[^}]*\})+)\}", s)
                   for d in re.findall(r"\{([^}]*)\}", gp)]
    for d in dirs:
        for ext in ["", ".pdf", ".png", ".jpg", ".jpeg"]:
            path = str(PurePosixPath(d) / (name + ext)).removeprefix("./")
            if path in files:
                return path
    return None


def to_image(name, data):
    if name.lower().endswith(".pdf"):
        page = pymupdf.open(stream=data, filetype="pdf")[0]
        pix = page.get_pixmap(dpi=round(2 * THUMB_WIDTH * 72 / page.rect.width))  # render at 2x thumb width
        return Image.open(io.BytesIO(pix.tobytes("png")))
    return Image.open(io.BytesIO(data))


def extract_figure1(source, out):
    """`source` is the raw arXiv e-print (a .tar.gz of the LaTeX project)."""
    with tarfile.open(fileobj=io.BytesIO(source), mode="r:*") as tar:
        members = {m.name.removeprefix("./"): m for m in tar.getmembers() if m.isfile()}
        tex = {n: tar.extractfile(m).read().decode("utf-8", "replace")
               for n, m in members.items() if n.endswith(".tex")}
        name = find_figure1(tex)
        assert name, "no \\includegraphics inside a figure environment"
        path = resolve_graphic(name, set(members), tex)
        assert path, f"figure 1 '{name}' not found in source"
        img = to_image(path, tar.extractfile(members[path]).read())
    img = img.convert("RGBA")
    flat = Image.new("RGB", img.size, "white")
    flat.paste(img, mask=img)
    flat = flat.resize((THUMB_WIDTH, round(THUMB_WIDTH * img.height / img.width)), Image.LANCZOS)
    out.parent.mkdir(parents=True, exist_ok=True)
    flat.save(out, "WEBP", quality=85)


def arxiv_source(arxiv_id):
    time.sleep(3)  # arXiv asks for <1 request / 3s
    data = get(f"https://arxiv.org/e-print/{arxiv_id}").content
    if data[:2] == b"\x1f\x8b" and not tarfile.is_tarfile(io.BytesIO(data)):
        data = gzip.decompress(data)  # tar wrapped in gzip is handled by tarfile; this is the bare-gzip case
    return data


# --- rendering -----------------------------------------------------------------

def format_authors(names):
    me = next((i for i, n in enumerate(names) if ME in n), None)
    shown = sorted({i for i in [0, 1, 2, me, len(names) - 1] if i is not None and i < len(names)})
    if len(names) <= 6:
        shown = range(len(names))
    parts, prev = [], -1
    for i in shown:
        if i > prev + 1:
            parts.append("…")
        parts.append(f"<b>{html.escape(names[i])}</b>" if i == me else html.escape(names[i]))
        prev = i
    return ", ".join(parts)


def url_of(p):
    return p.get("url") or (f"https://arxiv.org/abs/{p['arxiv']}" if p["arxiv"]
                            else f"https://doi.org/{p['doi']}" if p["doi"]
                            else f"https://www.semanticscholar.org/paper/{p['s2']}")


def render(p, thumb):
    url = url_of(p)
    links = [f'<a href="https://arxiv.org/pdf/{p["arxiv"]}">pdf</a>'] if p["arxiv"] else []
    links += [f'<a href="{html.escape(u)}">{html.escape(k)}</a>' for k, u in p.get("links", {}).items()]
    img = (f'<a class="thumb" href="{url}"><img src="{thumb}" alt="" loading="lazy"></a>'
           if thumb else '<span class="thumb"></span>')
    return f"""<li class="paper">
  {img}
  <div>
    <a class="title" href="{url}">{html.escape(p["title"])}</a>
    <span class="authors">{format_authors(p["authors"])}</span>
    <span class="venue">{html.escape(p["venue"])} {p["year"] or ""}</span>
    <span class="extras">{" · ".join(links)}</span>
  </div>
</li>"""


def render_line(p):
    end = "" if p["title"][-1] in ".?!" else "."
    return (f'<li><a href="{url_of(p)}">{html.escape(p["title"])}</a>{end} '
            f'{format_authors(p["authors"])}. <i>{html.escape(p["venue"])} {p["year"] or ""}</i></li>')


def splice(page, name, inner):
    start, end = f"<!-- {name}:start -->", f"<!-- {name}:end -->"
    return re.sub(f"{start}.*?{end}", lambda _: f"{start}\n{inner}\n{end}", page, flags=re.S)


def build(cfg, page_path, img_dir):
    papers = fetch_papers(cfg["author_id"])
    for p in papers:
        p.update(cfg["overrides"].get(p["id"], {}))
    items = []
    for p in selected(papers, cfg):
        fig = p.get("figure")
        if fig is None and p["arxiv"]:
            out = img_dir / f"{p['id']}.webp"
            if not out.exists():
                print(f"figure 1 ← arXiv {p['arxiv']}  {p['title'][:60]}")
                extract_figure1(arxiv_source(p["arxiv"]), out)
            fig = os.path.relpath(out, page_path.parent)
        items.append(render(p, None if fig in (None, "none") else fig))
    rest = [render_line(p) for p in full_list(papers, cfg)]
    page = splice(page_path.read_text(), "selected", "\n".join(items))
    page_path.write_text(splice(page, "all", "\n".join(rest)))
    print(f"wrote {len(items)} selected + {len(rest)} total papers to {page_path}")


if __name__ == "__main__":
    build(yaml.safe_load((ROOT / "papers.yaml").read_text()), ROOT / "index.html", ROOT / "img" / "papers")
