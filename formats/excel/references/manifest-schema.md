# Excel translation manifest

Use UTF-8 JSON with two arrays:

```json
{
  "items": [
    {
      "id": "Sheet1!B12",
      "source": "水泥磨 15TPH",
      "translation": "15TPH Cement Mill",
      "status": "translated",
      "protected_tokens": ["15TPH"]
    }
  ],
  "images": [
    {
      "id": "Sheet1#Image1",
      "status": "reviewed",
      "reason": "Logo; no translatable text"
    }
  ]
}
```

Item status is `translated` or `retain`. A retained item requires `reason`; its translation remains identical to the source. Every protected token must appear unchanged in the translation.

Image status is `reviewed`, `localized`, or `retain`, always with a concrete reason. Include every image, including logos and images without text, so review coverage is explicit.

Run `scripts/validate_manifest.py <manifest.json>` before editing the workbook.
