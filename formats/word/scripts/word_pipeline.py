#!/usr/bin/env python3
"""Deterministic Word translation pipeline: prepare, apply, validate."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile

from lxml import etree

from analyze_docx import analyze


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
W_P = f"{{{W_NS}}}p"
W_R = f"{{{W_NS}}}r"
W_T = f"{{{W_NS}}}t"
W_TAB = f"{{{W_NS}}}tab"
W_BREAKS = {f"{{{W_NS}}}br", f"{{{W_NS}}}cr"}
TEXT_PARTS = ("word/document.xml", "word/header", "word/footer", "word/footnotes.xml", "word/endnotes.xml", "word/comments.xml")


def is_text_part(name: str) -> bool:
    return name in TEXT_PARTS or name.startswith(("word/header", "word/footer")) and name.endswith(".xml")


def normalize_protected_tokens(tokens: list[str]) -> set[str]:
    return {
        re.sub(r"\s+", "", token).replace("℃", "°C").replace(",", ".").casefold()
        for token in tokens
    }


def local_content_nodes(paragraph: etree._Element) -> list[etree._Element]:
    allowed = {W_T, W_TAB, *W_BREAKS}
    return [
        node for node in paragraph.iter()
        if node.tag in allowed
        and next((ancestor for ancestor in node.iterancestors() if ancestor.tag == W_P), None) is paragraph
    ]


def paragraph_text(paragraph: etree._Element) -> str:
    pieces = []
    for node in local_content_nodes(paragraph):
        if node.tag == W_T:
            pieces.append(node.text or "")
        elif node.tag == W_TAB:
            pieces.append("\t")
        else:
            pieces.append("\n")
    return "".join(pieces).strip()


def set_text_node(node: etree._Element, value: str) -> None:
    node.text = value
    space_key = f"{{{XML_NS}}}space"
    if value[:1].isspace() or value[-1:].isspace():
        node.set(space_key, "preserve")
    else:
        node.attrib.pop(space_key, None)


def remove_cjk_width_controls(node: etree._Element, source: str, target: str) -> None:
    if not re.search(r"[\u3400-\u9fff]", source) or not re.search(r"[A-Za-z]", target):
        return
    run = next((ancestor for ancestor in node.iterancestors() if ancestor.tag == W_R), None)
    if run is None:
        return
    properties = run.find(f"{{{W_NS}}}rPr")
    if properties is None:
        return
    for name in ("spacing", "w", "fitText"):
        child = properties.find(f"{{{W_NS}}}{name}")
        if child is not None:
            properties.remove(child)


def replace_paragraph_text(paragraph: etree._Element, source: str, target: str) -> None:
    if target == source:
        return
    nodes = local_content_nodes(paragraph)
    text_indexes = [index for index, node in enumerate(nodes) if node.tag == W_T and (node.text or "").strip()]
    if not text_indexes:
        raise ValueError("paragraph has no writable text node")
    # paragraph_text() strips boundary whitespace; keep boundary tabs/breaks untouched too.
    active_nodes = nodes[text_indexes[0]:text_indexes[-1] + 1]
    separators = ["\t" if node.tag == W_TAB else "\n" for node in active_nodes if node.tag != W_T]
    target_parts = re.split(r"(\t|\n)", target)
    target_separators = target_parts[1::2]
    if target_separators != separators:
        raise ValueError("translation changed protected tab or line-break structure")
    segments = target_parts[0::2]
    groups: list[list[etree._Element]] = [[]]
    for node in active_nodes:
        if node.tag == W_T:
            groups[-1].append(node)
        else:
            groups.append([])
    if len(groups) != len(segments) or any(not group for group in groups):
        raise ValueError("paragraph has unsupported empty text segment around a tab or line break")
    for group, segment in zip(groups, segments):
        original = [node.text or "" for node in group]
        if "".join(original) == segment:
            continue
        writable = [node for node in group if (node.text or "").strip()]
        if not writable:
            writable = [group[0]]
        writable = writable[:max(1, min(len(writable), len(segment)))]
        weights = [max(1, len(node.text or "")) for node in writable]
        boundaries = [0]
        cumulative = 0
        whitespace = [index for index, char in enumerate(segment) if char.isspace()]
        for index, weight in enumerate(weights[:-1], start=1):
            cumulative += weight
            ideal = round(len(segment) * cumulative / sum(weights))
            lower = boundaries[-1] + 1
            upper = len(segment) - (len(weights) - index)
            choices = [position for position in whitespace if lower <= position <= upper]
            boundary = min(choices, key=lambda position: abs(position - ideal)) if choices else ideal
            boundaries.append(max(lower, min(upper, boundary)))
        boundaries.append(len(segment))
        for node in group:
            set_text_node(node, "")
        for index, node in enumerate(writable):
            value = segment[boundaries[index]:boundaries[index + 1]]
            set_text_node(node, value)
            remove_cjk_width_controls(node, source, target)


def prepare(source: Path, job_dir: Path, target_language: str) -> Path:
    job_dir.mkdir(parents=True, exist_ok=True)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest().upper()
    if source.suffix.lower() == ".doc":
        working = job_dir / "source-working.docx"
        script = Path(__file__).with_name("word_com.ps1")
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Action", "convert", "-InputPath", str(source), "-OutputPath", str(working)], check=True)
    elif source.suffix.lower() == ".docx":
        working = job_dir / ("source-working" + source.suffix.lower())
        shutil.copy2(source, working)
    else:
        raise ValueError("Word pipeline accepts only .doc and .docx")
    report = analyze(working)
    if "unsupported_chart_text" in report["complex_reasons"]:
        raise ValueError("unsupported editable chart text; translate or remove the chart text before retrying")
    units = [{"id": index, "source": text, "target": ""} for index, text in enumerate(report["unique_texts"], 1)]
    manifest = {
        "schema": 1, "source": str(source.resolve()), "source_sha256": source_hash,
        "working_docx": str(working.resolve()), "target_language": target_language,
        "baseline": {key: report[key] for key in ("section_count", "table_count", "media_count")},
        "protected_tokens": report["protected_tokens"], "units": units,
    }
    path = job_dir / "translation-manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"stage": "prepared", "units": len(units), "manifest": str(path.resolve())}, ensure_ascii=False))
    return path


def apply(manifest_path: Path, output: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    missing = [unit["id"] for unit in manifest["units"] if not unit.get("target")]
    if missing:
        raise ValueError(f"translation targets are empty: {missing}")
    mapping = {unit["source"]: unit["target"] for unit in manifest["units"]}
    applied = Counter()
    source = Path(manifest["working_docx"])
    output.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() == output.resolve():
        raise ValueError("input and output paths must be different")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with ZipFile(source) as src, ZipFile(temporary, "w", ZIP_DEFLATED) as dst:
            for info in src.infolist():
                data = src.read(info.filename)
                if is_text_part(info.filename):
                    parser = etree.XMLParser(remove_blank_text=False, resolve_entities=False)
                    root = etree.fromstring(data, parser)
                    for paragraph in root.iter(W_P):
                        source_text = paragraph_text(paragraph)
                        if source_text in mapping:
                            replace_paragraph_text(paragraph, source_text, mapping[source_text])
                            applied[source_text] += 1
                    data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
                dst.writestr(info, data)
        unmatched = [unit["id"] for unit in manifest["units"] if applied[unit["source"]] == 0]
        apply_report = {
            "applied_occurrences": sum(applied.values()),
            "matched_units": len(applied),
            "unmatched_unit_ids": unmatched,
        }
        (manifest_path.parent / "apply-report.json").write_text(
            json.dumps(apply_report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if unmatched:
            raise ValueError(f"translation units were not written: {unmatched}")
        with ZipFile(temporary) as package:
            if package.testzip() is not None or "word/document.xml" not in package.namelist():
                raise ValueError("generated DOCX package failed integrity validation")
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    print(json.dumps({"stage": "applied", "output": str(output.resolve())}, ensure_ascii=False))


def validate(candidate: Path, manifest_path: Path, word_native: bool = False) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    report = analyze(candidate)
    failures = []
    source = Path(manifest["source"])
    if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest().upper() != manifest["source_sha256"]:
        failures.append("source file hash changed")
    candidate_texts = set(report["unique_texts"])
    missing_targets = [unit["id"] for unit in manifest["units"] if unit["target"] not in candidate_texts]
    if missing_targets:
        failures.append(f"missing target text for units: {missing_targets}")
    target_texts = {unit["target"] for unit in manifest["units"]}
    unsafe_layout = [item for item in report.get("text_layout_risks", []) if item.get("text") in target_texts]
    if unsafe_layout:
        failures.append(f"unsafe translated text layout: {unsafe_layout}")
    expected_tokens = normalize_protected_tokens([
        token for occurrence in manifest["protected_tokens"] for token in occurrence["tokens"]
    ])
    actual_tokens = normalize_protected_tokens([
        token for occurrence in report["protected_tokens"] for token in occurrence["tokens"]
    ])
    if actual_tokens != expected_tokens:
        failures.append("protected token mismatch")
    for key in ("section_count", "table_count", "media_count"):
        if report[key] != manifest["baseline"][key]:
            failures.append(f"{key}: expected {manifest['baseline'][key]}, got {report[key]}")
    warnings = []
    word_report = {"status": "skipped"}
    if word_native:
        script = Path(__file__).with_name("word_com.ps1")
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Action", "validate", "-InputPath", str(candidate)],
                check=True, capture_output=True, text=True, timeout=30,
            )
            word_report = json.loads(result.stdout.strip().splitlines()[-1])
            word_report["status"] = "passed"
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError, IndexError, KeyError) as exc:
            warning = f"optional Word-native check failed: {exc}"
            warnings.append(warning)
            word_report = {"status": "warning", "message": warning}
    qa = {"passed": not failures, "failures": failures, "warnings": warnings, "structure": report, "word": word_report}
    qa_path = manifest_path.parent / "qa-report.json"
    qa_path.write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8")
    if failures:
        raise ValueError("; ".join(failures))
    print(json.dumps({"stage": "validated", "word_native": word_report["status"], "report": str(qa_path.resolve())}, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("prepare")
    p.add_argument("source", type=Path); p.add_argument("--job-dir", type=Path, required=True); p.add_argument("--target-language", required=True)
    a = commands.add_parser("apply")
    a.add_argument("manifest", type=Path); a.add_argument("--output", type=Path, required=True)
    v = commands.add_parser("validate")
    v.add_argument("candidate", type=Path); v.add_argument("--manifest", type=Path, required=True)
    v.add_argument("--word-native", action="store_true", help="Run optional non-blocking Microsoft Word open/pagination check")
    args = parser.parse_args()
    try:
        if args.command == "prepare": prepare(args.source, args.job_dir, args.target_language)
        elif args.command == "apply": apply(args.manifest, args.output)
        else: validate(args.candidate, args.manifest, args.word_native)
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr); return 2


if __name__ == "__main__":
    raise SystemExit(main())
