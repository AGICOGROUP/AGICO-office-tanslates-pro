# Excel translation manifest

Create new jobs with UTF-8 schema v2. Keep every source location in `occurrences`; store reusable model work in `translation_units`.

```json
{
  "schema_version": 2,
  "source_file": "sample.xlsx",
  "source_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "target_language": "en",
  "output_mode": "monolingual",
  "occurrences": [
    {
      "id": "Sheet1!B12",
      "kind": "cell",
      "sheet": "Sheet1",
      "address": "B12",
      "source": "水泥磨 15TPH",
      "context_key": "cell:equipment-name",
      "protected_tokens": ["15TPH"],
      "translation_unit_id": "tu-001"
    }
  ],
  "translation_units": [
    {
      "id": "tu-001",
      "source": "水泥磨 15TPH",
      "context_key": "cell:equipment-name",
      "protected_tokens": ["15TPH"],
      "translation": "15TPH Cement Mill",
      "status": "translated"
    }
  ],
  "images": [
    {
      "id": "img-001",
      "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "occurrences": ["Sheet1#Image1", "Sheet2#Image3"],
      "status": "retain",
      "reason_code": "logo-or-brand"
    }
  ]
}
```

## Translation units

- Reuse one translation unit only when source text, object kind, context key, and protected tokens match.
- Keep every physical workbook location as a separate occurrence, even when several occurrences reference one translation unit.
- Use status `translated` for translated text. Use `retain` only when the translation equals the source and include a concrete `reason`.
- Preserve every protected token exactly in the translation.
- Keep deterministic English fixed-label translations and identifier/model-code retains in the
  same schema; only `pending` units require model work.
- Parameter occurrences may add `original_source`, `original_protected_tokens`, and
  `translation_template`. Their translation unit contains only the reusable label; `apply`
  deterministically appends the recorded separator and technical suffix.

## Images

Group identical image bytes by SHA-256 while retaining every occurrence location. Use status `reviewed`, `localized`, `retain`, or `manual-review`. Use one of these reason codes:

- `no-source-text`
- `logo-or-brand`
- `photograph`
- `localized`
- `manual-review`

## Validation and compatibility

Run `python scripts/validate_manifest.py <manifest.json>` before workbook mutation. The validator continues to accept legacy schema-less `{items, images}` manifests so existing jobs remain readable; all new pipeline jobs must emit schema v2.
