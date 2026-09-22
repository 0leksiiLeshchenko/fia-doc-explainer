import argparse
import asyncio
import os
import pathlib
import sys
from dataclasses import dataclass

from dotenv import load_dotenv

from fia_doc_explainer.download import download_pdf
from fia_doc_explainer.errors import DocumentProcessingError
from fia_doc_explainer.pipeline import process_document
from fia_doc_explainer.providers.anthropic_provider import AnthropicProvider
from fia_doc_explainer.providers.chain import ProviderChain
from fia_doc_explainer.providers.gemini_provider import GeminiProvider

REQUIRED_ENV_VARS = (
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "ANTHROPIC_PRIMARY_MODEL",
    "ANTHROPIC_ESCALATION_MODEL",
    "GEMINI_MODEL",
)


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


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fia-doc-explainer")
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--url", type=str)
    source_group.add_argument("--file", type=pathlib.Path)
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv()

    args = _build_arg_parser().parse_args(argv)

    try:
        config = load_config()
    except ConfigError as exc:
        print(exc.message, file=sys.stderr)
        return 3

    providers = ProviderChain(
        primary=AnthropicProvider(model=config.anthropic_primary_model),
        escalation=AnthropicProvider(model=config.anthropic_escalation_model),
        quota_fallback=GeminiProvider(model=config.gemini_model),
    )

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

    print(summary.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
