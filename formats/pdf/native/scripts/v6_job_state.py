from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STAGES = (
    "initialized",
    "native_translated",
    "images_annotated",
    "images_cleaned",
    "assembled",
    "verified",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^\w.-]+", "-", value, flags=re.UNICODE).strip(".-")
    return cleaned or "pdf-job"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_job(job_dir: Path, job: dict[str, Any]) -> None:
    job_path = job_dir / "job.json"
    temporary = job_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(job_path)


def create_job(source: Path, jobs_root: Path) -> Path:
    source = source.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    source_hash = sha256_file(source)
    job_dir = jobs_root.resolve() / f"{_slug(source.stem)}-{source_hash[:8]}"
    job_dir.mkdir(parents=True, exist_ok=True)
    job_path = job_dir / "job.json"
    if job_path.exists():
        job = load_job(job_dir)
        if job["source"]["sha256"] != source_hash:
            raise ValueError("job identity conflicts with source hash")
        return job_dir
    job = {
        "schema_version": 1,
        "stage": "initialized",
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "source": {"path": str(source), "sha256": source_hash},
        "artifacts": {},
        "failures": [],
    }
    save_job(job_dir, job)
    return job_dir


def load_job(job_dir: Path) -> dict[str, Any]:
    return json.loads((job_dir / "job.json").read_text(encoding="utf-8"))


def _assert_source(job: dict[str, Any]) -> None:
    source = Path(job["source"]["path"])
    if not source.is_file() or sha256_file(source) != job["source"]["sha256"]:
        raise ValueError("source hash changed")


def bind_artifact(job_dir: Path, name: str, path: Path) -> None:
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    job = load_job(job_dir)
    job["artifacts"][name] = {
        "path": str(path),
        "sha256": sha256_file(path),
    }
    job["updated_at"] = _utc_now()
    save_job(job_dir, job)


def assert_artifacts(job_dir: Path, required: tuple[str, ...]) -> None:
    job = load_job(job_dir)
    _assert_source(job)
    for name in required:
        record = job["artifacts"].get(name)
        if not record:
            raise ValueError(f"missing artifact: {name}")
        path = Path(record["path"])
        if not path.is_file() or sha256_file(path) != record["sha256"]:
            raise ValueError(f"artifact hash changed: {name}")


def advance(
    job_dir: Path, target: str, required: tuple[str, ...]
) -> dict[str, Any]:
    assert_artifacts(job_dir, required)
    job = load_job(job_dir)
    try:
        current_index = STAGES.index(job["stage"])
        target_index = STAGES.index(target)
    except ValueError as exc:
        raise ValueError("unknown stage") from exc
    if target_index != current_index + 1:
        raise ValueError(
            f"invalid stage transition: {job['stage']} -> {target}"
        )
    job["stage"] = target
    job["updated_at"] = _utc_now()
    save_job(job_dir, job)
    return job
