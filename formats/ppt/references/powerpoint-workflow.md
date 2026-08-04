# PowerPoint workflow

## Choose the mutation path

- `.ppt`: use installed PowerPoint through `scripts/ppt_com.ps1`, save to a new file, and retain the legacy format unless conversion is explicitly requested.
- `.pptx`: use `scripts/pptx_ooxml.py` for stable ordered text-node replacement. Use PowerPoint COM for native tables, charts, notes, grouped objects, or overlay placement that requires the application object model.

## Native text

Replace paragraphs, runs, table-cell text, chart labels, and notes in place. Retain run properties, paragraph properties, object geometry, theme references, and relationships. Apply translations by stable object identity rather than string search.

Before translation, run `../scripts/resolve_repo_glossary.py` and search the resolved repository glossary `../../../references/水泥专业名词中英对照.md` for the complete Chinese phrase and then for the longest contained listed term. Use listed translations before proposing a new model translation. Apply `typography-and-fit.md` after native text replacement and before delivery.

## Tables and charts

Inventory merged cells, row heights, column widths, alignment, fills, borders, formulas, series, axes, legends, and data links. Translate only visible labels. Do not alter numeric data, formulas, chart series, or link targets.

## Verification

Reopen the saved result, extract all native text, and compare slide/object counts with the original. Render every slide at 2x; render dense diagrams at 3x. Check clipping, wrapping, overlap, contrast, source-language residue, terminology compliance, peer typography, protected tokens, and any approved local additions. Treat geometry changes without verified overflow or collision as failures.
