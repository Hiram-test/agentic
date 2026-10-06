# 06 Engineering-report typography and generation

## Source and contents

Use `assets/reference/original_review_0324.pdf` as the layout reference: A4 portrait, ruled headers/footers, thin table borders, separate figure captions and engineering-topic sections.

Generate the requested overall catwalk and portal support cable report with this contents structure:

- Cover and updatable table of contents.
- Chapter 1, Project overview: 1.1 Overview; 1.2 Source documents; 1.3 Criteria and conventions; 1.4 Materials and sections; 1.5 Principal loads.
- Chapter 2, Catwalk and portal cable analysis: 2.1 Control points and supports; 2.2 Model, mesh and steps; 2.3 Combinations and completeness; 2.4 Bottom cables; 2.5 Portal cables; 2.6 Result graphics.
- Chapter 3, Conclusions: calculated results, comparison outcomes and model definition.
- Appendix A, Input hashes and execution provenance.

Retain the approved Chinese report language. Use the actual generation date and the current report identity on its cover. The generated report has its own pagination.

## Reference and calculated values

Cable-force references come from Tables 1-11/1-14 on physical PDF pages 30/39. Safety-factor requirements come from Table 1-7 on page 11. Displacement references come from the separately documented MAPDL reproduction.

Force tables carry case/span, current N, report N, signed difference %, current K, required K and acceptance. Displacement tables carry current USUM, MAPDL reference, signed difference % and peak node.

Calculate `difference_percent = 100 * (current/reference - 1)`. Use absolute differences for regression acceptance and retain the signed values in tables. Preserve the original integer-kN reference precision.

## Generation

After solving all six cases, `run.py` invokes `report.generate()`. Build DOCX/PDF from the same result data. PDF generation embeds the bundled SimSun, SimHei and Times New Roman fonts through ReportLab; Word uses and embeds the same fonts.

Use white tables, thin rules, repeating headers, automatic page breaks, a contents field and three-digit page numbers. Update DOCX fields in Word with Ctrl+A/F9. Contours use SimSun Chinese labels, a white background, discrete color scales and red extrema annotations.

Describe the supplied initial-stress/reference-geometry state consistently. The delivered coordinate CSV represents the calculated line geometry; any separate unstressed-length or form-finding calculation needs its own solved data.

Embed UZ, bottom N and portal N for each case in the engineering report. Keep the other four PNGs per case in the result directory. Captions identify endpoint-average coloring, coordinate units m, displacement units mm, force units kN and independent axis scaling. Generate every result graphic from that run's final DAT fields.

## Fixed style parameters

Source: `assets/reference/report_style.json`; implementation: `scripts/report_style.py`; fonts and provenance: `assets/fonts/`.

- Page size: 595.32 × 842.04 pt. Left/right margins: 70.87/42.52 pt.
- Cover: centered two-line SimHei, 42/36 pt.
- Chapter/section/subsection headings: SimHei 16/14/12 pt.
- Body: SimSun 12 pt; Latin characters/numerals: Times New Roman; line spacing 23.4 pt; first-line indent 24 pt.
- Tables/captions: SimSun 10.5 pt; rule width 0.4 pt; white background.
- Safety-factor numerals: bold. Strength tables: approximately 409 pt wide, four span columns and vertically merged case labels.
- Header/footer horizontal rules: 56.1/768.7 pt from page top.
- Page numbering: three-digit current page / total pages.
- Use actual superscript formatting and verify glyph coverage for symbols, brackets and underscores.

## Pre-delivery checks

1. Read `run.json.status`, all six summaries and any failed criteria.
2. Verify report values against the current summaries, including P5.
3. Check reference/current column labels and the planar model description.
4. Visually inspect Chinese glyphs, margins, table width, captions and contents pagination.
5. Match chapters to the contents list above.
6. Match every reported response quantity to its output evidence.
7. Refresh SHA256SUMS and package the deliverables.

For typography-only changes, execute `scripts/rebuild_report.py --run /path/to/completed-run`. Rebuild from the completed data, verify unchanged numerical summaries and refresh output hashes.
