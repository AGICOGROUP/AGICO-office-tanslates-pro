# PowerPoint translation manifest schema v2

The UTF-8 JSON root requires:

```json
{
  "schema_version": 2,
  "source_file": "sample.pptx",
  "source_path": "D:/input/sample.pptx",
  "source_sha256": "64-lowercase-hex-digits",
  "source_language": "zh-CN",
  "target_language": "en",
  "format": "powerpoint",
  "occurrences": [],
  "translation_units": [],
  "image_groups": [],
  "risk_plan": {}
}
```

Every occurrence retains `id`, `kind`, `source_text`, `translation_unit_id`, `slide_index`,
`shape_id`, `paragraph_index`, `role`, `context_signature`, and `protected_tokens`. Table-cell
occurrences also retain `row` and `column` for the complex COM route plus
`package_paragraph_index` for the OOXML fast route.

Every translation unit retains `id`, `reuse_key`, `source_text`, `translation`, `role`,
`context_signature`, `protected_tokens`, and `occurrence_count`. Fill `translation` only. A unit may
serve multiple occurrences, but every referenced source text and protected-token sequence must
match exactly.

`image_groups` stores one record per unique media SHA-256 with all media paths and slide/shape
occurrences. Before apply, change `screening_status` from `pending` to `retain`, `localize`, or
`manual_review`; retained/manual groups require `reason_code`. `risk_plan` stores route, risk
slides, complex reasons, and strict reasons.

Schema v1 is not a production input. Convert a job by rerunning `inspect` and `prepare` from the
immutable source.
