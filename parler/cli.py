"""Command-line interface for parler."""

from __future__ import annotations

from datetime import date
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import click

from .config import load_config
from .errors import ParlerError, exit_code_for
from .pipeline import PipelineOrchestrator


def _package_version() -> str:
    try:
        return version("parler")
    except PackageNotFoundError:
        return "0.1.0+local"


def _parse_meeting_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _build_overrides(
    *,
    languages: tuple[str, ...],
    output_format: str | None,
    output_path: Path | None,
    participants: tuple[str, ...],
    meeting_date_value: str | None,
) -> dict[str, object]:
    overrides: dict[str, object] = {}
    if languages:
        overrides["transcription.languages"] = list(languages)
    if output_format is not None:
        overrides["output.format"] = output_format
    if output_path is not None:
        overrides["output.output_path"] = str(output_path)
    if participants:
        overrides["participants"] = list(participants)
    parsed_meeting_date = _parse_meeting_date(meeting_date_value)
    if parsed_meeting_date is not None:
        overrides["meeting_date"] = parsed_meeting_date.isoformat()
    return overrides


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(version=_package_version(), prog_name="parler")
def cli() -> None:
    """Multilingual meeting intelligence built on Voxtral."""


@cli.command()
@click.argument("input_path", type=click.Path(path_type=Path, dir_okay=False))
@click.option("--config", "config_path", type=click.Path(path_type=Path, dir_okay=False))
@click.option("--lang", "languages", multiple=True, help="Repeat for each expected language.")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["markdown", "html", "json"], case_sensitive=False),
)
@click.option("--output", "output_path", type=click.Path(path_type=Path, dir_okay=False))
@click.option("--participant", "participants", multiple=True, help="Known participant name.")
@click.option(
    "--meeting-date", "meeting_date_value", help="Meeting date in ISO format (YYYY-MM-DD)."
)
@click.option("--checkpoint", "checkpoint_path", type=click.Path(path_type=Path, dir_okay=False))
@click.option("--resume", is_flag=True, help="Resume from an existing checkpoint if available.")
@click.option("--transcribe-only", is_flag=True, help="Stop after transcription.")
@click.option("--no-diarize", is_flag=True, help="Skip speaker attribution.")
@click.option("--yes", "assume_yes", is_flag=True, help="Auto-confirm cost prompts.")
def process(
    input_path: Path,
    config_path: Path | None,
    languages: tuple[str, ...],
    output_format: str | None,
    output_path: Path | None,
    participants: tuple[str, ...],
    meeting_date_value: str | None,
    checkpoint_path: Path | None,
    resume: bool,
    transcribe_only: bool,
    no_diarize: bool,
    assume_yes: bool,
) -> None:
    """Process an audio file into a transcript or decision report."""

    overrides = _build_overrides(
        languages=languages,
        output_format=output_format.lower() if output_format is not None else None,
        output_path=output_path,
        participants=participants,
        meeting_date_value=meeting_date_value,
    )
    config = load_config(config_path=config_path, overrides=overrides)
    orchestrator = PipelineOrchestrator(config)

    def confirm_cost(cost: float) -> bool:
        if assume_yes:
            return True
        return click.confirm(f"Estimated API cost is ${cost:.2f}. Continue?", default=False)

    state = orchestrator.run(
        input_path,
        transcribe_only=transcribe_only,
        no_diarize=no_diarize,
        checkpoint_path=checkpoint_path,
        resume=resume,
        on_cost_confirm=confirm_cost,
    )
    if state is None:
        click.echo("Processing cancelled before the first billable stage.", err=True)
        return

    rendered_output: str | None
    if transcribe_only:
        rendered_output = state.transcript.text if state.transcript is not None else None
    else:
        rendered_output = state.report

    if rendered_output is None:
        click.echo("No output produced.", err=True)
        return

    target_path = output_path or config.output.output_path
    if target_path is not None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(rendered_output, encoding="utf-8")
        click.echo(str(target_path))
        return

    click.echo(rendered_output)


@cli.group()
def config() -> None:
    """Inspect and validate parler configuration."""


@config.command("validate")
@click.option("--config", "config_path", type=click.Path(path_type=Path, dir_okay=False))
def validate_config(config_path: Path | None) -> None:
    """Load config and exit non-zero if invalid."""

    load_config(config_path=config_path)
    click.echo("Configuration is valid.")


def main() -> None:
    try:
        cli.main(prog_name="parler", standalone_mode=False)
    except click.ClickException as exc:
        exc.show()
        raise SystemExit(exc.exit_code) from exc
    except ParlerError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(exit_code_for(exc)) from exc
    except NotImplementedError as exc:
        click.echo(f"Not implemented yet: {exc}", err=True)
        raise SystemExit(1) from exc


__all__ = ["cli", "main"]
