# saia-eb-agent

`saia-eb-agent` is a local, review-first assistant for preparing EasyBuild easyconfig changes for HPC CI repositories.

It is designed for workflows where EasyBuild can only run on HPC CI, not on the local laptop/workstation.

## Purpose

This project helps with:
- upstream candidate discovery from `easybuild-easyconfigs`
- policy-driven cluster placement checks
- static local validation
- safe patch preparation for `barnard-ci`
- MR-ready text generation

This project does **not** run real EasyBuild builds locally.

## Safety Model

Default behavior is safe and non-mutating:
- no `git push`
- no MR creation
- no merge
- no file writes unless `--apply` is explicitly provided

Every mutating action is explicit and inspectable.

## Architecture

- `providers/`: LLM provider abstraction + SAIA provider
- `repos/`: upstream easybuild + local barnard-ci adapters
- `parsing/`: filename + easyconfig text metadata extraction
- `policy/`: placement and dependency-domain policy
- `ranking/`: candidate scoring and heuristic ranking
- `validation/`: static local checks and policy checks
- `workflows/`: search/recommend/apply/prepare-mr orchestration
- `reporting/`: Markdown report generation
- `cli.py`: Typer CLI entrypoint

## Requirements

- Python 3.11+
- Git

## Install

```bash
cd /saia-eb-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

## Configuration

Copy and edit examples:

```bash
cp .env.example .env
cp config/policy.example.yaml config/policy.yaml
cp config/settings.example.yaml config/settings.yaml
```

Environment variables for SAIA provider:
- `SAIA_API_KEY`
- `SAIA_BASE_URL`
- `SAIA_MODEL`

If `SAIA_API_KEY` is unset, the tool runs in rule-only mode.

## CLI Commands

```bash
saia-eb-agent search --software GROMACS --version 2024.4 --cluster alpha --release r24.10 --gpu --refresh-upstream
```

```bash
saia-eb-agent recommend --software Foo --version 2024.4 --cluster capella --release r25.06 --report out.md
```

```bash
saia-eb-agent validate --file /path/to/Foo-1.2.3-GCC-13.2.0.eb --cluster romeo --release r24.10 --barnard-ci /path/to/barnard-ci
```

```bash
saia-eb-agent apply --software Foo --version 1.2.3 --cluster capella --release r25.06 --barnard-ci /path/to/barnard-ci --apply --report out.md
```

```bash
saia-eb-agent prepare-mr --file /path/to/Foo-1.2.3-GCC-13.2.0.eb --cluster capella --release r25.06
```

## Encoded Policy

Default policy (customizable via YAML):
- GPU clusters: `alpha`, `capella`
- CPU clusters: `romeo`, `barnard`, `julia`, `capella`
- Forbidden GPU clusters: `romeo`, `barnard`, `julia`
- Shared install domain: `alpha + romeo`
- If target cluster is `alpha`, dependency domain includes `romeo`

## Static Validation Checks

Implemented checks include:
- target path structure (`easyconfigs/<cluster>/<release>/`)
- release folder existence
- filename vs extracted metadata consistency
- GPU/CUDA placement policy
- absolute `/software/util/sources` rejection
- suspicious markers: `CUDA`, `NVHPC`, `gompic`, `nvompi`, hardcoded site-like paths
- duplicate and near-duplicate detection against local barnard-ci checkout

## Limitations

- No local EasyBuild dry-run or full semantic easyconfig evaluation
- Parsing is heuristic and text-based for safety and portability
- Ranking is heuristic and should be reviewed before apply
- SAIA API schema is assumed OpenAI-compatible (`/chat/completions`)

## What Must Still Be Verified on HPC CI

- actual EasyBuild resolution and build success
- runtime/module behavior on target architecture
- dependency closure in real shared filesystem domain
- final CI pipeline and merge gating outcome

Use Draft MR first, then convert after successful HPC CI and review.

## Tests

Run:

```bash
pytest
```

Coverage targets key logic:
- filename parsing
- easyconfig metadata extraction
- policy engine behavior
- ranking heuristics
- static validation checks
- apply workflow in temporary repos
