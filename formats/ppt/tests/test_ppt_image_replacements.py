from __future__ import annotations

from hashlib import sha256
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

from PIL import Image


SKILL_ROOT = Path(__file__).parents[1]
SCRIPT = SKILL_ROOT / "scripts" / "pptx_ooxml.py"
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
from ppt_image_replacements import (  # noqa: E402
    localized_parts,
    replacement_plan,
    verify_replacements,
)


SLIDE_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld><p:spTree>
    <p:pic>
      <p:nvPicPr><p:cNvPr id="3" name="Picture 1"/></p:nvPicPr>
      <p:blipFill><a:blip r:embed="rId2"
        xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>
        <a:stretch><a:fillRect/></a:stretch></p:blipFill>
      <p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="914400" cy="685800"/></a:xfrm></p:spPr>
    </p:pic>
    <p:sp>
      <p:nvSpPr><p:cNvPr id="2" name="TextBox 1"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
      <p:spPr/>
      <p:txBody><a:bodyPr/><a:lstStyle/><a:p>
        <a:r><a:rPr lang="zh-CN" sz="2400"/><a:t>梁式窑</a:t></a:r>
      </a:p></p:txBody>
    </p:sp>
  </p:spTree></p:cSld>
</p:sld>
""".encode("utf-8")

THEME = b"<theme>untouched</theme>"
RELATIONSHIPS = b"<Relationships>untouched</Relationships>"
SLIDE_ONE = b"<slide>one</slide>"


def png_bytes(size, color):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


class LocalizedImageReplacementTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.source = self.root / "source.pptx"
        self.output = self.root / "output.pptx"
        self.manifest_path = self.root / "manifest.json"
        self.media = png_bytes((32, 24), "white")
        with zipfile.ZipFile(self.source, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", "<Types/>")
            archive.writestr("ppt/slides/slide1.xml", SLIDE_XML)
            archive.writestr("ppt/slides/slide2.xml", SLIDE_ONE)
            archive.writestr("ppt/slides/_rels/slide1.xml.rels", RELATIONSHIPS)
            archive.writestr("ppt/theme/theme1.xml", THEME)
            archive.writestr("ppt/media/image1.png", self.media)

    def tearDown(self):
        self.temp_dir.cleanup()

    def localized_image(self, name="edited.png", size=(32, 24), color="navy"):
        path = self.root / name
        path.write_bytes(png_bytes(size, color))
        return path

    def write_manifest(self, group):
        self.manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "source_file": "source.pptx",
                    "source_path": str(self.source),
                    "source_sha256": "a" * 64,
                    "source_language": "zh-CN",
                    "target_language": "en",
                    "format": "powerpoint",
                    "occurrences": [
                        {
                            "id": "slide:1/shape:2/paragraph:1",
                            "slide_index": 1,
                            "shape_id": 2,
                            "paragraph_index": 1,
                            "kind": "ppt_paragraph",
                            "source_text": "梁式窑",
                            "translation_unit_id": "tu-beam",
                            "role": "body",
                            "context_signature": "body",
                            "protected_tokens": [],
                        }
                    ],
                    "translation_units": [
                        {
                            "id": "tu-beam",
                            "source_text": "梁式窑",
                            "translation": "Beam Lime Kiln",
                            "role": "body",
                            "context_signature": "body",
                            "protected_tokens": [],
                        }
                    ],
                    "image_groups": [group],
                    "preserved_parts": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def run_apply(self):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "apply", "--input", str(self.source),
             "--manifest", str(self.manifest_path), "--output", str(self.output)],
            capture_output=True, text=True, encoding="utf-8",
        )

    def group(self, replacement):
        return {
            "id": "f" * 64,
            "sha256": "f" * 64,
            "media_paths": ["ppt/media/image1.png"],
            "decision": "localized",
            "replacement_path": str(replacement),
            "replacement_sha256": sha256(replacement.read_bytes()).hexdigest(),
            "source_pixel_width": 32,
            "source_pixel_height": 24,
        }

    def test_swaps_the_media_part_and_leaves_every_other_part_untouched(self):
        replacement = self.localized_image()
        self.write_manifest(self.group(replacement))
        result = self.run_apply()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(1, json.loads(result.stdout)["image_replacements"])
        with zipfile.ZipFile(self.source) as before, zipfile.ZipFile(self.output) as after:
            self.assertEqual(before.namelist(), after.namelist())
            self.assertEqual(replacement.read_bytes(), after.read("ppt/media/image1.png"))
            for part in ("[Content_Types].xml", "ppt/slides/slide2.xml",
                         "ppt/slides/_rels/slide1.xml.rels", "ppt/theme/theme1.xml"):
                self.assertEqual(before.read(part), after.read(part))
            self.assertIn(b"Beam Lime Kiln", after.read("ppt/slides/slide1.xml"))
            # The picture shape keeps its extent and relationship.
            self.assertIn(b'r:embed="rId2"', after.read("ppt/slides/slide1.xml"))
            self.assertIn(b'cx="914400"', after.read("ppt/slides/slide1.xml"))

    def test_replacement_must_reproduce_the_source_pixel_dimensions(self):
        replacement = self.localized_image(name="small.png", size=(16, 12))
        self.write_manifest(self.group(replacement))
        result = self.run_apply()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must keep the source pixel dimensions", result.stderr)
        self.assertFalse(self.output.exists())

    def test_replacement_changed_after_review_is_rejected(self):
        replacement = self.localized_image()
        self.write_manifest(self.group(replacement))
        replacement.write_bytes(png_bytes((32, 24), "orange"))
        result = self.run_apply()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("changed after review", result.stderr)

    def test_a_media_part_claimed_twice_is_rejected(self):
        replacement = self.localized_image()
        group = self.group(replacement)
        self.write_manifest(group)
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["image_groups"].append({**group, "id": "e" * 64, "sha256": "e" * 64})
        self.manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "claimed twice"):
            replacement_plan(manifest)

    def test_verify_reports_a_replacement_that_never_reached_the_output(self):
        replacement = self.localized_image()
        group = self.group(replacement)
        self.write_manifest(group)
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual({"ppt/media/image1.png": group["replacement_sha256"]},
                         localized_parts(manifest))
        self.assertEqual(
            [{"code": "localized-image-changed", "part": "ppt/media/image1.png"}],
            verify_replacements(manifest, self.source),
        )
        with zipfile.ZipFile(self.output, "w") as archive:
            archive.writestr("ppt/media/image1.png", replacement.read_bytes())
        self.assertEqual([], verify_replacements(manifest, self.output))


if __name__ == "__main__":
    unittest.main()
