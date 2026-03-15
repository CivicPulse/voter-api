"""CLI commands for markdown-to-JSONL conversion.

Provides the ``voter-api convert`` command group with ``directory``
and ``file`` subcommands for batch and single-file conversion of
election markdown files to validated JSONL records.
"""

import sys
from pathlib import Path

import typer

from voter_api.lib.converter import convert_directory, convert_file

convert_app = typer.Typer()


@convert_app.command("directory")
def convert_directory_cmd(
    directory: Path = typer.Argument(  # noqa: B008
        ...,
        help="Path to the election directory to convert.",
        exists=True,
        file_okay=False,
        resolve_path=True,
    ),
    output: Path | None = typer.Option(  # noqa: B008
        None,
        "--output",
        "-o",
        help="Output directory for JSONL files. Defaults to sibling jsonl/ directory.",
    ),
    fail_fast: bool = typer.Option(  # noqa: B008
        False,
        "--fail-fast",
        help="Stop on first conversion failure.",
    ),
    counties_dir: Path | None = typer.Option(  # noqa: B008
        None,
        "--counties-dir",
        help="Path to county reference files. Defaults to auto-detect.",
    ),
) -> None:
    """Convert an entire election directory from markdown to JSONL.

    Walks the directory tree, parses markdown files, validates records
    against JSONL schemas, and writes output to JSONL files.
    """
    report = convert_directory(
        directory,
        output=output,
        fail_fast=fail_fast,
        counties_dir=counties_dir,
    )

    # Print terminal report
    typer.echo(report.render_terminal())

    # Exit with code 1 if any failures
    if report.files_failed > 0:
        typer.echo(f"{report.files_failed} file(s) failed conversion.", err=True)
        sys.exit(1)

    typer.echo(f"Converted {report.files_succeeded} file(s) successfully.")


@convert_app.command("file")
def convert_file_cmd(
    file_path: Path = typer.Argument(  # noqa: B008
        ...,
        help="Path to the markdown file to convert.",
        exists=True,
        dir_okay=False,
        resolve_path=True,
    ),
    output: Path | None = typer.Option(  # noqa: B008
        None,
        "--output",
        "-o",
        help="Output directory for JSONL files.",
    ),
) -> None:
    """Convert a single markdown file to JSONL records.

    Parses the file, validates records against JSONL schemas, and
    prints a summary of the results.
    """
    result = convert_file(file_path, output=output)

    if result.errors:
        typer.echo("Conversion failed:", err=True)
        for error in result.errors:
            typer.echo(f"  {error}", err=True)
        sys.exit(1)

    typer.echo(f"Converted {file_path.name}: {len(result.records)} record(s)")
