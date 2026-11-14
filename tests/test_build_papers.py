import io
import tarfile

import pytest
from PIL import Image

import build_papers as bp


# --- figure 1 discovery in LaTeX source ---------------------------------------

def test_finds_first_includegraphics_inside_a_figure_env():
    tex = {
        "main.tex": r"""
\documentclass{article}
\begin{document}
\includegraphics{logo}  % not in a figure, ignore
\begin{figure*}[t]
  \centering
  \includegraphics[width=\linewidth]{figs/fig1.pdf}
  \caption{Overview}
\end{figure*}
\begin{figure}\includegraphics{figs/fig2}\end{figure}
\end{document}
"""
    }
    assert bp.find_figure1(tex) == "figs/fig1.pdf"


def test_follows_input_into_section_files_and_skips_comments():
    tex = {
        "paper.tex": r"\documentclass{article}\begin{document}\input{sections/intro}\end{document}",
        "sections/intro.tex": "% \\begin{figure}\\includegraphics{old}\\end{figure}\n"
                              "\\begin{figure}\\includegraphics{new.png}\\end{figure}",
    }
    assert bp.find_figure1(tex) == "new.png"


def test_no_figure_returns_none():
    assert bp.find_figure1({"a.tex": r"\documentclass{article} hello"}) is None


def test_resolve_graphic_tries_extensions_and_graphicspath():
    files = {"figures/overview.pdf", "main.tex"}
    tex = {"main.tex": r"\graphicspath{{figures/}}"}
    assert bp.resolve_graphic("overview", files, tex) == "figures/overview.pdf"


def test_extract_figure1_from_tarball(tmp_path):
    buf = io.BytesIO()
    png = io.BytesIO()
    Image.new("RGB", (1200, 600), "red").save(png, "PNG")
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in {
            "main.tex": rb"\documentclass{article}\begin{figure}\includegraphics{f1}\end{figure}",
            "f1.png": png.getvalue(),
        }.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    out = tmp_path / "x.webp"
    bp.extract_figure1(buf.getvalue(), out)
    img = Image.open(out)
    assert img.width == bp.THUMB_WIDTH and img.height == bp.THUMB_WIDTH // 2


# --- formatting ----------------------------------------------------------------

def test_short_venue():
    assert bp.short_venue("Neural Information Processing Systems") == "NeurIPS"
    assert bp.short_venue("arXiv.org") == "preprint"
    assert bp.short_venue("") == "preprint"
    assert bp.short_venue("Some Workshop") == "Some Workshop"


def test_format_authors_bolds_me_and_elides_long_lists():
    names = [f"A{i}" for i in range(10)]
    names[6] = "Daniel Wurgaft"
    out = bp.format_authors(names + ["Noah D. Goodman"])
    assert out == "A0, A1, A2, …, <b>Daniel Wurgaft</b>, …, Noah D. Goodman"
    assert bp.format_authors(["Daniel Wurgaft", "B"]) == "<b>Daniel Wurgaft</b>, B"


def test_selected_is_exactly_the_configured_list_in_configured_order():
    papers = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
    assert [p["id"] for p in bp.selected(papers, {"selected": ["3", "1"]})] == ["3", "1"]


def test_format_authors_marks_equal_contribution():
    names = ["A", "Daniel Wurgaft", "C"]
    assert bp.format_authors(names, equal=[0, 1]) == "A*, <b>Daniel Wurgaft*</b>, C"


def test_full_list_is_everything_minus_exclude():
    papers = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
    assert [p["id"] for p in bp.full_list(papers, {"exclude": ["2"]})] == ["1", "3"]


def test_render_line_is_compact_without_thumbnail():
    p = {"id": "1", "arxiv": "1", "doi": None, "s2": "x", "title": "T", "venue": "NeurIPS",
         "year": 2025, "authors": ["Daniel Wurgaft", "B"]}
    line = bp.render_line(p)
    assert "<img" not in line and "<b>Daniel Wurgaft</b>" in line and "NeurIPS 2025" in line


def test_render_replaces_only_between_markers():
    page = "top\n<!-- all:start -->\nold\n<!-- all:end -->\nbottom"
    out = bp.splice(page, "all", "NEW")
    assert out == "top\n<!-- all:start -->\nNEW\n<!-- all:end -->\nbottom"


# --- integration -----------------------------------------------------------------

@pytest.mark.network
def test_build_end_to_end(tmp_path):
    """Real Semantic Scholar + arXiv: builds the page with the ICL paper and its figure 1."""
    page = tmp_path / "index.html"
    page.write_text("<!-- selected:start -->\n<!-- selected:end -->\n<!-- all:start -->\n<!-- all:end -->")
    cfg = {"author_id": "2387864918", "selected": ["2506.17859"], "exclude": [], "overrides": {}}
    bp.build(cfg, page, tmp_path / "img")
    html = page.read_text()
    assert "In-Context Learning Strategies Emerge Rationally" in html
    assert "NeurIPS" in html
    assert (tmp_path / "img" / "2506.17859.webp").exists()
    assert len(list((tmp_path / "img").iterdir())) == 1  # thumbnails only for selected
    full = html.split("<!-- all:start -->")[1]
    assert "Scaling up the think-aloud method" in full and "<img" not in full


def test_render_line_does_not_double_title_punctuation():
    base = {"id": "1", "arxiv": None, "doi": None, "s2": "x", "venue": "v", "year": 1, "authors": ["A"]}
    assert "Why?</a> A." in bp.render_line({**base, "title": "Why?"})
    assert "Done.</a> A." in bp.render_line({**base, "title": "Done."})
    assert "Plain</a>. A." in bp.render_line({**base, "title": "Plain"})
