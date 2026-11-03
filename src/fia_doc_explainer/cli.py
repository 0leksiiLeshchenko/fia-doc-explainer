import argparse
import asyncio
import os
import pathlib
import sys
import textwrap
from dataclasses import dataclass

from dotenv import load_dotenv

from fia_doc_explainer.download import download_pdf
from fia_doc_explainer.errors import DocumentProcessingError
from fia_doc_explainer.pipeline import process_document
from fia_doc_explainer.providers.anthropic_provider import AnthropicProvider
from fia_doc_explainer.providers.chain import ProviderChain
from fia_doc_explainer.providers.gemini_provider import GeminiProvider
from fia_doc_explainer.schemas import DocumentSummary

REQUIRED_ENV_VARS = (
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "ANTHROPIC_PRIMARY_MODEL",
    "ANTHROPIC_ESCALATION_MODEL",
    "GEMINI_MODEL",
)
WRAP_WIDTH = 88


class ConfigError(Exception):
    def __init__(self, message: str, *args: object) -> None:
        super().__init__(message, *args)
        self.message = message


@dataclass(frozen=True)
class Config:
    anthropic_primary_model: str
    anthropic_escalation_model: str
    gemini_model: str


def load_config() -> Config:
    values = {name: os.environ.get(name, "") for name in REQUIRED_ENV_VARS}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ConfigError(
            f"Missing required environment variables: {', '.join(missing)}"
        )
    return Config(
        anthropic_primary_model=values["ANTHROPIC_PRIMARY_MODEL"],
        anthropic_escalation_model=values["ANTHROPIC_ESCALATION_MODEL"],
        gemini_model=values["GEMINI_MODEL"],
    )


def _build_provider_chain(config: Config) -> ProviderChain:
    return ProviderChain(
        primary=AnthropicProvider(model=config.anthropic_primary_model),
        escalation=AnthropicProvider(model=config.anthropic_escalation_model),
        quota_fallback=GeminiProvider(model=config.gemini_model),
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fia-doc-explainer")
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--url", type=str)
    source_group.add_argument("--file", type=pathlib.Path)
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def _wrap_paragraphs(text: str) -> str:
    paragraphs = (part.strip() for part in text.split("\n\n"))
    return "\n\n".join(textwrap.fill(p, WRAP_WIDTH) for p in paragraphs if p)


def _reason_line(label: str, reason: str | None, absent: str) -> str:
    prefix = f"  {label}: "
    return textwrap.fill(
        reason if reason is not None else absent,
        WRAP_WIDTH,
        initial_indent=prefix,
        subsequent_indent=" " * len(prefix),
    )


def format_summary(summary: DocumentSummary) -> str:
    header = [f"Document type: {summary.doc_type}"]
    if summary.source_url is not None:
        header.append(f"Source: {summary.source_url}")
    header.append(f"Model: {summary.model_used}")
    sections = ["\n".join(header)]

    if summary.low_confidence:
        sections.append(
            "\n".join(
                [
                    "LOW CONFIDENCE",
                    _reason_line(
                        "Heuristic", summary.heuristic_reason, "not triggered"
                    ),
                    _reason_line(
                        "Model", summary.low_confidence_reason, "did not flag"
                    ),
                ]
            )
        )

    facts = [
        textwrap.fill(fact, WRAP_WIDTH, initial_indent="- ", subsequent_indent="  ")
        for fact in summary.key_facts
    ]
    sections.append("\n".join(["Key facts:", *facts]))
    sections.append("Explanation:\n" + _wrap_paragraphs(summary.plain_explanation))
    return "\n\n".join(sections)


def main(argv: list[str] | None = None) -> int:
    load_dotenv()

    args = _build_arg_parser().parse_args(argv)

    try:
        config = load_config()
    except ConfigError as exc:
        print(exc.message, file=sys.stderr)
        return 3

    providers = _build_provider_chain(config)

    try:
        if args.url is not None:
            pdf_bytes = asyncio.run(download_pdf(args.url))
            source_url = args.url
        else:
            pdf_bytes = args.file.read_bytes()
            source_url = None

        summary = process_document(
            pdf_bytes=pdf_bytes, providers=providers, source_url=source_url
        )
    except (DocumentProcessingError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.as_json:
        print(summary.model_dump_json(indent=2))
    else:
        print(format_summary(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
