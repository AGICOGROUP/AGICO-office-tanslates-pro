"""Replace GPT-localized PowerPoint pictures by rewriting their media parts.

A PowerPoint picture shape owns its geometry (``a:xfrm`` extent, ``a:srcRect``
crop, rotation, group membership) independently of the media part it points at.
Because a localized replacement is fitted to the source image's exact pixel
dimensions (see ``normalize_generated_image.fit``), the recorded extent and crop
stay correct when the referenced ``ppt/media/*`` bytes are swapped, so the shape
is left untouched and only the picture content changes.

Every other package part, relationship, content type and slide XML is copied
byte-for-byte, and the rewrite is atomic: the previous output survives a failed
write.
"""
from __future__ import annotations

import hashlib
import io
from pathlib import Path
import sys
from zipfile import ZipFile

from PIL import Image

REPOSITORY_SCRIPTS = str(Path(__file__).resolve().parents[3] / "scripts")
if REPOSITORY_SCRIPTS not in sys.path:
    sys.path.append(REPOSITORY_SCRIPTS)

from translation_core import file_hash

MEDIA_PREFIX = "ppt/media/"


def _label(group: dict) -> str:
    return str(group.get("id") or group.get("sha256") or "<unknown>")


def replacement_plan(manifest: dict) -> dict[str, tuple[str, Path]]:
    """Map each localized media part to its verified replacement file.

    Raises ``RuntimeError`` when a declared replacement is missing, changed
    after review, ambiguous, or stored in a format the part cannot host.
    """
    plan: dict[str, tuple[str, Path]] = {}
    for group in manifest.get("image_groups", []):
        if group.get("decision") != "localized":
            continue
        label = _label(group)
        replacement = Path(str(group.get("replacement_path", "")))
        if not replacement.is_absolute() or not replacement.is_file():
            raise RuntimeError(f"localized image is missing: {label}")
        if file_hash(replacement) != group.get("replacement_sha256"):
            raise RuntimeError(f"localized image changed after review: {label}")
        parts = [str(item) for item in group.get("media_paths") or []]
        if not parts:
            raise RuntimeError(f"localized image has no package media part: {label}")
        for part in parts:
            if not part.startswith(MEDIA_PREFIX):
                raise RuntimeError(f"localized image part is outside the media folder: {part}")
            if Path(part).suffix.lower() != replacement.suffix.lower():
                raise RuntimeError(
                    f"replacement format differs from {part}; update the package content types first"
                )
            if part in plan:
                raise RuntimeError(f"localized media part is claimed twice: {part}")
            plan[part] = (label, replacement)
    return plan


def localized_parts(manifest: dict) -> dict[str, str]:
    """Map each localized media part to the expected sha256 of its new bytes."""
    return {part: file_hash(path) for part, (_label, path) in replacement_plan(manifest).items()}


def image_size(payload: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(payload)) as image:
        return image.size


def replacement_payloads(manifest: dict, source_package: ZipFile) -> dict[str, bytes]:
    """Verified replacement bytes keyed by package part.

    The replacement must reproduce the source picture's exact pixel dimensions,
    otherwise the picture shape would stretch or crop differently and the
    recorded geometry would no longer describe the rendered result.
    """
    payloads: dict[str, bytes] = {}
    for part, (label, replacement) in replacement_plan(manifest).items():
        try:
            source_payload = source_package.read(part)
        except KeyError as exc:
            raise RuntimeError(f"localized image part is absent from the package: {part}") from exc
        payload = replacement.read_bytes()
        source_size = image_size(source_payload)
        if image_size(payload) != source_size:
            raise RuntimeError(
                f"localized image {label} must keep the source pixel dimensions of {part}: "
                f"{image_size(payload)} != {source_size}"
            )
        payloads[part] = payload
    return payloads


def verify_replacements(manifest: dict, output_path: Path) -> list[dict]:
    """Confirm every declared replacement is present in the output byte-for-byte."""
    try:
        expected = localized_parts(manifest)
    except RuntimeError as exc:
        return [{"code": "localized-image-invalid", "message": str(exc)}]
    if not expected:
        return []
    errors: list[dict] = []
    with ZipFile(output_path) as archive:
        names = set(archive.namelist())
        for part, digest in expected.items():
            if part not in names:
                errors.append({"code": "localized-image-missing", "part": part})
                continue
            if hashlib.sha256(archive.read(part)).hexdigest() != digest:
                errors.append({"code": "localized-image-changed", "part": part})
    return errors
