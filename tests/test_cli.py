import json
import pathlib

import pytest

from fia_doc_explainer import cli
from fia_doc_explainer.cli import REQUIRED_ENV_VARS, WRAP_WIDTH, format_summary, main
from fia_doc_explainer.errors import DownloadError, ExtractionError, LLMError
from fia_doc_explainer.providers.chain import ProviderChain
from fia_doc_explainer.schemas import DocumentSummary
from tests.conftest import make_pdf_bytes
from tests.fakes import FakeProvider, flag_response, summary_response

PRIMARY_MODEL = "fake-primary"
ESCALATION_MODEL = "fake-escalation"
QUOTA_FALLBACK_MODEL = "fake-fallback"


def _unused_provider(model: str) -> FakeProvider:
    return FakeProvider(
        model=model, outcome=AssertionError(f"{model} should not be called")
    )


def _chain(primary: FakeProvider, escalation: FakeProvider) -> ProviderChain:
    return ProviderChain(
        primary=primary,
        escalation=escalation,
        quota_fallback=_unused_provider(QUOTA_FALLBACK_MODEL),
    )


def _forbidden_build_chain(config: cli.Config) -> ProviderChain:
    raise AssertionError("real provider chain must not be built in tests")


async def _forbidden_download(url: str) -> bytes:
    raise AssertionError(f"network call attempted: {url}")


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch) -> None:
    # load_dotenv would re-add variables deleted via delenv from the real .env.
    monkeypatch.setattr("fia_doc_explainer.cli.load_dotenv", lambda *a, **k: False)
    monkeypatch.setattr(
        "fia_doc_explainer.cli._build_provider_chain", _forbidden_build_chain
    )
    monkeypatch.setattr("fia_doc_explainer.cli.download_pdf", _forbidden_download)
    for name in REQUIRED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def full_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in REQUIRED_ENV_VARS:
        monkeypatch.setenv(name, f"value-of-{name}")


@pytest.fixture
def pdf_file(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "doc.pdf"
    path.write_bytes(make_pdf_bytes(pages=["Stewards Decision"]))
    return path


def _use_chain(monkeypatch: pytest.MonkeyPatch, chain: ProviderChain) -> None:
    monkeypatch.setattr(
        "fia_doc_explainer.cli._build_provider_chain", lambda config: chain
    )


def _happy_chain() -> ProviderChain:
    return _chain(
        FakeProvider(
            model=PRIMARY_MODEL, outcome=summary_response(model=PRIMARY_MODEL)
        ),
        _unused_provider(ESCALATION_MODEL),
    )


def _make_summary(
    *,
    plain_explanation: str = "Short text",
    key_facts: list[str] | None = None,
    source_url: str | None = None,
    low_confidence_reason: str | None = None,
    heuristic_reason: str | None = None,
) -> DocumentSummary:
    return DocumentSummary(
        doc_type="Decision",
        source_url=source_url,
        key_facts=key_facts if key_facts is not None else ["Kimi won"],
        plain_explanation=plain_explanation,
        model_used=PRIMARY_MODEL,
        low_confidence_reason=low_confidence_reason,
        heuristic_reason=heuristic_reason,
    )


# --- configuration ---


@pytest.mark.usefixtures("full_env")
@pytest.mark.parametrize("name", REQUIRED_ENV_VARS)
def test_missing_variable_reported(
    name: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    pdf_file: pathlib.Path,
) -> None:
    monkeypatch.delenv(name)

    code = main(argv=["--file", str(pdf_file)])

    captured = capsys.readouterr()
    assert code == 3
    assert name in captured.err
    assert captured.out == ""
    for other in REQUIRED_ENV_VARS:
        if other != name:
            assert other not in captured.err


@pytest.mark.usefixtures("full_env")
def test_all_missing_variables_reported_together(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    pdf_file: pathlib.Path,
) -> None:
    monkeypatch.delenv(REQUIRED_ENV_VARS[0])
    monkeypatch.delenv(REQUIRED_ENV_VARS[-1])

    code = main(argv=["--file", str(pdf_file)])

    err = capsys.readouterr().err
    assert code == 3
    assert REQUIRED_ENV_VARS[0] in err
    assert REQUIRED_ENV_VARS[-1] in err


@pytest.mark.usefixtures("full_env")
def test_empty_variable_counts_as_missing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    pdf_file: pathlib.Path,
) -> None:
    monkeypatch.setenv("GEMINI_MODEL", "")

    code = main(argv=["--file", str(pdf_file)])

    assert code == 3
    assert "GEMINI_MODEL" in capsys.readouterr().err


@pytest.mark.usefixtures("full_env")
def test_complete_config_has_no_config_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    pdf_file: pathlib.Path,
) -> None:
    _use_chain(monkeypatch, _happy_chain())

    code = main(argv=["--file", str(pdf_file)])

    assert code == 0
    assert "environment variables" not in capsys.readouterr().err


# --- arguments ---


@pytest.mark.parametrize(
    "argv",
    [["--url", "https://fia.com/a.pdf", "--file", "a.pdf"], []],
    ids=["both", "neither"],
)
def test_source_arguments_are_exclusive_and_required(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(argv=argv)

    assert exc_info.value.code == 2


# --- error handling ---


@pytest.mark.usefixtures("full_env")
@pytest.mark.parametrize("exc_type", [DownloadError, ExtractionError, LLMError])
def test_pipeline_errors_exit_1(
    exc_type: type[Exception],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    pdf_file: pathlib.Path,
) -> None:
    def failing_process_document(*args: object, **kwargs: object) -> DocumentSummary:
        raise exc_type("it broke")

    _use_chain(monkeypatch, _happy_chain())
    monkeypatch.setattr(
        "fia_doc_explainer.cli.process_document", failing_process_document
    )

    code = main(argv=["--file", str(pdf_file)])

    captured = capsys.readouterr()
    assert code == 1
    assert "it broke" in captured.err
    assert captured.out == ""


@pytest.mark.usefixtures("full_env")
def test_download_error_exits_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def failing_download(url: str) -> bytes:
        raise DownloadError("404 from server")

    _use_chain(monkeypatch, _happy_chain())
    monkeypatch.setattr("fia_doc_explainer.cli.download_pdf", failing_download)

    code = main(argv=["--url", "https://fia.com/a.pdf"])

    captured = capsys.readouterr()
    assert code == 1
    assert "404 from server" in captured.err
    assert captured.out == ""


@pytest.mark.usefixtures("full_env")
def test_unreadable_file_exits_1_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: pathlib.Path,
) -> None:
    _use_chain(monkeypatch, _happy_chain())

    code = main(argv=["--file", str(tmp_path / "missing.pdf")])

    captured = capsys.readouterr()
    assert code == 1
    assert captured.err != ""
    assert "Traceback" not in captured.err
    assert captured.out == ""


# --- happy path ---


@pytest.mark.usefixtures("full_env")
def test_success_shows_model_and_both_reasons(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: pathlib.Path,
) -> None:
    pdf_bytes = make_pdf_bytes(
        pages=["Stewards Decision 文書番号 42 判定 penalty"], font="Vera"
    )
    path = tmp_path / "bad.pdf"
    path.write_bytes(pdf_bytes)
    primary = FakeProvider(
        model=PRIMARY_MODEL,
        outcome=flag_response(model=PRIMARY_MODEL, reason="unsure about doc type"),
    )
    escalation = FakeProvider(
        model=ESCALATION_MODEL, outcome=summary_response(model=ESCALATION_MODEL)
    )
    _use_chain(monkeypatch, _chain(primary, escalation))

    code = main(argv=["--file", str(path)])

    out = capsys.readouterr().out
    assert code == 0
    assert ESCALATION_MODEL in out
    assert "unsure about doc type" in out
    assert "non-printable" in out


@pytest.mark.usefixtures("full_env")
def test_json_output_is_parseable_and_has_computed_field(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    pdf_file: pathlib.Path,
) -> None:
    _use_chain(monkeypatch, _happy_chain())

    code = main(argv=["--file", str(pdf_file), "--json"])

    data = json.loads(capsys.readouterr().out)
    assert code == 0
    assert data["low_confidence"] is False
    assert data["model_used"] == PRIMARY_MODEL


@pytest.mark.usefixtures("full_env")
def test_file_makes_no_network_call_and_has_no_source_url(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    pdf_file: pathlib.Path,
) -> None:
    download_calls: list[str] = []

    async def recording_download(url: str) -> bytes:
        download_calls.append(url)
        raise AssertionError("--file must not download")

    _use_chain(monkeypatch, _happy_chain())
    monkeypatch.setattr("fia_doc_explainer.cli.download_pdf", recording_download)

    code = main(argv=["--file", str(pdf_file), "--json"])

    data = json.loads(capsys.readouterr().out)
    assert code == 0
    assert download_calls == []
    assert data["source_url"] is None


# --- format_summary ---


def test_paragraphs_are_preserved() -> None:
    first = "First paragraph is short."
    second = "Second paragraph is short too."
    assert len(first) < WRAP_WIDTH and len(second) < WRAP_WIDTH

    out = format_summary(_make_summary(plain_explanation=f"{first}\n\n{second}"))

    assert out.endswith(f"{first}\n\n{second}")


def test_no_line_exceeds_wrap_width() -> None:
    long_text = " ".join(["stewards"] * 60)
    out = format_summary(
        _make_summary(
            plain_explanation=long_text,
            key_facts=[long_text],
            low_confidence_reason=long_text,
            heuristic_reason=long_text,
        )
    )

    assert all(len(line) <= WRAP_WIDTH for line in out.splitlines())
    assert len(out.splitlines()) > 10


@pytest.mark.parametrize(
    ("heuristic_reason", "model_reason", "heuristic_line", "model_line"),
    [
        ("garbled text", None, "  Heuristic: garbled text", "  Model: did not flag"),
        (None, "unsure", "  Heuristic: not triggered", "  Model: unsure"),
    ],
    ids=["heuristic_only", "model_only"],
)
def test_low_confidence_lines(
    heuristic_reason: str | None,
    model_reason: str | None,
    heuristic_line: str,
    model_line: str,
) -> None:
    out = format_summary(
        _make_summary(
            heuristic_reason=heuristic_reason, low_confidence_reason=model_reason
        )
    )

    lines = out.splitlines()
    assert "LOW CONFIDENCE" in lines
    assert heuristic_line in lines
    assert model_line in lines


def test_no_low_confidence_block_when_confident() -> None:
    assert "LOW CONFIDENCE" not in format_summary(_make_summary())
