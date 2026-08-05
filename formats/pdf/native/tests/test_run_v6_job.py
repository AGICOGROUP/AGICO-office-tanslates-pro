from __future__ import annotations

import json
import hashlib
import subprocess
import sys
import tempfile
import unittest
import io
from pathlib import Path

from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont


RUNNER = Path(__file__).resolve().parents[1] / "scripts" / "run_v6_job.py"


def make_pdf(path: Path) -> None:
    pdf = canvas.Canvas(str(path), pagesize=(200, 200))
    pdf.drawString(20, 150, "Test")
    image = Image.new("RGB", (8, 8), (0, 90, 200))
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    pdf.drawImage(ImageReader(io.BytesIO(stream.getvalue())), 20, 30, 40, 40)
    pdf.save()


def run(*args: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RUNNER), *(str(value) for value in args)],
        capture_output=True,
        text=True,
    )


def prepare_annotation_job(root: Path) -> tuple[Path, str]:
    source = root / "source.pdf"
    make_pdf(source)
    initialized = run("init", source, "--jobs-root", root / "jobs")
    job_dir = Path(json.loads(initialized.stdout)["job_dir"])
    job_path = job_dir / "job.json"
    job = json.loads(job_path.read_text(encoding="utf-8"))
    job["stage"] = "native_translated"
    native_pdf = job_dir / "translated-native.pdf"
    make_pdf(native_pdf)
    job["artifacts"]["native_pdf"] = {
        "path": str(native_pdf.resolve()),
        "sha256": hashlib.sha256(native_pdf.read_bytes()).hexdigest(),
    }
    job_path.write_text(json.dumps(job), encoding="utf-8")
    inventory = json.loads(
        (job_dir / "images" / "image-inventory.json").read_text(encoding="utf-8")
    )
    return job_dir, inventory["images"][0]["id"]


def routed_review(image_id: str, method: str = "deterministic_cleanup") -> dict:
    return {
        "complete": True,
        "reviewed_image_ids": [image_id],
        "images": [
            {
                "id": image_id,
                "asset_type": "raster_simple",
                "method": method,
                "expected_label_count": 1,
                "translated_label_count": 1,
                "preserved_label_count": 0,
                "confirm_count": 0,
                "structural_review_complete": True,
                "labels": [
                    {
                        "id": "label-1",
                        "source_text": "烟囱",
                        "translation": "Chimney",
                        "ocr_confidence": "high",
                        "method": method,
                        "status": "translated",
                    }
                ],
            }
        ],
        "confirm_items": [],
    }


class RunV6JobTests(unittest.TestCase):
    def test_init_creates_source_bound_job_and_resume_requests_translation(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "source.pdf"
            make_pdf(source)
            result = run("init", source, "--jobs-root", root / "jobs")
            self.assertEqual(result.returncode, 0, result.stderr)
            job_dir = Path(json.loads(result.stdout)["job_dir"])
            job = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
            self.assertIn("manifest", job["artifacts"])
            self.assertIn("image_inventory", job["artifacts"])
            resumed = run("resume", job_dir)
            self.assertEqual(resumed.returncode, 2)
            # The fixture contains target-language text only, so no translation
            # round trip is needed.
            self.assertEqual(json.loads(resumed.stdout)["action"], "build_native")

    def test_assemble_rejects_skipped_stages(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "source.pdf"
            make_pdf(source)
            initialized = run("init", source, "--jobs-root", root / "jobs")
            job_dir = Path(json.loads(initialized.stdout)["job_dir"])
            result = run("assemble", job_dir)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("images_cleaned", result.stderr)

    def test_verify_rejects_extractable_cjk(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "source.pdf"
            make_pdf(source)
            initialized = run("init", source, "--jobs-root", root / "jobs")
            job_dir = Path(json.loads(initialized.stdout)["job_dir"])
            candidate = job_dir / "candidate.pdf"
            pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
            pdf = canvas.Canvas(str(candidate), pagesize=(200, 200))
            pdf.setFont("STSong-Light", 12)
            pdf.drawString(20, 150, "中文残留")
            pdf.save()
            digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
            job_path = job_dir / "job.json"
            job = json.loads(job_path.read_text(encoding="utf-8"))
            job["stage"] = "assembled"
            job["artifacts"]["candidate_pdf"] = {
                "path": str(candidate.resolve()),
                "sha256": digest,
            }
            job_path.write_text(
                json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            result = run("verify", job_dir, "--visual-review-complete")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("extractable CJK", result.stderr)

    def test_image_annotation_requires_review_of_every_original_image(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "source.pdf"
            make_pdf(source)
            initialized = run("init", source, "--jobs-root", root / "jobs")
            job_dir = Path(json.loads(initialized.stdout)["job_dir"])
            job_path = job_dir / "job.json"
            job = json.loads(job_path.read_text(encoding="utf-8"))
            job["stage"] = "native_translated"
            job_path.write_text(json.dumps(job), encoding="utf-8")
            metadata = root / "metadata.json"
            review = root / "review.json"
            metadata.write_text('{"images": []}', encoding="utf-8")
            review.write_text(
                '{"complete": true, "reviewed_image_ids": []}',
                encoding="utf-8",
            )
            result = run(
                "annotate-images",
                job_dir,
                "--metadata",
                metadata,
                "--review",
                review,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unreviewed original images", result.stderr)

    def test_verify_rejects_logo_footer_overlap_or_unreviewed_images(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "source.pdf"
            make_pdf(source)
            initialized = run("init", source, "--jobs-root", root / "jobs")
            job_dir = Path(json.loads(initialized.stdout)["job_dir"])
            candidate = job_dir / "candidate.pdf"
            make_pdf(candidate)
            digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
            job_path = job_dir / "job.json"
            job = json.loads(job_path.read_text(encoding="utf-8"))
            job["stage"] = "assembled"
            job["artifacts"]["candidate_pdf"] = {
                "path": str(candidate.resolve()),
                "sha256": digest,
            }
            job_path.write_text(json.dumps(job), encoding="utf-8")
            report = root / "visual-review.json"
            report.write_text(
                json.dumps(
                    {
                        "all_pages_rendered": True,
                        "unreviewed_images": 1,
                        "untranslated_clear_image_labels": 1,
                        "logo_review_complete": False,
                        "header_footer_high_resolution_review_complete": False,
                        "text_overlap_failures": [{"page": 1, "region": "footer"}],
                    }
                ),
                encoding="utf-8",
            )
            result = run(
                "verify",
                job_dir,
                "--visual-review-report",
                report,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("visual delivery gates failed", result.stderr)

    def test_image_annotation_rejects_unknown_localization_method(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            job_dir, image_id = prepare_annotation_job(root)
            metadata = root / "metadata.json"
            review = root / "review.json"
            metadata.write_text(
                json.dumps({"images": [{"id": image_id, "regions": []}]}),
                encoding="utf-8",
            )
            review.write_text(
                json.dumps(routed_review(image_id, "uncontrolled_redraw")),
                encoding="utf-8",
            )

            result = run(
                "annotate-images", job_dir, "--metadata", metadata, "--review", review
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsupported image localization method", result.stderr)

    def test_image_annotation_rejects_incomplete_label_coverage(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            job_dir, image_id = prepare_annotation_job(root)
            metadata = root / "metadata.json"
            review = root / "review.json"
            metadata.write_text(
                json.dumps({"images": [{"id": image_id, "regions": []}]}),
                encoding="utf-8",
            )
            payload = routed_review(image_id)
            payload["images"][0]["expected_label_count"] = 2
            review.write_text(json.dumps(payload), encoding="utf-8")

            result = run(
                "annotate-images", job_dir, "--metadata", metadata, "--review", review
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("image label coverage mismatch", result.stderr)

    def test_image_annotation_requires_reported_confirm_item(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            job_dir, image_id = prepare_annotation_job(root)
            metadata = root / "metadata.json"
            review = root / "review.json"
            metadata.write_text(
                json.dumps({"images": [{"id": image_id, "regions": []}]}),
                encoding="utf-8",
            )
            payload = routed_review(image_id, "preserve_confirm")
            image = payload["images"][0]
            image["translated_label_count"] = 0
            image["preserved_label_count"] = 1
            image["confirm_count"] = 1
            image["labels"][0]["translation"] = ""
            image["labels"][0]["status"] = "confirm"
            review.write_text(json.dumps(payload), encoding="utf-8")

            result = run(
                "annotate-images", job_dir, "--metadata", metadata, "--review", review
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unreported confirm item", result.stderr)

    def test_verify_requires_image_structural_evidence(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "source.pdf"
            make_pdf(source)
            initialized = run("init", source, "--jobs-root", root / "jobs")
            job_dir = Path(json.loads(initialized.stdout)["job_dir"])
            candidate = job_dir / "candidate.pdf"
            make_pdf(candidate)
            job_path = job_dir / "job.json"
            job = json.loads(job_path.read_text(encoding="utf-8"))
            job["stage"] = "assembled"
            job["artifacts"]["candidate_pdf"] = {
                "path": str(candidate.resolve()),
                "sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
            }
            job_path.write_text(json.dumps(job), encoding="utf-8")
            report = root / "visual-review.json"
            report.write_text(
                json.dumps(
                    {
                        "all_pages_rendered": True,
                        "unreviewed_images": 0,
                        "untranslated_clear_image_labels": 0,
                        "logo_review_complete": True,
                        "header_footer_high_resolution_review_complete": True,
                        "text_overlap_failures": [],
                    }
                ),
                encoding="utf-8",
            )

            result = run("verify", job_dir, "--visual-review-report", report)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("image_structural_review_complete", result.stderr)


if __name__ == "__main__":
    unittest.main()
