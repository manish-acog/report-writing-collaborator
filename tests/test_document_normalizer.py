from __future__ import annotations

import hashlib
import re
import stat
import sys
from pathlib import Path

import pymupdf
import pytest

from canonical_workspace import (
    DocumentConversionError,
    DocumentNormalizationError,
    DocumentNormalizer,
    DocumentParseError,
    SourceSpec,
    UnsupportedDocumentTypeError,
)


def _make_pdf(path: Path, *, image: bool = False) -> None:
    document = pymupdf.open()
    document.set_metadata({"title": "Normalization sample", "author": "Aganitha"})
    first_page = document.new_page()
    first_page.insert_textbox(
        pymupdf.Rect(72, 200, 500, 600),
        "# First page\n\nBody paragraph one.\nBody paragraph two.",
        fontsize=12,
    )
    second_page = document.new_page()
    second_page.insert_textbox(
        pymupdf.Rect(72, 200, 500, 600),
        "# Second page\n\nBody paragraph one.\nBody paragraph two.",
        fontsize=12,
    )
    first_page = document.load_page(0)

    first_page.insert_link(
        {
            "kind": pymupdf.LINK_URI,
            "from": pymupdf.Rect(72, 80, 200, 100),
            "uri": "https://example.com/evidence",
        }
    )
    first_page.insert_link(
        {
            "kind": pymupdf.LINK_GOTO,
            "from": pymupdf.Rect(72, 110, 200, 130),
            "page": 1,
            "to": pymupdf.Point(0, 0),
        }
    )
    document.embfile_add(
        "evidence.txt",
        b"embedded evidence",
        filename="evidence.txt",
        desc="Supporting evidence",
    )

    if image:
        pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 100, 100), False)
        pixmap.clear_with(0x336699)
        first_page.insert_image(
            pymupdf.Rect(72, 150, 272, 350),
            stream=pixmap.tobytes("png"),
        )

    document.save(path)
    document.close()


def _add_named_link(path: Path, nameddest: str) -> None:
    # PyMuPDF's insert_link() cannot create LINK_NAMED annotations; inject the
    # raw PDF object directly to reproduce hyperref-style citation anchors.
    document = pymupdf.open(path)
    page = document[0]
    rect = pymupdf.Rect(72, 400, 200, 420)
    annot_xref = document.get_new_xref()
    document.update_object(
        annot_xref,
        "<< /Type /Annot /Subtype /Link /Rect "
        f"[{rect.x0} {rect.y0} {rect.x1} {rect.y1}] "
        f"/Border [0 0 0] /Dest ({nameddest}) >>",
    )
    document.xref_set_key(page.xref, "Annots", f"[{annot_xref} 0 R]")
    document.saveIncr()
    document.close()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_png_bytes(width: int, height: int, color: int = 0x336699) -> bytes:
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, width, height), False)
    pixmap.clear_with(color)
    return pixmap.tobytes("png")


def _make_soffice(
    path: Path,
    template_pdf: Path,
    version: str = "26.8.0",
    conversion_exit: int = 0,
) -> None:
    script = f"""#!{sys.executable}
import shutil
import sys
from pathlib import Path

if "--version" in sys.argv:
    print("LibreOffice {version}")
    raise SystemExit(0)

if {conversion_exit}:
    print("conversion failed", file=sys.stderr)
    raise SystemExit({conversion_exit})

outdir = Path(sys.argv[sys.argv.index("--outdir") + 1])
shutil.copyfile({str(template_pdf)!r}, outdir / "original.pdf")
"""
    path.write_text(script, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_pdf_normalization_preserves_provenance(tmp_path: Path) -> None:
    source = tmp_path / "sample.pdf"
    staging = tmp_path / "staging with spaces"
    _make_pdf(source, image=True)
    original_hash = _sha256(source)

    result = DocumentNormalizer(staging).normalize_document(
        SourceSpec(path=source, source_instance_id="source_01")
    )

    assert result.source_id == f"src_{original_hash[:12]}"
    assert result.source_instance_id == "source_01"
    assert result.source_type == "pdf"
    assert result.hashes.source_sha256 == original_hash
    assert result.hashes.normalized_sha256 == _sha256(staging / result.normalized_path)
    assert result.metadata["title"] == "Normalization sample"
    assert result.metadata["page_count"] == 2
    assert len(result.page_map) == 2
    assert result.page_map[0].start_line == 1
    assert result.page_map[0].end_line is not None
    assert result.page_map[1].start_line is not None
    assert result.page_map[1].start_line > result.page_map[0].end_line
    assert {link.kind for link in result.links} == {"external", "internal"}
    assert result.links[1].target_page == 2
    assert result.embedded_files[0].original_name == "evidence.txt"
    assert (staging / result.embedded_files[0].path).read_bytes() == b"embedded evidence"
    assert result.assets
    assert all((staging / asset.path).is_file() for asset in result.assets)
    assert all(
        not Path(path).is_absolute() for path in (result.original_path, result.normalized_path)
    )
    markdown_path = staging / result.normalized_path
    image_match = re.search(r"!\[[^\]]*\]\(([^)]+)\)", markdown_path.read_text(encoding="utf-8"))
    assert image_match is not None
    resolved_image = (markdown_path.parent / image_match.group(1)).resolve()
    assert image_match.group(1).startswith("../../assets/")
    assert resolved_image in {(staging / asset.path).resolve() for asset in result.assets}
    assert _sha256(source) == original_hash
    assert result.tooling.normalizer == "pymupdf4llm"
    assert result.tooling.normalizer_version == "1.28.2"
    assert result.tooling.converter is None
    assert result.warnings == ()


def _make_single_page_pdf(path: Path, *, width: float = 200, height: float = 200) -> None:
    document = pymupdf.open()
    document.new_page(width=width, height=height)
    document.save(path)
    document.close()


def test_collect_assets_dedupes_identical_content(tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    _make_single_page_pdf(pdf_path)
    normalizer = DocumentNormalizer(tmp_path / "staging")
    source_id = "src_test"
    assets_dir = normalizer._assets_dir(source_id)
    assets_dir.mkdir(parents=True)
    duplicate = _make_png_bytes(60, 60)
    distinct = _make_png_bytes(60, 60, color=0x992200)
    (assets_dir / "document-0001-00.png").write_bytes(duplicate)
    (assets_dir / "document-0001-01.png").write_bytes(duplicate)
    (assets_dir / "document-0001-02.png").write_bytes(distinct)

    assets = normalizer._collect_assets(source_id, pdf_path)

    assert [Path(asset.path).name for asset in assets] == [
        "document-0001-00.png",
        "document-0001-02.png",
    ]
    # Duplicate file itself is untouched -- only the returned asset list dedupes.
    assert (assets_dir / "document-0001-01.png").is_file()


def test_collect_assets_filters_undersized_images(tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    _make_single_page_pdf(pdf_path, width=200, height=200)
    normalizer = DocumentNormalizer(tmp_path / "staging")
    source_id = "src_test"
    assets_dir = normalizer._assets_dir(source_id)
    assets_dir.mkdir(parents=True)
    # Page is 200x200pt; at _IMAGE_DPI=150 that's ~417px/side, 10% ~= 42px.
    (assets_dir / "document-0001-00.png").write_bytes(_make_png_bytes(200, 200))
    (assets_dir / "document-0001-01.png").write_bytes(_make_png_bytes(10, 10))

    assets = normalizer._collect_assets(source_id, pdf_path)

    assert [Path(asset.path).name for asset in assets] == ["document-0001-00.png"]
    # The filtered file itself is untouched -- only the returned asset list excludes it.
    assert (assets_dir / "document-0001-01.png").is_file()


def test_collect_assets_rejects_unexpected_image_filename(tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    _make_single_page_pdf(pdf_path)
    normalizer = DocumentNormalizer(tmp_path / "staging")
    source_id = "src_test"
    assets_dir = normalizer._assets_dir(source_id)
    assets_dir.mkdir(parents=True)
    (assets_dir / "unexpected-name.png").write_bytes(_make_png_bytes(60, 60))

    with pytest.raises(DocumentParseError, match="doesn't match expected pattern"):
        normalizer._collect_assets(source_id, pdf_path)



def test_named_destination_link_is_internal(tmp_path: Path) -> None:
    source = tmp_path / "cited.pdf"
    _make_pdf(source)
    _add_named_link(source, "cite.hochreiter1997")

    result = DocumentNormalizer(tmp_path / "staging").normalize_document(
        SourceSpec(source, "source_01")
    )

    named_links = [link for link in result.links if link.target == "cite.hochreiter1997"]
    assert len(named_links) == 1
    assert named_links[0].kind == "internal"
    assert result.warnings == ()


def test_running_footer_is_captured_and_stripped_from_body(tmp_path: Path) -> None:
    source = tmp_path / "footered.pdf"
    document = pymupdf.open()
    for page_index in range(3):
        page = document.new_page()
        page.insert_textbox(
            pymupdf.Rect(72, 150, 500, 600),
            f"Body content for page {page_index + 1}.",
            fontsize=12,
        )
        # A small, fixed-position line near the bottom of every page is what
        # PyMuPDF4LLM's layout model classifies as a running footer.
        page.insert_text((280, 770), f"Page {page_index + 1}", fontsize=8)
    document.save(source)
    document.close()

    result = DocumentNormalizer(tmp_path / "staging").normalize_document(
        SourceSpec(source, "source_01")
    )

    assert [entry.footer for entry in result.header_footer] == ["Page 1", "Page 2", "Page 3"]
    assert all(entry.header is None for entry in result.header_footer)
    body = (tmp_path / "staging" / result.normalized_path).read_text(encoding="utf-8")
    assert "Page 1" not in body
    assert "Body content for page 1." in body


def test_sparse_pdf_text_is_not_discarded(tmp_path: Path) -> None:
    source = tmp_path / "sparse.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 450), "Sparse document body")
    document.save(source)
    document.close()

    staging = tmp_path / "staging"
    result = DocumentNormalizer(staging).normalize_document(SourceSpec(source, "source_01"))

    assert "Sparse document body" in (staging / result.normalized_path).read_text(encoding="utf-8")
    assert result.warnings == (
        "Page 1 classified entirely as header/footer; original text kept in body",
    )


def test_office_source_uses_pinned_libreoffice(tmp_path: Path) -> None:
    source = tmp_path / "sample.docx"
    source.write_bytes(b"office source")
    template_pdf = tmp_path / "template.pdf"
    _make_pdf(template_pdf)
    soffice = tmp_path / "soffice"
    _make_soffice(soffice, template_pdf)

    result = DocumentNormalizer(
        tmp_path / "staging",
        libreoffice_path=soffice,
    ).normalize_document(SourceSpec(source, "source_02"))

    assert result.source_type == "docx"
    assert result.original_path.endswith("original.docx")
    assert result.tooling.converter == "libreoffice"
    assert result.tooling.converter_version == "26.8.0"
    assert "First page" in (tmp_path / "staging" / result.normalized_path).read_text(
        encoding="utf-8"
    )


def test_office_source_rejects_unpinned_version(tmp_path: Path) -> None:
    source = tmp_path / "sample.pptx"
    source.write_bytes(b"office source")
    template_pdf = tmp_path / "template.pdf"
    _make_pdf(template_pdf)
    soffice = tmp_path / "soffice"
    _make_soffice(soffice, template_pdf, version="26.2.5")

    with pytest.raises(DocumentConversionError, match=r"26\.8\.0 required"):
        DocumentNormalizer(
            tmp_path / "staging",
            libreoffice_path=soffice,
        ).normalize_document(SourceSpec(source, "source_01"))


def test_office_conversion_failure_is_typed(tmp_path: Path) -> None:
    source = tmp_path / "sample.doc"
    source.write_bytes(b"office source")
    template_pdf = tmp_path / "template.pdf"
    _make_pdf(template_pdf)
    soffice = tmp_path / "soffice"
    _make_soffice(soffice, template_pdf, conversion_exit=2)

    with pytest.raises(DocumentConversionError, match="conversion failed"):
        DocumentNormalizer(
            tmp_path / "staging",
            libreoffice_path=soffice,
        ).normalize_document(SourceSpec(source, "source_01"))


@pytest.mark.parametrize("suffix", ["txt", "odt", ""])
def test_unsupported_source_type_is_typed(tmp_path: Path, suffix: str) -> None:
    source = tmp_path / (f"sample.{suffix}" if suffix else "sample")
    source.write_text("unsupported", encoding="utf-8")

    with pytest.raises(UnsupportedDocumentTypeError):
        DocumentNormalizer(tmp_path / "staging").normalize_document(SourceSpec(source, "source_01"))


def test_source_instance_id_is_required(tmp_path: Path) -> None:
    source = tmp_path / "sample.pdf"
    _make_pdf(source)

    with pytest.raises(DocumentNormalizationError, match="instance ID is required"):
        DocumentNormalizer(tmp_path / "staging").normalize_document(SourceSpec(source, ""))


def test_corrupt_pdf_is_typed(tmp_path: Path) -> None:
    source = tmp_path / "corrupt.pdf"
    source.write_bytes(b"not a PDF")

    with pytest.raises(DocumentParseError):
        DocumentNormalizer(tmp_path / "staging").normalize_document(SourceSpec(source, "source_01"))
