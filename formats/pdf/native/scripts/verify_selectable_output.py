import argparse
import hashlib
import json
import re
from pathlib import Path

from pypdf import PdfReader
from pypdf.generic import ContentStream


CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
TEXT_SHOW_OPERATORS = {b"Tj", b"TJ", b"'", b'"'}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def page_image_hashes(page) -> set[str]:
    return {sha256(item.data) for item in page.images}


def stream_text_show_count(reader: PdfReader, stream_object) -> int:
    if stream_object is None:
        return 0
    stream = ContentStream(stream_object, reader)
    return sum(operator in TEXT_SHOW_OPERATORS for _, operator in stream.operations)


def form_text_show_count(
    reader: PdfReader,
    resources,
    visited: set[tuple[int, int]],
) -> int:
    if not resources:
        return 0
    resources = resources.get_object()
    xobjects = resources.get("/XObject")
    if not xobjects:
        return 0
    count = 0
    for reference in xobjects.get_object().values():
        key = (
            int(getattr(reference, "idnum", id(reference))),
            int(getattr(reference, "generation", 0)),
        )
        if key in visited:
            continue
        visited.add(key)
        object_ = reference.get_object()
        if object_.get("/Subtype") != "/Form":
            continue
        count += stream_text_show_count(reader, object_)
        count += form_text_show_count(reader, object_.get("/Resources"), visited)
    return count


def page_text_show_count(reader: PdfReader, page) -> int:
    count = stream_text_show_count(reader, page.get_contents())
    return count + form_text_show_count(
        reader, page.get("/Resources"), set()
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument(
        "--allow-modified-image-page",
        type=int,
        action="append",
        default=[],
        help="1-based page number whose image XObjects may be changed or replaced",
    )
    parser.add_argument("--report", type=Path)
    parser.add_argument("--visual-review-complete", action="store_true")
    args = parser.parse_args()

    source = PdfReader(args.source)
    candidate = PdfReader(args.candidate)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    target_language = str(manifest.get("target_language", "")).casefold()
    target_allows_cjk = target_language.startswith(("zh", "ja", "ko"))
    assert len(source.pages) == len(candidate.pages) == len(manifest["pages"])

    allowed = set(args.allow_modified_image_page)
    coverage: list[float] = []
    extractable_cjk: dict[int, str] = {}
    selectable_failures: list[int] = []
    image_failures: list[int] = []
    geometry_failures: list[int] = []

    for page_number, (source_page, output_page, page_manifest) in enumerate(
        zip(source.pages, candidate.pages, manifest["pages"]),
        start=1,
    ):
        source_box = tuple(float(value) for value in source_page.mediabox)
        output_box = tuple(float(value) for value in output_page.mediabox)
        if (
            source_box != output_box
            or int(source_page.get("/Rotate", 0))
            != int(output_page.get("/Rotate", 0))
        ):
            geometry_failures.append(page_number)

        output_text = output_page.extract_text() or ""
        cjk = "".join(CJK.findall(output_text))
        if cjk:
            extractable_cjk[page_number] = cjk[:80]

        expected = sum(
            len(
                str(
                    block.get(
                        "render_translation_override",
                        block.get("translation") or "",
                    )
                ).strip()
            )
            for block in page_manifest["blocks"]
            if float(block["bbox"][1]) < 750
        )
        visible = len(re.sub(r"\s+", "", output_text))
        if expected:
            coverage.append(visible / expected)

        source_text = source_page.extract_text() or ""
        if source_text.strip() and page_text_show_count(candidate, output_page) == 0:
            selectable_failures.append(page_number)

        if page_number not in allowed:
            if not page_image_hashes(source_page).issubset(
                page_image_hashes(output_page)
            ):
                image_failures.append(page_number)

    report = {
        "source": str(args.source),
        "candidate": str(args.candidate),
        "source_sha256": file_sha256(args.source),
        "candidate_sha256": file_sha256(args.candidate),
        "pages": len(candidate.pages),
        "geometry_failures": geometry_failures,
        "extractable_cjk_pages": extractable_cjk,
        "selectable_text_failures": selectable_failures,
        "unapproved_image_changes": image_failures,
        "minimum_page_text_coverage": round(min(coverage), 4) if coverage else 0,
        "average_page_text_coverage": (
            round(sum(coverage) / len(coverage), 4) if coverage else 0
        ),
        "visual_review_complete": args.visual_review_complete,
    }
    assert not geometry_failures, report
    assert target_allows_cjk or not extractable_cjk, report
    assert not selectable_failures, report
    assert not image_failures, report
    assert not coverage or min(coverage) >= 0.70, report
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
