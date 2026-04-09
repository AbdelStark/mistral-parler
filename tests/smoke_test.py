from __future__ import annotations

from datetime import date

from click.testing import CliRunner
from parler import ParlerConfig
from parler.cli import cli
from parler.models import DecisionLog, ExtractionMetadata
from parler.rendering.renderer import OutputFormat, RenderConfig, ReportRenderer


def main() -> None:
    config = ParlerConfig(api_key="smoke-test-key")
    assert config.output.format == "markdown"

    log = DecisionLog(
        decisions=(),
        commitments=(),
        rejected=(),
        open_questions=(),
        metadata=ExtractionMetadata(
            model="mistral-large-latest",
            prompt_version="v1",
            meeting_date=date(2026, 4, 9),
            extracted_at="2026-04-09T10:00:00Z",
            input_tokens=0,
            output_tokens=0,
        ),
    )
    output = ReportRenderer().render(log, RenderConfig(format=OutputFormat.JSON))
    assert "metadata" in output

    help_result = CliRunner().invoke(cli, ["--help"])
    assert help_result.exit_code == 0
    assert "process" in help_result.output


if __name__ == "__main__":
    main()
