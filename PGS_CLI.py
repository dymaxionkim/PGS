"""Command-line (headless) PGS sizing + export runner.

Loads a saved report file (e.g. a GUI-produced ``Result/README.md``), finds
its ``## Input Parameters`` section, re-runs the exact same calculation the
GUI ``Run`` button performs and — depending on the save option — writes all
output files next to the input Markdown file, with the per-gear folders
(``Gs1``, ``Gp1``, ...) inside that directory exactly like the GUI ``Save``.

Usage::

    uv run PGS_CLI.py <path/to/README.md> [SaveAll|SaveOK|SaveMD]

Arguments
---------
<README.md>
    Path to the Markdown file carrying the ``## Input Parameters`` section.

[SaveAll|SaveOK|SaveMD]   (default: SaveAll)
    SaveAll : always write the report ``README.md``, the PNG drawings and the
              per-gear CSV/DXF/PNG result folders next to the input file.
    SaveOK  : only write them when ``## Check Geometrical Conditions`` of the
              newly computed report contains no "Fail" status.
    SaveMD  : write nothing unless every check is "OK"; in that case save
              only the report ``README.md`` (no images, no per-gear folders).

Notes
-----
- The output report is written as ``README.md`` in the input file's folder.
  If the input file itself is named ``README.md``, the regenerated report
  overwrites it.
"""

from __future__ import annotations

import os
import sys

import matplotlib

matplotlib.use("Agg")  # headless rendering, no GUI window needed

import design  # noqa: E402  (backend must be set before design imports pyplot)


class _Entry:
    """Minimal stand-in for a ttk entry widget; only ``.get()`` is used."""

    def __init__(self, value: str) -> None:
        self._value = value

    def get(self) -> str:
        return self._value


class _Text:
    """Minimal stand-in for the report textbox widget."""

    def __init__(self) -> None:
        self._text = ""

    def delete(self, first="0.0", last="end") -> None:  # noqa: ARG002
        self._text = ""

    def insert(self, index: str, content: str) -> None:  # noqa: ARG002
        self._text += content

    def get(self, first="0.0", last="end") -> str:  # noqa: ARG002
        return self._text


def _entry_values(report_values: dict[str, str]) -> dict[str, str]:
    """Map the report ``## Input Parameters`` keys to entry-widget values.

    Mirrors the GUI Load button: the TYPE lines carry "code, label" and the
    ring teeth are stored negative ("-90.0") while the input fields expect
    the positive count ("90.0").
    """
    values: dict[str, str] = {}
    for report_key, entry_key in design.REPORT_KEY_TO_ENTRY.items():
        value = report_values.get(report_key)
        if value is None:
            continue
        if entry_key == "TYPE":
            code = int(value.split(",")[0].strip())
            label = design.TYPE_CODE_TO_LABEL.get(code)
            if label is not None:
                values[entry_key] = label
        elif entry_key in ("Zr1", "Zr2"):
            values[entry_key] = str(abs(float(value)))
        else:
            values[entry_key] = value
    return values


def _apply_defaults(values: dict[str, str]) -> dict[str, str]:
    """Fill any entry missing from the report with the GUI default value."""
    for key, default in design.DEFAULT_INPUTS.items():
        if key in values:
            continue
        if key == "TYPE":
            values[key] = design.TYPE_CODE_TO_LABEL[default]
        elif key == "PlotOption":
            values[key] = design.PLOT_CODE_TO_LABEL[default]
        else:
            values[key] = str(default)
    return values


def _checks_contain_fail(report: str) -> bool:
    """True when ``## Check Geometrical Conditions`` holds a "Fail" status."""
    in_checks = False
    for line in report.splitlines():
        if line.startswith("## "):
            if line.strip() == "## Check Geometrical Conditions":
                in_checks = True
            elif in_checks:
                break
        elif in_checks and line.startswith("* "):
            if "Fail" in line:
                return True
    return False


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Run the PGS calculation from a report file's "
                    "'## Input Parameters' section and optionally export "
                    "every result file next to it.",
    )
    parser.add_argument(
        "md",
        help="Path to the Markdown report carrying the '## Input Parameters' "
             "section (e.g. Result/README.md).",
    )
    parser.add_argument(
        "mode",
        nargs="?",
        default="SaveAll",
        choices=("SaveAll", "SaveOK", "SaveMD"),
        help="'SaveAll' (default) always writes the result files; "
             "'SaveOK' skips writing when a check fails; "
             "'SaveMD' writes only the report README.md, and only when "
             "every check is 'OK'.",
    )
    args = parser.parse_args(argv)

    md_path = os.path.abspath(args.md)
    if not os.path.isfile(md_path):
        print(f"Error: file not found: {md_path}", file=sys.stderr)
        return 1

    try:
        with open(md_path, encoding="utf-8") as f:
            md_text = f.read()
    except OSError as exc:
        print(f"Error: failed to read {md_path}: {exc}", file=sys.stderr)
        return 1

    report_values = design._parse_input_parameters(md_text)
    if not report_values:
        print(f"Error: no '## Input Parameters' section in {md_path}",
              file=sys.stderr)
        return 1

    try:
        entry_values = _apply_defaults(_entry_values(report_values))
    except ValueError as exc:
        print(f"Error: malformed '## Input Parameters' values: {exc}",
              file=sys.stderr)
        return 1

    # Replicate `design.main()`: fresh model + involute (GPG) gear set.
    design.P1 = design.PGS()
    design.gears = {name: design.GPG() for name in design.GEAR_ORDER}
    design.gears_second = None
    design.entries = {key: _Entry(value) for key, value in entry_values.items()}
    design.textbox = _Text()

    design.read_parameters()
    design.run_calc()
    design.build_report()

    report = design.textbox.get("0.0", "end")
    print(report)

    out_dir = os.path.dirname(md_path)
    if args.mode in ("SaveOK", "SaveMD") and _checks_contain_fail(report):
        print(f"{args.mode}: 'Fail' present in '## Check Geometrical Conditions'"
              f" -> nothing was saved to {out_dir}")
        return 0

    if os.path.basename(md_path).lower() == "readme.md":
        print(f"Note: overwriting the input report {os.path.basename(md_path)}"
              f" with the regenerated one.")

    if args.mode == "SaveMD":
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "README.md"), "w",
                  encoding="utf-8") as f:
            f.write(report)
        print(f"README.md saved in {out_dir}")
        return 0

    design.save_output(out_dir)
    design.save_pngs(out_dir)
    print(f"Result files saved in {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())