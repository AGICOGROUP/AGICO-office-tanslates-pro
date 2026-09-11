#!/usr/bin/env python3
"""Sparse XLSX text inspection and atomic preservation writer (no Office execution).

Only translated cells, their wrapping styles, and affected row heights are changed.
All other ZIP entries retain their original bytes. Rich run properties survive;
translated characters are distributed across the original runs proportionally.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import posixpath
import re
import sys
import tempfile
from zipfile import ZipFile

from lxml import etree as ET
from validate_manifest import technical_mismatch

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
Q = lambda name: f"{{{NS}}}{name}"


def xml(data):
    return ET.fromstring(data, ET.XMLParser(resolve_entities=False, no_network=True))


def serialize(root):
    return ET.tostring(root, encoding="UTF-8", xml_declaration=True)


def canonical(root):
    return ET.tostring(root, method="c14n")


def column_number(label):
    result = 0
    for char in label:
        result = result * 26 + ord(char.upper()) - 64
    return result


def coordinates(address):
    match = re.fullmatch(r"\$?([A-Za-z]{1,3})\$?(\d+)", address)
    if not match:
        raise ValueError(f"invalid cell address: {address}")
    return column_number(match[1]), int(match[2])


class Package:
    def __init__(self, path):
        self.path = Path(path)
        with ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ValueError("duplicate ZIP entries")
            self.data = {name: archive.read(name) for name in names}
        if (self.path.suffix.lower() == ".xlsm"
                or any(name.lower().endswith("vbaproject.bin") for name in names)
                or b"macroenabled" in self.data.get("[Content_Types].xml", b"").lower()
                or any(b"vbaproject" in data.lower() for name, data in self.data.items()
                       if name == "[Content_Types].xml" or name.endswith(".rels"))):
            raise ValueError("unsupported Excel workbook features: macro")
        workbook = xml(self.data["xl/workbook.xml"])
        if workbook.tag != Q("workbook"):
            raise ValueError("unsupported spreadsheet namespace")
        rels = xml(self.data["xl/_rels/workbook.xml.rels"])
        targets = {r.get("Id"): posixpath.normpath(posixpath.join("xl", r.get("Target", ""))).lstrip("/")
                   for r in rels if r.get("TargetMode") != "External"}
        self.shared = list(xml(self.data["xl/sharedStrings.xml"])) if "xl/sharedStrings.xml" in self.data else []
        self.styles = xml(self.data["xl/styles.xml"]) if "xl/styles.xml" in self.data else None
        self.sheets = []
        self.cells = {}
        self.formulas = []
        for sheet in workbook.findall(f"{Q('sheets')}/{Q('sheet')}"):
            part = targets.get(sheet.get(f"{{{REL}}}id"))
            if not part or part not in self.data:
                raise ValueError(f"missing worksheet: {sheet.get('name')}")
            root = xml(self.data[part])
            # Chartsheets remain opaque; their original package parts survive.
            if root.tag != Q("worksheet"):
                continue
            name = sheet.get("name")
            info = {"name": name, "part": part, "root": root, "visible": sheet.get("state", "visible") == "visible"}
            self.sheets.append(info)
            for cell in root.findall(f"{Q('sheetData')}/{Q('row')}/{Q('c')}"):
                key = (name, cell.get("r"))
                if key in self.cells:
                    raise ValueError(f"duplicate cell: {key}")
                self.cells[key] = cell
                formula = cell.find(Q("f"))
                if formula is not None:
                    self.formulas.append((name, formula.text or ""))
        # Defined names, validations and conditional formatting can also consume strings.
        self.formulas.extend((None, node.text or "") for node in workbook.findall(f"{Q('definedNames')}/{Q('definedName')}")
                             if node.get("name") not in {"_xlnm.Print_Area", "_xlnm.Print_Titles"})
        for sheet in self.sheets:
            for node in sheet["root"].iter():
                if isinstance(node.tag, str) and ET.QName(node).localname in {"formula", "formula1", "formula2"}:
                    self.formulas.append((sheet["name"], node.text or ""))

    def rich(self, cell):
        if cell.get("t") == "s":
            index = cell.findtext(Q("v"))
            return self.shared[int(index)]
        return cell.find(Q("is"))

    def text(self, cell):
        if cell.find(Q("f")) is not None:
            return None
        if cell.get("t") in {"s", "inlineStr"}:
            rich = self.rich(cell)
            if rich is None:
                return ""
            return "".join(node.text or "" for node in rich.findall(Q("t")) + rich.findall(f"{Q('r')}/{Q('t')}"))
        if cell.get("t") == "str":
            return cell.findtext(Q("v"), "")
        return None


def operational_cells(package):
    """Conservatively retain formula inputs without evaluating formulas or links."""
    texts = {key: package.text(cell) for key, cell in package.cells.items()}
    texts = {key: value for key, value in texts.items() if value is not None and value.strip()}
    literals = set()
    refs = set()
    ranges = []
    qualifier = r"(?:(?:'((?:[^']|'')+)'|([\w.]+))!)?"
    cell_ref = r"\$?[A-Z]{1,3}\$?\d+"
    reference = qualifier + rf"({cell_ref})(?::({cell_ref}))?"
    ref_pattern = re.compile(r"(?<![\w.])" + reference + r"(?![\w(])", re.I)
    whole_pattern = re.compile(r"(?<![\w.])" + qualifier + r"(\$?[A-Z]{1,3}:\$?[A-Z]{1,3}|\$?\d+:\$?\d+)(?![\w])", re.I)

    def unresolved(sheet, formula):
        raise ValueError(f"unresolved formula reference in {sheet or 'defined name'}: {formula}; "
                         "replace dynamic or unsupported references with explicit sheet-qualified A1 ranges before translation")

    formulas = list(package.formulas)
    shared = {}
    for (sheet, address), cell in package.cells.items():
        node = cell.find(Q("f"))
        if node is not None and node.get("t") == "shared" and node.text:
            shared[(sheet, node.get("si"))] = (address, node.text)
    for (sheet, address), cell in package.cells.items():
        node = cell.find(Q("f"))
        if node is None:
            continue
        if node.get("t") == "dataTable":
            unresolved(sheet, f"{address} (dataTable)")
        if node.get("t") == "shared" and not node.text:
            from openpyxl.formula.translate import Translator
            master = shared.get((sheet, node.get("si")))
            if master is None:
                unresolved(sheet, f"{address} (missing shared formula master)")
            try:
                formulas.append((sheet, Translator("=" + master[1], origin=master[0]).translate_formula(address)[1:]))
            except Exception as exc:
                raise ValueError(f"unresolved formula reference in {sheet}!{address}: shared formula expansion failed") from exc

    for current_sheet, formula in formulas:
        for match in re.finditer(r'"((?:""|[^"])*)"', formula):
            literals.add(re.sub(r"^[<>=]+", "", match[1].replace('""', '"')))
        # Tokenization keeps function-like text inside string literals opaque.
        if re.search(r"\b(?:INDIRECT|OFFSET)\s*\(", formula, re.I):
            from openpyxl.formula import Tokenizer
            from openpyxl.utils.cell import get_column_letter

            tokens = [t for t in Tokenizer("=" + formula.lstrip("=")).items if t.type != "WHITE-SPACE"]
            for i in range(len(tokens) - 1, -1, -1):
                token = tokens[i]
                if token.type != "FUNC" or token.subtype != "OPEN":
                    continue
                function = token.value[:-1].upper()
                if function not in {"INDIRECT", "OFFSET"}:
                    continue
                end = i + 1
                while end < len(tokens) and not (tokens[end].type == "FUNC" and tokens[end].subtype == "CLOSE"):
                    end += 1
                values = [t.value for t in tokens[i + 1:end]]
                args = "".join(values).split(",")
                resolved = None
                if function == "INDIRECT":
                    # Only a literal address and optional A1 mode are statically known.
                    argument = re.fullmatch(r'("(?:""|[^"])*")(?:,(?:TRUE|1))?', "".join(values), re.I)
                    if argument:
                        resolved = argument[1][1:-1].replace('""', '"')
                        if not (re.fullmatch(reference, resolved, re.I) or whole_pattern.fullmatch(resolved)):
                            resolved = None
                elif function == "OFFSET" and 3 <= len(args) <= 5:
                    base = re.fullmatch(reference, args[0], re.I)
                    if base and all(re.fullmatch(r"[+-]?\d+", arg) for arg in args[1:]):
                        a, b = coordinates(base[3]), coordinates(base[4] or base[3])
                        col, row = a[0] + int(args[2]), a[1] + int(args[1])
                        height = int(args[3]) if len(args) >= 4 else b[1] - a[1] + 1
                        width = int(args[4]) if len(args) == 5 else b[0] - a[0] + 1
                        if min(col, row, height, width) > 0 and col + width - 1 <= 16384 and row + height - 1 <= 1048576:
                            prefix = args[0][:base.start(3)]
                            target = f"{prefix}{get_column_letter(col)}{row}:{get_column_letter(col + width - 1)}{row + height - 1}"
                            resolved = f"({args[0]},{target})"
                if resolved is None or end == len(tokens):
                    unresolved(current_sheet, formula)
                token.value = resolved
                token.type, token.subtype = "OPERAND", "RANGE"
                del tokens[i + 1:end + 1]
            formula = "".join(t.value for t in tokens)
        clean = re.sub(r'"(?:""|[^"])*"', '""', formula)
        if "[" in clean or re.search(r"\b(?:INDIRECT|OFFSET)\s*\(", clean, re.I):
            unresolved(current_sheet, formula)
        for match in whole_pattern.finditer(clean):
            sheet = match[1] or match[2] or current_sheet
            if sheet is None:
                unresolved(current_sheet, formula)
            a, b = match[3].replace("$", "").split(":")
            bounds = ((column_number(a), 1), (column_number(b), 1048576)) if a.isalpha() else ((1, int(a)), (16384, int(b)))
            ranges.append((sheet.replace("''", "'").casefold(), *bounds))
        for match in ref_pattern.finditer(clean):
            sheet = (match[1] or match[2] or current_sheet)
            if sheet is None:
                unresolved(current_sheet, formula)
            sheet = sheet.replace("''", "'")
            if match[4]:
                ranges.append((sheet.casefold(), coordinates(match[3]), coordinates(match[4])))
            else:
                refs.add((sheet.casefold(), match[3].replace("$", "").upper()))
    patterns = []
    for literal in literals:
        tokens = re.findall(r"~[~*?]|.", literal, flags=re.S)
        pattern = "".join(re.escape(t[1]) if t.startswith("~") and len(t) == 2 else
                          ".*" if t == "*" else "." if t == "?" else re.escape(t) for t in tokens)
        patterns.append(re.compile(f"^{pattern}$", re.I | re.S))
    result = set()
    for key, value in texts.items():
        sheet, address = key
        col, row = coordinates(address)
        if ((sheet.casefold(), address) in refs
                or any(s == sheet.casefold() and min(a[0], b[0]) <= col <= max(a[0], b[0])
                       and min(a[1], b[1]) <= row <= max(a[1], b[1]) for s, a, b in ranges)
                or any(pattern.fullmatch(value) for pattern in patterns)):
            result.add(key)
    return result


def preservation_warnings(package):
    prefixes = ("xl/charts/", "xl/comments", "xl/threadedComments/", "xl/drawings/", "xl/externalLinks/", "xl/tables/", "customXml/")
    warnings = [f"Preserved without translating complex content: {name}" for name in package.data
                if name.startswith(prefixes) and name.endswith(".xml")]
    for sheet in package.sheets:
        if any(isinstance(node.tag, str) and ET.QName(node).localname in {"oddHeader", "oddFooter", "evenHeader", "evenFooter", "firstHeader", "firstFooter"}
               and (node.text or "").strip() for node in sheet["root"].iter()):
            warnings.append(f"Preserved without translating header/footer: {sheet['part']}")
    return warnings


def inspect(source):
    package = Package(source)
    operational = operational_cells(package)
    occurrences = []
    sheets = []
    for sheet in package.sheets:
        prior = {}
        cells = [(key, cell) for key, cell in package.cells.items() if key[0] == sheet["name"]]
        cells.sort(key=lambda item: coordinates(item[0][1])[::-1])
        for (name, address), cell in cells:
            text = package.text(cell)
            if text is None or not text.strip():
                continue
            col, _ = coordinates(address)
            occurrences.append({"id": f"{name}!{address}", "kind": "cell", "sheet": name,
                                "address": address, "source": text, "formula_dependency": (name, address) in operational,
                                "context_key": f"cell:column:{prior[col]}" if col in prior else "unknown"})
            prior[col] = text.strip()
        sheets.append({"name": sheet["name"], "visible": sheet["visible"], "used": bool(cells),
                       "range": sheet["root"].find(Q("dimension")).get("ref") if sheet["root"].find(Q("dimension")) is not None else None})
    external_data = (any(name.startswith("xl/externalLinks/") or name in {"xl/connections.xml"}
                         or name.startswith("xl/queryTables/") for name in package.data)
                     or any(re.search(r"\b(?:WEBSERVICE|RTD|DDE)\s*\(|\[[^\]]+\][^!]*!", formula, re.I) for _, formula in package.formulas)
                     or any(b"externallink" in data.lower() for name, data in package.data.items() if name.endswith(".rels")))
    warnings = preservation_warnings(package)
    if operational:
        examples = ", ".join(f"{sheet}!{address}" for sheet, address in sorted(operational)[:8])
        warnings.append(f"Formula input text retained without translation: {len(operational)} cells; examples: {examples}")
    if external_data:
        warnings.append("External data preserved without refresh; Excel recalculation must be skipped")
    return {"sheets": sheets, "occurrences": occurrences, "warnings": warnings, "external_data": external_data}


def decisions(package, manifest):
    units = {unit["id"]: unit for unit in manifest.get("translation_units", [])}
    if len(units) != len(manifest.get("translation_units", [])):
        raise ValueError("duplicate translation units")
    expected = {}
    operational = operational_cells(package)
    for occurrence in manifest.get("occurrences", []):
        if occurrence.get("kind", "cell") != "cell":
            raise ValueError("unsupported occurrence kind")
        key = (occurrence["sheet"], occurrence["address"])
        cell = package.cells.get(key)
        if cell is None or key in expected:
            raise ValueError(f"missing or duplicate source cell: {key}")
        source = package.text(cell)
        if source != occurrence.get("original_source", occurrence["source"]):
            raise ValueError(f"source text mismatch: {key}")
        unit = units[occurrence["translation_unit_id"]]
        target = unit.get("translation")
        if unit.get("status") not in {"translated", "retain"} or not isinstance(target, str) or not target.strip():
            raise ValueError(f"pending translation: {key}")
        template = occurrence.get("translation_template")
        if template:
            target += template["separator"] + template["suffix"]
        if key in operational and target != source:
            raise ValueError(f"formula-dependent text must be retained: {key}")
        if unit.get("status") == "retain" and target != source:
            raise ValueError(f"retained text changed: {key}")
        tokens = occurrence.get("original_protected_tokens", unit.get("protected_tokens", []))
        if technical_mismatch(source, target, tokens):
            raise ValueError(f"protected-token-change: {key}")
        expected[key] = target
    missing = [key for key, cell in package.cells.items() if (package.text(cell) or "").strip() and key not in expected]
    if missing:
        raise ValueError(f"manifest coverage missing cells: {missing[:10]}")
    return expected


def replace_text(package, cell, target):
    rich = package.rich(cell)
    inline = deepcopy(rich) if rich is not None else ET.Element(Q("is"))
    inline.tag = Q("is")
    # Phonetic guides index source characters and cannot survive translated text.
    for node in list(inline):
        if node.tag in {Q("rPh"), Q("phoneticPr")}:
            inline.remove(node)
    runs = inline.findall(Q("r"))
    if runs:
        texts = []
        for run in runs:
            node = run.find(Q("t"))
            if node is None:
                node = ET.SubElement(run, Q("t"))
            texts.append(node)
        total = sum(len(node.text or "") for node in texts) or len(texts)
        position = cumulative = 0
        for index, node in enumerate(texts):
            cumulative += len(node.text or "") or (1 if total == len(texts) else 0)
            end = len(target) if index == len(texts) - 1 else round(len(target) * cumulative / total)
            node.text = target[position:end]
            node.set(XML_SPACE, "preserve")
            position = end
    else:
        node = inline.find(Q("t"))
        if node is None:
            node = ET.SubElement(inline, Q("t"))
        node.text = target
        node.set(XML_SPACE, "preserve")
    for node in list(cell):
        if node.tag in {Q("v"), Q("is")}:
            cell.remove(node)
    cell.set("t", "inlineStr")
    cell.insert(0, inline)


def wrapped_lines(text, width):
    capacity = max(6, int(width * 1.15))
    def weight(word):
        return sum(1 if ord(c) < 128 else 2 for c in word)
    total = 0
    for line in text.split("\n"):
        used, count = 0, 1
        for word in line.split():
            size = weight(word)
            if used and used + 1 + size > capacity:
                count += 1
                used = 0
            if used:
                used += 1
            count += max(0, math.ceil(size / capacity) - 1)
            used += size % capacity or min(size, capacity)
        total += count
    return total


def layout_geometry(root, address):
    col, row = coordinates(address)
    defaults = root.find(Q("sheetFormatPr"))
    default_width = float(defaults.get("defaultColWidth", "8.43")) if defaults is not None else 8.43
    columns = root.findall(f"{Q('cols')}/{Q('col')}")
    start = end = col
    vertical = False
    for node in root.findall(f"{Q('mergeCells')}/{Q('mergeCell')}"):
        a, b = [coordinates(value) for value in node.get("ref").split(":")]
        if a[0] <= col <= b[0] and a[1] <= row <= b[1]:
            start, end, vertical = a[0], b[0], a[1] != b[1]
            break
    width = sum(next((float(c.get("width", str(default_width))) for c in columns
                      if int(c.get("min")) <= n <= int(c.get("max"))), default_width)
                for n in range(start, end + 1))
    return width, vertical


def expand_layout(package, changes):
    expanded = set()
    styles_changed = False
    clones = {}
    for sheet in package.sheets:
        root = sheet["root"]
        columns = root.findall(f"{Q('cols')}/{Q('col')}")
        merges = [node.get("ref") for node in root.findall(f"{Q('mergeCells')}/{Q('mergeCell')}")]
        defaults = root.find(Q("sheetFormatPr"))
        default_height = float(defaults.get("defaultRowHeight", "15")) if defaults is not None else 15
        default_width = float(defaults.get("defaultColWidth", "8.43")) if defaults is not None else 8.43
        rows = {int(row.get("r")): row for row in root.findall(f"{Q('sheetData')}/{Q('row')}")}
        for (name, address), target in changes.items():
            if name != sheet["name"]:
                continue
            col, row_number = coordinates(address)
            start = end = col
            vertical = False
            for merge in merges:
                a, b = [coordinates(v) for v in merge.split(":")]
                if a[0] <= col <= b[0] and a[1] <= row_number <= b[1]:
                    start, end, vertical = a[0], b[0], a[1] != b[1]
                    break
            row = rows[row_number]
            if vertical or row.get("hidden") == "1":
                continue
            width = sum(next((float(c.get("width", str(default_width))) for c in columns
                              if int(c.get("min")) <= n <= int(c.get("max"))), default_width)
                        for n in range(start, end + 1))
            lines = wrapped_lines(target, width)
            if lines <= 1:
                continue
            current = float(row.get("ht", str(default_height)))
            needed = min(409.5, lines * 15 + 3)
            if needed > current:
                row.set("ht", str(needed))
                row.set("customHeight", "1")
                expanded.add((name, row_number))
            cell = package.cells[(name, address)]
            xfs = package.styles.find(Q("cellXfs")) if package.styles is not None else None
            if xfs is None:
                continue
            style = int(cell.get("s", "0"))
            xf = xfs[style]
            align = xf.find(Q("alignment"))
            if align is not None and align.get("wrapText") in {"1", "true"}:
                continue
            if style not in clones:
                clone = deepcopy(xf)
                alignment = clone.find(Q("alignment"))
                if alignment is None:
                    alignment = ET.Element(Q("alignment"))
                    # alignment precedes protection/extLst in CT_Xf.
                    clone.insert(next((i for i, n in enumerate(clone) if n.tag in {Q("protection"), Q("extLst")}), len(clone)), alignment)
                alignment.set("wrapText", "1")
                clone.set("applyAlignment", "1")
                clones[style] = len(xfs)
                xfs.append(clone)
                xfs.set("count", str(len(xfs)))
                styles_changed = True
            cell.set("s", str(clones[style]))
    return expanded, styles_changed


def verify(source, output, manifest):
    before, after = Package(source), Package(output)
    expected = decisions(before, manifest)
    changed = {key for key, target in expected.items() if before.text(before.cells[key]) != target}
    errors = []
    if before.data.keys() != after.data.keys():
        errors.append("package-parts-change")
    if set(before.cells) != set(after.cells):
        errors.append("cell-structure-change")
    allowed_parts = {s["part"] for s in before.sheets if any(key[0] == s["name"] for key in changed)}
    if changed:
        allowed_parts.add("xl/styles.xml")
    localized = {item["sha256"]: item.get("replacement_sha256") for item in manifest.get("images", []) if item.get("status") == "localized"}
    for part, data in before.data.items():
        actual = after.data.get(part)
        if part in allowed_parts:
            continue
        replacement = localized.get(hashlib.sha256(data).hexdigest()) if part.startswith("xl/media/") else None
        if replacement:
            if actual is None or hashlib.sha256(actual).hexdigest() != replacement:
                errors.append(f"image-change:{part}")
        elif actual != data:
            errors.append(f"untouched-part-change:{part}")
    for key, cell in before.cells.items():
        actual = after.cells.get(key)
        if actual is None:
            errors.append(f"missing-cell:{key}")
            continue
        formula = cell.find(Q("f"))
        out_formula = actual.find(Q("f"))
        if formula is not None and (out_formula is None or canonical(formula) != canonical(out_formula)):
            errors.append(f"formula-change:{key[0]}!{key[1]}")
        if before.text(cell) is None and canonical(cell) != canonical(actual):
            errors.append(f"non-text-change:{key[0]}!{key[1]}")
        if key in expected and after.text(actual) != expected[key]:
            errors.append(f"missing-translation:{key[0]}!{key[1]}")
        if key not in changed and canonical(cell) != canonical(actual):
            errors.append(f"untouched-cell-change:{key}")
        if key in changed:
            source_rich, output_rich = before.rich(cell), after.rich(actual)
            source_runs = source_rich.findall(Q("r")) if source_rich is not None else []
            output_runs = output_rich.findall(Q("r")) if output_rich is not None else []
            def semantic_properties(node):
                if node is None:
                    return None
                return (
                    node.tag,
                    tuple(sorted(node.attrib.items())),
                    node.text,
                    tuple(semantic_properties(child) for child in node),
                )
            def run_properties(runs):
                return [semantic_properties(r.find(Q("rPr"))) for r in runs]
            if run_properties(source_runs) != run_properties(output_runs):
                errors.append(f"rich-format-change:{key[0]}!{key[1]}")
            if before.styles is not None and after.styles is not None:
                source_xfs, output_xfs = before.styles.find(Q("cellXfs")), after.styles.find(Q("cellXfs"))
                if source_xfs is not None and output_xfs is not None:
                    source_style, output_style = int(cell.get("s", "0")), int(actual.get("s", "0"))
                    if output_style >= len(output_xfs):
                        errors.append(f"style-change:missing-style:{key}")
                    else:
                        a, b = deepcopy(source_xfs[source_style]), deepcopy(output_xfs[output_style])
                        align = b.find(Q("alignment"))
                        root = next(s["root"] for s in before.sheets if s["name"] == key[0])
                        width, vertical = layout_geometry(root, key[1])
                        row = cell.getparent()
                        if not vertical and row.get("hidden") != "1" and wrapped_lines(expected[key], width) > 1:
                            if align is None or align.get("wrapText") not in {"1", "true"}:
                                errors.append(f"style-change:missing-wrap:{key}")
                        for style in (a, b):
                            style.attrib.pop("applyAlignment", None)
                            alignment = style.find(Q("alignment"))
                            if alignment is not None:
                                alignment.attrib.pop("wrapText", None)
                                if not len(alignment) and not alignment.attrib:
                                    style.remove(alignment)
                        if canonical(a) != canonical(b):
                            errors.append(f"style-change:cell-format:{key}")
    # Independently compare structural XML after masking permitted text/style/row edits.
    out_sheets = {s["name"]: s for s in after.sheets}
    changed_rows = {(name, coordinates(address)[1]) for name, address in changed}
    for sheet in before.sheets:
        other = out_sheets.get(sheet["name"])
        if other is None:
            errors.append(f"missing-sheet:{sheet['name']}")
            continue
        a, b = deepcopy(sheet["root"]), deepcopy(other["root"])
        source_merges = [node.get("ref") for node in a.findall(f"{Q('mergeCells')}/{Q('mergeCell')}")]
        output_merges = [node.get("ref") for node in b.findall(f"{Q('mergeCells')}/{Q('mergeCell')}")]
        if source_merges != output_merges:
            errors.append(f"merge-change:{sheet['name']}")
        for root in (a, b):
            for row in root.findall(f"{Q('sheetData')}/{Q('row')}"):
                if (sheet["name"], int(row.get("r"))) in changed_rows:
                    for attribute in ("ht", "customHeight"):
                        row.attrib.pop(attribute, None)
                for cell in row.findall(Q("c")):
                    if (sheet["name"], cell.get("r")) in changed:
                        for child in list(cell):
                            if child.tag in {Q("is"), Q("v")}:
                                cell.remove(child)
                        for attribute in ("t", "s"):
                            cell.attrib.pop(attribute, None)
        if canonical(a) != canonical(b):
            errors.append(f"structure-change:{sheet['part']}")
    if before.styles is not None and after.styles is not None:
        a, b = deepcopy(before.styles), deepcopy(after.styles)
        x, y = a.find(Q("cellXfs")), b.find(Q("cellXfs"))
        if x is not None and y is not None:
            original_count = len(x)
            for extra in list(y)[original_count:]:
                candidate = deepcopy(extra)
                candidate.attrib.pop("applyAlignment", None)
                align = candidate.find(Q("alignment"))
                if align is None or align.get("wrapText") != "1":
                    errors.append("style-change:invalid-wrap-clone")
                else:
                    align.attrib.pop("wrapText", None)
                    if not len(align) and not align.attrib:
                        candidate.remove(align)
                valid = False
                for original in x:
                    compare = deepcopy(original)
                    compare.attrib.pop("applyAlignment", None)
                    alignment = compare.find(Q("alignment"))
                    if alignment is not None:
                        alignment.attrib.pop("wrapText", None)
                        if not len(alignment) and not alignment.attrib:
                            compare.remove(alignment)
                    valid |= canonical(candidate) == canonical(compare)
                if not valid:
                    errors.append("style-change:unrelated-style")
                y.remove(extra)
            y.set("count", x.get("count", str(original_count)))
        if canonical(a) != canonical(b):
            errors.append("style-change:original-styles")
    elif before.data.get("xl/styles.xml") != after.data.get("xl/styles.xml"):
        errors.append("style-change:missing-styles")
    return {"passed": not errors, "errors": sorted(set(errors)), "warnings": preservation_warnings(before),
            "checked_cells": len(before.cells), "preserved_parts": len(before.data) - len(allowed_parts)}


def apply(source, output, manifest):
    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output:
        raise ValueError("output must not overwrite source")
    package = Package(source)
    expected = decisions(package, manifest)
    changes = {key: target for key, target in expected.items() if package.text(package.cells[key]) != target}
    for key, target in changes.items():
        replace_text(package, package.cells[key], target)
    expanded, styles_changed = expand_layout(package, changes)
    changed_sheets = {key[0] for key in changes}
    patches = {s["part"]: serialize(s["root"]) for s in package.sheets if s["name"] in changed_sheets}
    if styles_changed:
        patches["xl/styles.xml"] = serialize(package.styles)
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".excel-native-", suffix=output.suffix, dir=output.parent)
    os.close(descriptor)
    temporary = Path(name)
    try:
        with ZipFile(source) as original, ZipFile(temporary, "w") as translated:
            translated.comment = original.comment
            for entry in original.infolist():
                translated.writestr(entry, patches.get(entry.filename, package.data[entry.filename]))
        if any(item.get("status") == "localized" for item in manifest.get("images", [])):
            from inspect_excel_package import apply_image_replacements
            apply_image_replacements(temporary, manifest)
        # Verify before replacement: prior good output survives any detected damage.
        report = verify(source, temporary, manifest)
        if not report["passed"]:
            raise ValueError(f"native write verification failed: {report['errors']}")
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return {"changed_sheets": sorted(changed_sheets), "expandedRows": len(expanded), "compressedRows": 0,
            "warnings": preservation_warnings(package)}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inspect", "apply", "verify"))
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "inspect":
            report = inspect(args.source)
        else:
            if args.output is None or args.manifest is None:
                raise ValueError("apply/verify require --output and --manifest")
            manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
            report = (apply if args.action == "apply" else verify)(args.source, args.output, manifest)
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report.get("passed", True) else 2
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
