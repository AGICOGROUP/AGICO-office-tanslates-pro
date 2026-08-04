#!/usr/bin/env python3
"""Route a verified Excel container to the correct translation engine."""

from __future__ import annotations

import json
from pathlib import Path
import posixpath
import struct
import sys
import xml.etree.ElementTree as ET
from zipfile import BadZipFile, ZipFile


CFB_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")
CFB_FREE = 0xFFFFFFFF
CFB_END = 0xFFFFFFFE
CFB_FAT = 0xFFFFFFFD
CFB_DIFAT = 0xFFFFFFFC
CFB_MAX_REGULAR = 0xFFFFFFFA
NO_STREAM = 0xFFFFFFFF
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
XLSM_CONTENT_TYPE = "application/vnd.ms-excel.sheet.macroEnabled.main+xml"
VBA_CONTENT_TYPE = "application/vnd.ms-office.vbaProject"
CONTENT_TYPES_NAMESPACE = "http://schemas.openxmlformats.org/package/2006/content-types"
SPREADSHEETML_NAMESPACE = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
RELATIONSHIPS_NAMESPACE = "http://schemas.openxmlformats.org/package/2006/relationships"
VBA_RELATIONSHIP_TYPE = "http://schemas.microsoft.com/office/2006/relationships/vbaProject"


def _cfb_failure(message: str) -> ValueError:
    return ValueError(f"invalid CFB Excel container: {message}")


def validate_excel_cfb(data: bytes) -> None:
    """Validate the CFB allocation tables and require a root-level Excel stream."""
    if len(data) < 1024 or data[:8] != CFB_SIGNATURE:
        raise _cfb_failure("truncated header")
    if data[28:30] != b"\xfe\xff":
        raise _cfb_failure("wrong byte order")
    major_version = struct.unpack_from("<H", data, 26)[0]
    sector_shift = struct.unpack_from("<H", data, 30)[0]
    if (major_version, sector_shift) not in {(3, 9), (4, 12)}:
        raise _cfb_failure("unsupported version or sector size")
    sector_size = 1 << sector_shift
    if len(data) % sector_size:
        raise _cfb_failure("file length is not sector aligned")
    sector_count = len(data) // sector_size - 1

    def read_sector(sector_id: int) -> bytes:
        if sector_id > CFB_MAX_REGULAR or sector_id >= sector_count:
            raise _cfb_failure(f"sector {sector_id} is out of range")
        offset = (sector_id + 1) * sector_size
        return data[offset : offset + sector_size]

    fat_sector_count = struct.unpack_from("<I", data, 44)[0]
    first_directory_sector = struct.unpack_from("<I", data, 48)[0]
    first_difat_sector = struct.unpack_from("<I", data, 68)[0]
    difat_sector_count = struct.unpack_from("<I", data, 72)[0]
    if fat_sector_count == 0 or fat_sector_count > sector_count:
        raise _cfb_failure("invalid FAT sector count")

    difat = list(struct.unpack_from("<109I", data, 76))
    difat = [sector_id for sector_id in difat if sector_id != CFB_FREE]
    seen_difat: set[int] = set()
    next_difat = first_difat_sector
    integers_per_sector = sector_size // 4
    for _ in range(difat_sector_count):
        if next_difat in seen_difat:
            raise _cfb_failure("cyclic DIFAT chain")
        seen_difat.add(next_difat)
        difat_sector = read_sector(next_difat)
        values = struct.unpack(f"<{integers_per_sector}I", difat_sector)
        difat.extend(sector_id for sector_id in values[:-1] if sector_id != CFB_FREE)
        next_difat = values[-1]
    if difat_sector_count and next_difat != CFB_END:
        raise _cfb_failure("unterminated DIFAT chain")
    if len(difat) < fat_sector_count:
        raise _cfb_failure("FAT sectors are missing from DIFAT")
    fat_sector_ids = difat[:fat_sector_count]
    if len(set(fat_sector_ids)) != len(fat_sector_ids):
        raise _cfb_failure("duplicate FAT sector")

    fat: list[int] = []
    for sector_id in fat_sector_ids:
        fat.extend(struct.unpack(f"<{integers_per_sector}I", read_sector(sector_id)))
    if len(fat) < sector_count:
        raise _cfb_failure("FAT is shorter than the container")
    for sector_id in fat_sector_ids:
        if fat[sector_id] != CFB_FAT:
            raise _cfb_failure("FAT sector is not marked as FAT")

    def read_chain(first_sector: int, label: str) -> bytes:
        chunks: list[bytes] = []
        seen: set[int] = set()
        sector_id = first_sector
        while sector_id != CFB_END:
            if sector_id in seen:
                raise _cfb_failure(f"cyclic {label} chain")
            if sector_id > CFB_MAX_REGULAR or sector_id >= sector_count:
                raise _cfb_failure(f"invalid {label} sector")
            seen.add(sector_id)
            chunks.append(read_sector(sector_id))
            sector_id = fat[sector_id]
            if len(seen) > sector_count:
                raise _cfb_failure(f"overlong {label} chain")
        return b"".join(chunks)

    directory_bytes = read_chain(first_directory_sector, "directory")
    if len(directory_bytes) < 128:
        raise _cfb_failure("directory is empty")

    entries: list[dict] = []
    for offset in range(0, len(directory_bytes), 128):
        entry = directory_bytes[offset : offset + 128]
        if len(entry) < 128:
            break
        entry_type = entry[66]
        name_length = struct.unpack_from("<H", entry, 64)[0]
        name = ""
        if entry_type:
            if name_length < 2 or name_length > 64 or name_length % 2:
                raise _cfb_failure("invalid directory entry name")
            try:
                name = entry[: name_length - 2].decode("utf-16le")
            except UnicodeDecodeError as exc:
                raise _cfb_failure("invalid directory entry encoding") from exc
        entries.append(
            {
                "name": name,
                "type": entry_type,
                "left": struct.unpack_from("<I", entry, 68)[0],
                "right": struct.unpack_from("<I", entry, 72)[0],
                "child": struct.unpack_from("<I", entry, 76)[0],
                "start": struct.unpack_from("<I", entry, 116)[0],
                "size": struct.unpack_from("<Q", entry, 120)[0],
            }
        )
    if not entries or entries[0]["type"] != 5 or entries[0]["name"] != "Root Entry":
        raise _cfb_failure("missing root directory entry")

    root_children: list[int] = []
    visited: set[int] = set()

    def walk_sibling_tree(entry_id: int) -> None:
        if entry_id == NO_STREAM:
            return
        if entry_id >= len(entries) or entry_id in visited:
            raise _cfb_failure("invalid or cyclic directory tree")
        visited.add(entry_id)
        entry = entries[entry_id]
        if entry["type"] not in {1, 2}:
            raise _cfb_failure("invalid root child entry type")
        walk_sibling_tree(entry["left"])
        root_children.append(entry_id)
        walk_sibling_tree(entry["right"])

    walk_sibling_tree(entries[0]["child"])
    root_names = {entries[entry_id]["name"] for entry_id in root_children}
    if {"EncryptedPackage", "EncryptionInfo"} & root_names:
        raise ValueError("encrypted CFB Excel workbooks are not supported")
    workbook_entries = [entries[entry_id] for entry_id in root_children if entries[entry_id]["name"] in {"Workbook", "Book"} and entries[entry_id]["type"] == 2]
    if len(workbook_entries) != 1:
        raise _cfb_failure("missing unique root-level Workbook or Book stream")
    workbook = workbook_entries[0]
    if workbook["size"] <= 0 or workbook["start"] in {CFB_FREE, CFB_END, CFB_FAT, CFB_DIFAT}:
        raise _cfb_failure("Workbook stream is empty or invalid")

    mini_stream_cutoff = struct.unpack_from("<I", data, 56)[0]
    if workbook["size"] >= mini_stream_cutoff:
        workbook_bytes = read_chain(workbook["start"], "Workbook")
    else:
        mini_sector_size = 1 << struct.unpack_from("<H", data, 32)[0]
        first_mini_fat_sector = struct.unpack_from("<I", data, 60)[0]
        mini_fat_sector_count = struct.unpack_from("<I", data, 64)[0]
        root = entries[0]
        if mini_sector_size != 64 or mini_fat_sector_count == 0 or root["size"] <= 0:
            raise _cfb_failure("Workbook mini stream metadata is missing")
        mini_fat_bytes = read_chain(first_mini_fat_sector, "mini FAT")
        if len(mini_fat_bytes) < mini_fat_sector_count * sector_size:
            raise _cfb_failure("mini FAT is truncated")
        mini_fat = struct.unpack(f"<{len(mini_fat_bytes) // 4}I", mini_fat_bytes)
        root_stream = read_chain(root["start"], "root mini stream")[: root["size"]]
        chunks: list[bytes] = []
        seen_mini: set[int] = set()
        mini_sector_id = workbook["start"]
        while mini_sector_id != CFB_END:
            if mini_sector_id in seen_mini or mini_sector_id >= len(mini_fat):
                raise _cfb_failure("invalid or cyclic Workbook mini stream")
            seen_mini.add(mini_sector_id)
            offset = mini_sector_id * mini_sector_size
            chunk = root_stream[offset : offset + mini_sector_size]
            if len(chunk) != mini_sector_size:
                raise _cfb_failure("Workbook mini stream is truncated")
            chunks.append(chunk)
            mini_sector_id = mini_fat[mini_sector_id]
        workbook_bytes = b"".join(chunks)
    workbook_bytes = workbook_bytes[: workbook["size"]]
    if len(workbook_bytes) != workbook["size"]:
        raise _cfb_failure("Workbook stream is truncated")
    validate_biff_workbook(workbook_bytes)


def validate_biff_workbook(workbook: bytes) -> None:
    if len(workbook) < 4:
        raise _cfb_failure("BIFF Workbook stream is empty")
    first_record = struct.unpack_from("<H", workbook, 0)[0]
    if first_record not in {0x0009, 0x0209, 0x0409, 0x0809}:
        raise _cfb_failure("Workbook stream does not begin with a BIFF BOF record")
    offset = 0
    while offset + 4 <= len(workbook):
        record_id, record_size = struct.unpack_from("<HH", workbook, offset)
        offset += 4
        if offset + record_size > len(workbook):
            raise _cfb_failure("truncated BIFF record")
        if record_id == 0x002F:
            raise ValueError("encrypted CFB Excel workbook: BIFF FILEPASS record found")
        offset += record_size
        if record_id == 0x000A:
            return
    raise _cfb_failure("BIFF global substream has no EOF record")


def parse_ooxml_workbook_type(content_types: bytes, workbook_xml: bytes) -> tuple[str, dict[str, str]]:
    try:
        types_root = ET.fromstring(content_types)
        workbook_root = ET.fromstring(workbook_xml)
    except ET.ParseError as exc:
        raise ValueError(f"invalid OOXML XML: {exc}") from exc
    if types_root.tag != f"{{{CONTENT_TYPES_NAMESPACE}}}Types":
        raise ValueError("invalid OOXML content types namespace")
    if workbook_root.tag != f"{{{SPREADSHEETML_NAMESPACE}}}workbook":
        raise ValueError("invalid OOXML workbook namespace")
    overrides = {
        node.attrib.get("PartName", "").lstrip("/"): node.attrib.get("ContentType", "")
        for node in types_root
        if node.tag == f"{{{CONTENT_TYPES_NAMESPACE}}}Override" and node.attrib.get("PartName")
    }
    content_type = overrides.get("xl/workbook.xml")
    if not content_type:
        raise ValueError("missing OOXML workbook content type")
    if content_type not in {XLSX_CONTENT_TYPE, XLSM_CONTENT_TYPE}:
        raise ValueError(f"unsupported OOXML workbook content type: {content_type}")
    return content_type, overrides


def validate_vba_relationship(relationships_xml: bytes) -> bool:
    try:
        root = ET.fromstring(relationships_xml)
    except ET.ParseError as exc:
        raise ValueError(f"invalid VBA relationships XML: {exc}") from exc
    if root.tag != f"{{{RELATIONSHIPS_NAMESPACE}}}Relationships":
        raise ValueError("invalid VBA relationships namespace")
    matches = [
        node
        for node in root
        if node.tag == f"{{{RELATIONSHIPS_NAMESPACE}}}Relationship"
        and node.attrib.get("Type") == VBA_RELATIONSHIP_TYPE
    ]
    if len(matches) > 1:
        raise ValueError("ambiguous VBA workbook relationship")
    if not matches:
        return False
    relationship = matches[0]
    if relationship.attrib.get("TargetMode", "Internal") != "Internal":
        raise ValueError("VBA workbook relationship must be internal")
    target = relationship.attrib.get("Target", "").replace("\\", "/")
    resolved_target = posixpath.normpath(target).lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl", target))
    if resolved_target != "xl/vbaProject.bin":
        raise ValueError(f"VBA workbook relationship resolves to unexpected target: {resolved_target}")
    return True


def route(path: str | Path) -> dict:
    source = Path(path)
    if not source.is_file():
        raise ValueError(f"file not found: {source}")
    extension = source.suffix.lower()
    source_bytes = source.read_bytes()
    prefix = source_bytes[:8]

    if prefix == CFB_SIGNATURE:
        validate_excel_cfb(source_bytes)
        if extension != ".xls":
            raise ValueError(f"extension/signature mismatch: CFB Excel input must use .xls, got {extension or '<none>'}")
        return {
            "format": "excel",
            "subtype": "xls",
            "detection": "cfb-signature",
            "engine": "excel-compatible-converter",
            "requires_conversion": True,
            "preserve_vba": True,
            "legacy_vba_inspection_required": True,
        }

    try:
        with ZipFile(source) as archive:
            corrupt = archive.testzip()
            if corrupt:
                raise ValueError(f"corrupt OOXML member: {corrupt}")
            names = set(archive.namelist())
            if "[Content_Types].xml" not in names or "xl/workbook.xml" not in names:
                raise ValueError("ZIP container is not an Excel OOXML workbook")
            content_types = archive.read("[Content_Types].xml")
            workbook_xml = archive.read("xl/workbook.xml")
            relationships_xml = archive.read("xl/_rels/workbook.xml.rels") if "xl/_rels/workbook.xml.rels" in names else None
    except BadZipFile as exc:
        raise ValueError("unsupported or corrupt Excel container") from exc

    has_vba = "xl/vbaProject.bin" in names
    workbook_content_type, overrides = parse_ooxml_workbook_type(content_types, workbook_xml)
    macro_container = workbook_content_type == XLSM_CONTENT_TYPE
    vba_override_value = overrides.get("xl/vbaProject.bin")
    if vba_override_value is not None and vba_override_value != VBA_CONTENT_TYPE:
        raise ValueError("VBA project has an invalid content type")
    has_vba_override = vba_override_value == VBA_CONTENT_TYPE
    has_vba_relationship = validate_vba_relationship(relationships_xml) if relationships_xml is not None else False
    if not (has_vba == has_vba_override == has_vba_relationship):
        raise ValueError("VBA binary, content type, and workbook relationship must be present together")
    if has_vba and not macro_container:
        raise ValueError("VBA project requires a macro-enabled workbook content type")
    expected = ".xlsm" if has_vba or macro_container else ".xlsx"
    if extension != expected:
        raise ValueError(f"extension/signature mismatch: detected {expected}, got {extension or '<none>'}")
    return {
        "format": "excel",
        "subtype": expected[1:],
        "detection": "ooxml-package",
        "engine": "excel-com-macro-safe" if has_vba or macro_container else "artifact-tool",
        "requires_conversion": False,
        "preserve_vba": has_vba or macro_container,
    }


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print(json.dumps({"error": "usage: route_excel_file.py <workbook>"}))
        return 2
    try:
        print(json.dumps(route(args[0]), ensure_ascii=False))
        return 0
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
