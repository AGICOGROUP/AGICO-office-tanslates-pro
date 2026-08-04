# PowerPoint translation manifest

Use UTF-8 JSON. Keep items in slide reading order and never deduplicate repeated text.

```json
{
  "source_file": "sample.pptx",
  "source_language": "zh-CN",
  "target_language": "en",
  "format": "powerpoint",
  "items": []
}
```

Every item requires `id`, `kind`, `source_text`, `translation`, `context`, `location`, and `protected_tokens`. IDs must be unique. `translation` may be empty during extraction but must be non-empty before apply.

Supported kinds and locations:

| Kind | Required location fields |
|---|---|
| `ppt_paragraph` | `slide`, `shape_id`, `paragraph` |
| `ppt_table_cell` | `slide`, `shape_id`, `row`, `column`, `paragraph` |
| `ppt_note` | `slide`, `shape_id`, `paragraph` |
| `ppt_chart_text` | `slide`, `shape_id`, `chart_part` |
| `office_overlay` | `page_or_slide`, `host_shape_id`, `region_id` |

Preserve numbers, units, formulas, model identifiers, standards, and intentional whitespace in `protected_tokens` or translated text.
