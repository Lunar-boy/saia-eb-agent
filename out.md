# SAIA EB Agent Report

## Request Summary
- **software**: DMTCP
- **version**: 4.0.0
- **cluster**: barnard
- **release**: r2026
- **gpu**: False
- **preferred_toolchain**: None
- **keywords**: []

## Candidate Selection
- 1. `DMTCP-4.0.0-GCCcore-14.2.0.eb` (score=90.0)
  - reasons: exact software name match, exact version match, CPU/GPU intent appears aligned
- 2. `DMTCP-4.0.0-GCCcore-14.3.0.eb` (score=90.0)
  - reasons: exact software name match, exact version match, CPU/GPU intent appears aligned
- 3. `DMTCP-3.0.0-GCCcore-11.3.0.eb` (score=60.0)
  - reasons: exact software name match, CPU/GPU intent appears aligned
  - risk: exact requested version not found
- 4. `DMTCP-3.0.0-GCCcore-12.2.0.eb` (score=60.0)
  - reasons: exact software name match, CPU/GPU intent appears aligned
  - risk: exact requested version not found
- 5. `DMTCP-3.0.0-GCCcore-12.3.0.eb` (score=60.0)
  - reasons: exact software name match, CPU/GPU intent appears aligned
  - risk: exact requested version not found

## Validation
- Result: PASS
- [info] duplicate.near: found 6 near-duplicate(s) with same software stem

## Operations
- copy /home/nate/.cache/saia-eb-agent/easybuild-easyconfigs/easybuild/easyconfigs/d/DMTCP/DMTCP-4.0.0-GCCcore-14.2.0.eb -> /home/nate/Desktop/barnard-ci/easyconfigs/barnard/r2026/DMTCP-4.0.0-GCCcore-14.2.0.eb
- write applied (--apply enabled)

## MR Artifacts
- **branch_name**: easyconfig/barnard/r2026/dmtcp-4.0.0
- **issue_title**: Add DMTCP 4.0.0 easyconfig for barnard/r2026
- **commit_message**: easyconfigs: add DMTCP-4.0.0 for barnard/r2026 (GCCcore-14.2.0)
- **mr_title**: [barnard/r2026] Add DMTCP 4.0.0 easyconfig
- **mr_description**: Summary:
- Adds DMTCP-4.0.0-GCCcore-14.2.0.eb to easyconfigs/barnard/r2026/

Checklist:
- [ ] Local static validation reviewed
- [ ] GPU/CPU placement policy validated
- [ ] Draft MR opened first
- [ ] HPC CI build passed


## HPC Follow-Up
- Local checks are heuristic only and do not replace HPC CI EasyBuild execution.
- Open Draft MR first, validate with HPC CI, then promote to non-draft after review.