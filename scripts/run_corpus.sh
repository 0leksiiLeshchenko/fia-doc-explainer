#!/usr/bin/env bash
set -u

n=${1:-1}
if ! [[ $n =~ ^[1-9][0-9]*$ ]]; then
    echo "usage: $0 [N]  (N: positive integer, runs per document)" >&2
    exit 2
fi

if ! command -v jq >/dev/null 2>&1; then
    echo "jq is required but not found" >&2
    exit 2
fi

cd "$(dirname "$0")/.." || exit 2

# runs/ is excluded: it holds the results of earlier runs. Anywhere else, a
# change means the commit hash would not describe the code that actually ran.
dirty=$(git status --porcelain --untracked-files=all -- . ':(exclude)runs')
rc=$?
if [ $rc -ne 0 ]; then
    echo "git status failed (exit $rc)" >&2
    exit 2
fi
if [ -n "$dirty" ]; then
    echo "Working tree has changes outside runs/; commit or stash them first:" >&2
    echo "$dirty" >&2
    exit 2
fi

rev=$(git rev-parse --short HEAD) || exit 2
start=$(date +%s)
stamp=$(date -u -d "@$start" +%Y%m%dT%H%M%SZ)
started_at=$(date -u -d "@$start" +%Y-%m-%dT%H:%M:%SZ)
outdir="runs/corpus-$rev-$stamp"

if [ -e "$outdir" ]; then
    echo "$outdir already exists" >&2
    exit 2
fi

# The CLI calls load_dotenv() without override: a variable already in the
# environment (even empty) wins over .env. Read .env with the same parser.
model_vars=(ANTHROPIC_PRIMARY_MODEL ANTHROPIC_ESCALATION_MODEL GEMINI_MODEL)
dotenv_json=$(uv run python -c '
import json, sys
from dotenv import dotenv_values
values = dotenv_values(sys.argv[1])
print(json.dumps({k: values.get(k) or "" for k in sys.argv[2:]}))
' "$PWD/.env" "${model_vars[@]}") || { echo "could not read .env" >&2; exit 2; }

model_value() {
    if [ -n "${!1+x}" ]; then
        printf '%s' "${!1}"
    else
        jq -r --arg k "$1" '.[$k] // ""' <<<"$dotenv_json"
    fi
}

mkdir "$outdir" || exit 2

jq -n \
    --arg rev "$rev" \
    --arg started_at "$started_at" \
    --argjson runs "$n" \
    --arg primary "$(model_value ANTHROPIC_PRIMARY_MODEL)" \
    --arg escalation "$(model_value ANTHROPIC_ESCALATION_MODEL)" \
    --arg gemini "$(model_value GEMINI_MODEL)" \
    '{rev: $rev, started_at: $started_at, runs_per_document: $runs,
      ANTHROPIC_PRIMARY_MODEL: $primary,
      ANTHROPIC_ESCALATION_MODEL: $escalation,
      GEMINI_MODEL: $gemini}' >"$outdir/manifest.json" || exit 2

failures="$outdir/failures.txt"
summaries="$outdir/summaries.jsonl"
calls=0
cli_failures=0
wrap_failures=0
ok_list=()

for pdf in tests/corpus/*.pdf; do
    stem=$(basename "$pdf" .pdf)
    for ((k = 1; k <= n; k++)); do
        base="$outdir/$stem-run$k"
        calls=$((calls + 1))
        uv run fia-doc-explainer --file "$pdf" --json >"$base.json" 2>"$base.err"
        code=$?
        if [ $code -ne 0 ]; then
            echo "$stem run$k stage=cli exit=$code" >>"$failures"
            rm -f "$base.json"
            cli_failures=$((cli_failures + 1))
        else
            ok_list+=("$stem:$k")
        fi
    done
done

# Separate step, from files on disk: the raw model response is already saved,
# so a failing wrapper cannot lose it.
for item in "${ok_list[@]}"; do
    stem=${item%:*}
    k=${item##*:}
    line=$(jq -c \
        --arg file "$stem.pdf" --arg rev "$rev" --argjson run "$k" \
        '{file: $file, rev: $rev, run: $run, summary: .}' \
        "$outdir/$stem-run$k.json")
    code=$?
    if [ $code -ne 0 ]; then
        echo "$stem run$k stage=wrap exit=$code" >>"$failures"
        wrap_failures=$((wrap_failures + 1))
    else
        printf '%s\n' "$line" >>"$summaries"
    fi
done

find "$outdir" -name '*.err' -empty -delete

failed=$((cli_failures + wrap_failures))
echo "Run directory: $outdir"
echo "Calls: $calls"
echo "Successful: $((calls - failed))"
echo "Failures: stage=cli $cli_failures, stage=wrap $wrap_failures"

[ $failed -eq 0 ] || exit 1
exit 0
