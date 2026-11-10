#!/usr/bin/env python3
"""Pair a source deck and its verified translation in presentation order."""

import argparse
import hashlib
from pathlib import Path
import posixpath
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from inspect_pptx_package import paragraph_text, relationship_targets


P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def signatures(path):
    with ZipFile(path) as package:
        presentation = ET.fromstring(package.read("ppt/presentation.xml"))
        rels = ET.fromstring(package.read("ppt/_rels/presentation.xml.rels"))
        targets = {entry.attrib["Id"]: entry.attrib["Target"] for entry in rels}
        image_hashes = {}
        for slide in presentation.find(P + "sldIdLst"):
            target = targets[slide.attrib[R + "id"]]
            part = posixpath.normpath(posixpath.join("ppt", target)).lstrip("/")
            node = ET.fromstring(package.read(part))
            text = tuple(paragraph_text(paragraph) for paragraph in node.iter(A + "p"))
            images = []
            image_targets = relationship_targets(package, part)
            for blip in node.iter(A + "blip"):
                media = image_targets.get(blip.get(R + "embed"))
                if media:
                    if media not in image_hashes:
                        image_hashes[media] = hashlib.sha256(package.read(media)).digest()
                    images.append(image_hashes[media])
            yield text, tuple(images)


def pair(source, translated, output):
    source, translated, output = (Path(p).resolve() for p in (source, translated, output))
    if any(p.suffix.lower() != ".pptx" for p in (source, translated, output)):
        raise ValueError("Pairing requires .pptx files. Use the prepared .pptx source for a legacy .ppt.")
    if len({source, translated, output}) != 3:
        raise ValueError("Choose three distinct paths for source, translation and paired candidate.")
    shell = shutil.which("powershell.exe")
    if not shell:
        raise RuntimeError("PowerPoint pairing requires Windows PowerShell and Microsoft PowerPoint.")
    left, right = list(signatures(source)), list(signatures(translated))
    if not left or len(left) != len(right):
        raise ValueError("Pairing requires equal, nonzero source and target slide counts.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ppt-pair-", dir=output.parent) as directory:
        candidate = Path(directory) / "paired.pptx"
        subprocess.run(
            [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
             str(Path(__file__).with_name("pair_slides.ps1")), "-SourcePath", str(source),
             "-TranslatedPath", str(translated), "-OutputPath", str(candidate)],
            check=True, timeout=180,
        )
        actual = list(signatures(candidate))
        expected = [slide for twins in zip(left, right) for slide in twins]
        if len(actual) != len(expected):
            raise ValueError("Paired candidate has an unexpected number of slides.")
        for index, (got, want) in enumerate(zip(actual, expected), 1):
            if got != want:
                raise ValueError(f"Paired candidate slide {index} differs in text or embedded picture bytes.")
        candidate.replace(output)
    return len(expected)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source")
    parser.add_argument("translated")
    parser.add_argument("output", help="Private paired .pptx candidate for visual review")
    args = parser.parse_args()
    print(f"Verified {pair(args.source, args.translated, args.output)} paired slides.")
