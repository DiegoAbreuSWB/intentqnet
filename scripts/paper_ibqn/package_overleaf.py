"""P-IBQN-ZIP: builds paper_ibqn_overleaf/, a flattened, self-contained
snapshot of paper_ibqn/ ready to upload to Overleaf as a ZIP. Every
figure/table path inside the package is rewritten to point INSIDE the
package (never at ../results/paper_ibqn/...) - Overleaf has no access to
this repository's other directories. Section text is copied verbatim
(only the \\includegraphics/\\input path prefixes are rewritten); no
wording, denominator, or number is changed.

Run: python scripts/paper_ibqn/package_overleaf.py
Writes: paper_ibqn_overleaf/
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_PAPER = PROJECT_ROOT / "paper_ibqn"
SRC_FIGURES = PROJECT_ROOT / "results" / "paper_ibqn" / "figures"
SRC_TABLES = PROJECT_ROOT / "results" / "paper_ibqn" / "tables"
OUT_DIR = PROJECT_ROOT / "paper_ibqn_overleaf"

ALL_SECTION_FILES = [
    "01_introduction", "02_background_related_work", "03_ibqn_architecture", "04_implementation",
    "05_evaluation_methodology", "06_lifecycle_and_assurance_results", "07_planner_robustness_results",
    "08_reconciliation_results", "09_multi_intent_and_overhead", "10_discussion",
    "11_threats_to_validity", "12_conclusion",
]
INCOMPLETE_SECTIONS = {
    "01_introduction": "write final introduction",
    "02_background_related_work": "complete related work",
    "10_discussion": "write final discussion",
    "11_threats_to_validity": "consolidate threats to validity",
    "12_conclusion": "write conclusion",
}

# The 12 generated tables referenced by the manuscript, plus the macros file.
TABLE_NAMES = [
    "intent_schema", "lifecycle_states", "planner_capabilities", "planner_false_feasibility",
    "oracle_by_planner", "oracle_purification_boundary", "assurance_results", "reconciliation_results",
    "multi_intent_results", "overhead_results", "failure_taxonomy", "limitations",
]

FIGURE_NAMES = [
    "fig_ibqn_architecture", "fig_lifecycle_state_machine", "fig_planner_error_taxonomy",
    "fig_false_feasibility_by_planner", "fig_false_rejection_by_planner", "fig_assurance_vs_oracle",
    "fig_reconciliation_recovery", "fig_multi_intent_scenarios", "fig_overhead_control_plane",
    "fig_purification_boundary_mechanism", "fig_reconciliation_workflow", "fig_overhead_full",
    "fig_diamond_candidate_routes", "fig_planner_capability_cost",
]


def fix_includegraphics_and_input(text: str) -> str:
    """\\includegraphics[...]{fig_name} -> \\includegraphics[...]{figures/fig_name.pdf};
    \\input{../results/paper_ibqn/tables/name.tex} -> \\input{tables/name.tex}.
    Never touches anything else in the text."""
    text = re.sub(
        r"\\includegraphics(\[[^\]]*\])?\{(fig_[A-Za-z0-9_]+)\}",
        lambda m: f"\\includegraphics{m.group(1) or ''}{{figures/{m.group(2)}.pdf}}",
        text,
    )
    text = re.sub(
        r"\\input\{\.\./results/paper_ibqn/tables/([A-Za-z0-9_]+\.tex)\}",
        lambda m: f"\\input{{tables/{m.group(1)}}}",
        text,
    )
    return text


def build_main_tex() -> str:
    text = (SRC_PAPER / "main.tex").read_text(encoding="utf-8")

    # self-contained graphics path (was ../results/paper_ibqn/figures/)
    text = text.replace(
        "\\graphicspath{{../results/paper_ibqn/figures/}}",
        "\\graphicspath{{figures/}}",
    )

    # short, compilable placeholder abstract/keywords (per governing instruction)
    new_abstract = (
        "\\begin{abstract}\n"
        "\\textbf{Placeholder:} The final abstract will be written after "
        "manuscript refinement (see Sections 3--9 for the current complete "
        "results; Sections 1, 2, 10--12 remain outlines/placeholders).\n"
        "\\end{abstract}"
    )
    text = re.sub(r"\\begin\{abstract\}.*?\\end\{abstract\}", lambda m: new_abstract, text, flags=re.DOTALL)

    new_keywords = (
        "\\begin{IEEEkeywords}\n"
        "Placeholder keywords; to be finalized together with the abstract.\n"
        "\\end{IEEEkeywords}"
    )
    text = re.sub(r"\\begin\{IEEEkeywords\}.*?\\end\{IEEEkeywords\}", lambda m: new_keywords, text, flags=re.DOTALL)

    # supplement include flag (simple, per governing instruction - no complex logic)
    text = text.replace(
        "\\def\\BibTeX{",
        "\\newif\\ifincludesupplement\n\\includesupplementfalse\n% To include the supplement in this same PDF, change the line\n"
        "% above to \\includesupplementtrue (see README.md).\n\n"
        "\\def\\BibTeX{",
    )
    text = text.replace(
        "\\bibliography{bibliography/references}\n\n\\end{document}",
        "\\bibliography{bibliography/references}\n\n"
        "\\ifincludesupplement\n"
        "\\newpage\n"
        "\\input{supplementary/supplementary_body.tex}\n"
        "\\fi\n\n"
        "\\end{document}",
    )
    return text


def build_section(name: str) -> str:
    text = (SRC_PAPER / "sections" / f"{name}.tex").read_text(encoding="utf-8")
    text = fix_includegraphics_and_input(text)
    if name in INCOMPLETE_SECTIONS:
        marker = f"% TODO OVERLEAF: {INCOMPLETE_SECTIONS[name]}\n"
        text = marker + text
    return text


def build_supplementary_body() -> str:
    """Strips supplementary.tex down to its includable body (no
    \\documentclass/\\graphicspath/\\input{macros}/\\begin{document}/
    \\maketitle/\\end{document}) so the SAME fragment can be \\input both
    by main.tex (flag-gated) and by the standalone supplementary.tex -
    never duplicated as two different copies of the same content."""
    text = (SRC_PAPER / "supplementary" / "supplementary.tex").read_text(encoding="utf-8")
    start = text.index("This supplement accompanies")
    end = text.index("\\end{document}")
    body = text[start:end]
    # figures inside the shared body use bare filenames + extension, no
    # path prefix - each caller (main.tex or supplementary.tex) sets its
    # own \graphicspath so the same fragment resolves correctly from
    # either the package root or supplementary/.
    body = re.sub(
        r"\\includegraphics(\[[^\]]*\])?\{(fig_[A-Za-z0-9_]+)\}",
        lambda m: f"\\includegraphics{m.group(1) or ''}{{{m.group(2)}.pdf}}",
        body,
    )
    return "\\section{Supplementary Material}\n\n" + body


def build_supplementary_standalone() -> str:
    return (
        "\\documentclass[10pt]{article}\n"
        "\\usepackage[T1]{fontenc}\n"
        "\\usepackage{amsmath,amssymb,amsfonts}\n"
        "\\usepackage{graphicx}\n"
        "\\usepackage{booktabs}\n"
        "\\usepackage[margin=1in]{geometry}\n\n"
        "\\graphicspath{{../figures/}}\n"
        "\\input{../tables/result_macros.tex}\n\n"
        "\\title{Supplementary Material\\\\\n"
        "\\large Intent-Based Quantum Networks: Architecture, Assurance, and Planner-Robust Validation}\n"
        "\\author{}\n\\date{}\n\n"
        "\\begin{document}\n\\maketitle\n\n"
        "\\input{supplementary_body.tex}\n\n"
        "\\end{document}\n"
    )


def main() -> None:
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    for sub in ["sections", "figures", "tables", "bibliography", "supplementary"]:
        (OUT_DIR / sub).mkdir(parents=True, exist_ok=True)

    (OUT_DIR / "main.tex").write_text(build_main_tex(), encoding="utf-8")

    for name in ALL_SECTION_FILES:
        (OUT_DIR / "sections" / f"{name}.tex").write_text(build_section(name), encoding="utf-8")

    for name in TABLE_NAMES:
        shutil.copy(SRC_TABLES / f"{name}.tex", OUT_DIR / "tables" / f"{name}.tex")
    shutil.copy(SRC_PAPER / "tables" / "result_macros.tex", OUT_DIR / "tables" / "result_macros.tex")

    for name in FIGURE_NAMES:
        for ext in ("pdf", "png"):
            src = SRC_FIGURES / f"{name}.{ext}"
            if src.exists():
                shutil.copy(src, OUT_DIR / "figures" / f"{name}.{ext}")

    shutil.copy(SRC_PAPER / "bibliography" / "references.bib", OUT_DIR / "bibliography" / "references.bib")

    (OUT_DIR / "supplementary" / "supplementary_body.tex").write_text(build_supplementary_body(), encoding="utf-8")
    (OUT_DIR / "supplementary" / "supplementary.tex").write_text(build_supplementary_standalone(), encoding="utf-8")

    n_figs = sum(1 for name in FIGURE_NAMES if (OUT_DIR / "figures" / f"{name}.pdf").exists())
    n_tables = len(TABLE_NAMES) + 1
    print(f"Wrote {OUT_DIR}: {len(ALL_SECTION_FILES)} sections, {n_figs} figures (PDF+PNG each), {n_tables} table files.")


if __name__ == "__main__":
    main()
