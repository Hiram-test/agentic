# Agentic FEA manuscript framework

Reference: [FeaGPT: an End-to-End agentic-AI for Finite Element Analysis](https://arxiv.org/abs/2510.21993v1), by Yupeng Qi, Ran Xu and Xu Chu (2025).

## Deliverables

- [Downloaded reference paper](reference/FeaGPT.pdf) and [source/version/license record](reference/source.json).
- Figure-by-figure study: [Word](FeaGPT_figure_by_figure_study.docx) / [PDF](FeaGPT_figure_by_figure_study.pdf). All five figures, three tables and Algorithm 1 are mapped to the catwalk project.
- SCI manuscript framework: [Word](SCI_manuscript_framework.docx) / [PDF](SCI_manuscript_framework.pdf), with the reference section order, direct manuscript prose, result tables and figure captions.
- [Editable LaTeX outline](manuscript_outline.tex), [section mapping](section_mapping.json), [figure mapping](figure_mapping.csv), [task schema](task_specification.json) and [BibTeX](references.bib).
- Completed six-case comparison figure: [PNG](figures/figure_4_six_case_verification.png) / [vector PDF](figures/figure_4_six_case_verification.pdf) / [plot data](figures/figure_4_data.csv).
- [Evidence map](evidence_map.json) connects numerical results to the existing validated run. Planned GLM session measurements are tracked in the evidence map.

The English execution package is at [catwalk-static-review](../../skills/catwalk-static-review/README.md). Its approved Chinese engineering-report format is retained.

## Rebuild

Install the Skill's requirements and run:

```bash
python papers/agentic-fea-framework/scripts/build_framework.py
```

This builds the framework, study documents and Figure 4 from the bundled validation summary. XeLaTeX or LuaLaTeX can compile the editable `.tex` outline independently.

Source-paper previews are unchanged reproductions attributed to Qi, Xu and Chu, licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The study identifies the source composition and the corresponding catwalk replacement for each figure.
