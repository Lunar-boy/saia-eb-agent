# saia-eb-agent

`saia-eb-agent` is a local, review-first assistant for preparing EasyBuild easyconfig changes for HPC CI repositories.

It is designed for workflows where EasyBuild can only run on HPC CI, not on the local laptop/workstation.

## Purpose

This project helps with:
- upstream candidate discovery from `easybuild-easyconfigs`
- policy-driven cluster placement checks
- static local validation
- safe patch preparation for `cicd`
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
set -a
source .env
set +a
```

Toolchain resolution and ranking are deterministic and local (no external LLM dependency).

## CLI Commands

```bash
saia-eb-agent search --software GROMACS --tc GCC14.2.0
```

```bash
saia-eb-agent search --software GROMACS --tc foss2025a --cluster gpu
```

```bash
saia-eb-agent apply --software GROMACS --tc foss2025a --cluster gpu --release r25.06 --barnard-ci /path/to/barnard-ci --apply
```

```bash
saia-eb-agent guide
```

```bash
saia-eb-agent memory show
```

```bash
saia-eb-agent memory set-barnard-ci /path/to/barnard-ci
```

```bash
saia-eb-agent validate --file /path/to/Foo-1.2.3-GCC-13.2.0.eb --cluster romeo --release r24.10 --barnard-ci /path/to/barnard-ci
```

```bash
saia-eb-agent prepare-mr --file /path/to/Foo-1.2.3-GCC-13.2.0.eb --cluster romeo --release r25.06
```

### Search behavior changes

- Search no longer accepts `--version`, `--release`, `--gpu`, or `--refresh-upstream`.
- Search auto-refreshes upstream easyconfigs automatically (unless `--local-upstream` is used).
- Toolchain query uses `--tc` and resolves family equivalents (for example `GCC14.2.0` may match `GCC-14.2.0`, `GCCcore-14.2.0`, `foss-2025a`, `gfbf-2025a`).
- `--tc system` is supported. For `system` toolchain queries, newest matching EasyConfig versions are preferred deterministically.
- Search output includes toolchain match rationale and patch visibility (`found/declared`).

### Target cluster abstraction

- User-facing `--cluster` is now target kind: `cpu` or `gpu`.
- `cpu` expands to all CPU clusters from policy.
- `gpu` expands to all GPU clusters from policy.
- Apply/validation summary is reported per concrete cluster.

### Guided mode

- `saia-eb-agent guide` (or `saia-eb-agent agent`) runs the full pipeline automatically:
1. collect missing parameters via English prompts
2. search
3. recommend/select best candidate
4. validate on all expanded target clusters
5. apply (if enabled)
6. prepare MR artifacts

- Guided mode remembers session values inside one run.

### Persistent memory

- Stored at `~/.config/saia-eb-agent/state.json` (schema versioned).
- Remembers:
- `remembered_barnard_ci_path`
- `last_release`
- `release_history`
- last target kind/toolchain query hints
- Release reuse prompt:
- `Last release was r25.06. Press Enter to reuse it, or type a new release:`
- Memory commands:
- `saia-eb-agent memory show`
- `saia-eb-agent memory set-barnard-ci /path/to/barnard-ci`
- `saia-eb-agent memory clear`

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
- No external LLM-based expansion is used; toolchain resolution is rule-based and offline.

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
- toolchain normalization/alias expansion
- search auto-refresh behavior
- patch extraction/resolution metadata
- multi-cluster apply and validation aggregation
- persistent state load/save
- guided workflow path
- static validation checks
- apply workflow in temporary repos
