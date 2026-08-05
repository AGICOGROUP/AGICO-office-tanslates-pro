# Direct original-to-v6 workflow

The user supplies only the original PDF. The Skill owns every intermediate
artifact under a source-hash-bound job directory.

## Commands

```powershell
python scripts/run_v6_job.py init <source.pdf> --jobs-root tmp/pdfs
python scripts/run_v6_job.py status <job>
python scripts/run_v6_job.py resume <job>
python scripts/run_v6_job.py build-native <job>
python scripts/run_v6_job.py annotate-images <job> `
  --metadata <image-vector-metadata.json> --review <image-review.json>
python scripts/run_v6_job.py build-images <job>
python scripts/run_v6_job.py assemble <job>
python scripts/run_v6_job.py verify <job> `
  --visual-review-report <job>/visual-review.json
```

`resume` reports the next internal action. Exit code 2 means Codex must perform
that action; it is not a request for a user-supplied intermediate.

## Stage contract

| Stage | Required evidence |
|---|---|
| `initialized` | Source hash, native-text manifest, original-XObject inventory |
| `native_translated` | Complete translations and source-derived selectable PDF |
| `images_annotated` | Every inventory image and label reviewed; source type, route, OCR confidence, coverage, and confirms recorded |
| `images_cleaned` | Clean bases built; no changes outside approved regions; declared structures and evidence pass |
| `assembled` | Vector image labels merged into the native-text PDF |
| `verified` | Machine gates and full-page visual review passed |

`visual-review.json` must contain the SHA-256 of the exact candidate PDF.
Changing the candidate invalidates the report. The runner executes the native
selectability and typography verifiers itself; never copy zero values into the
final QA report.

Do not skip stages. Every artifact is bound by SHA-256. If the source or a
bound deterministic output changes unexpectedly, return to the owning stage.

## Image review schema

Review every ID in `image-inventory.json`, including logos, icons, diagrams,
photos, headers, and footers. Record whether it contains source-language text,
every stable label ID, asset type, OCR confidence, method, translation status,
coverage counts, structural-review status, and any `[CONFIRM]` regions. Images
with translated raster labels must have matching entries in
`image-vector-metadata.json`.

Use only the extracted original XObject path. Clean only minimum text regions.
Keep the clean drawing raster and place English in a separate embedded vector
text layer.

## Delivery

Do not copy the candidate to the delivery directory unless:

- `job.json` says `verified`;
- `final-qa.json` says `passed: true`;
- every page was rendered and inspected;
- no clear source-language text remains;
- source-selectable text and image-label text are selectable;
- image pixel and protected-line gates are zero.
- difference/alpha-overlay and structural review are complete;
- all confirm items are reported and no declared line failure remains.
