# PlaySpec

Regression platform with agentic test generation for Playwright.

PlaySpec has two operating modes:

- **Regression Mode** — deterministic Playwright E2E test execution for CI. No LLM, no external APIs, no repo mutation. Pure test runner driven by a regression manifest.
- **Author Mode** — AI-assisted Playwright test generation from JIRA, Confluence, Figma, and copy decks. Uses pluggable agent backends (GitHub Copilot CLI, OpenCode, Claude Code).

## Quick Start

```bash
pip install playspec
playspec init
```

This creates a `.playspec/` directory with:

- `config.yaml` — execution profiles, backend settings, audit configuration
- `regression-manifest.yaml` — suite definitions, quarantine list, hooks
- `audits/` — immutable run records
- `runs/` — test artifacts per run

## Regression Mode

Run tests against the manifest:

```bash
# Run smoke suite
playspec regress --suite smoke

# Run multiple suites
playspec regress --suite smoke --suite checkout

# Run tests tagged with a JIRA key
playspec regress --jira PROJ-1234

# Auto-detect changed files from git diff
playspec regress --changed-files

# Use a specific profile
playspec regress --suite smoke --profile pr-ci --base-url https://preview.example.com
```

### The Immutability Rule

Regression mode **never** mutates the repo. It never auto-repairs tests. It never weakens assertions. It reports failures or it is broken.

## Author Mode

Generate comprehensive Playwright tests from your specs:

```bash
# Full pipeline: gather context → plan → generate → execute → repair
playspec author --jira PROJ-1234 --figma https://figma.com/file/abc123

# With additional context sources
playspec author --jira PROJ-1234 --confluence https://wiki.example.com/pages/12345 --copy-deck copy.yaml

# Plan only (no generation)
playspec plan --jira PROJ-1234 --export-json plan.json
```

## Inspection & Management

```bash
# View test inventory
playspec inspect tests

# View suite configuration
playspec inspect suites

# Check JIRA coverage
playspec inspect coverage --jira PROJ-1234

# Manage quarantined tests
playspec quarantine list
playspec quarantine add tests/e2e/flaky.spec.ts --reason "Intermittent timeout"
playspec quarantine remove tests/e2e/flaky.spec.ts

# View audit trail
playspec audit list
playspec audit show ps-20260315-120000-abcd1234
playspec audit diff ps-run-a ps-run-b
playspec audit export ps-run-a --format md

# Check integration availability
playspec auth-check
```

## Configuration

### .playspec/config.yaml

```yaml
test_dir: tests/e2e
page_objects_dir: tests/e2e/pages
fixtures_dir: tests/e2e/fixtures
naming_convention: kebab-case
max_retries: 3

agent_backend:
  priority: [copilot, opencode, claudecode]
  copilot:
    mode: cli
  opencode:
    mode: cli
  claudecode:
    mode: cli

profiles:
  local-dev:
    base_url: http://localhost:3000
    browsers: [chromium]
    parallelism: 2
    headed: true
    repair_policy: propose
    artifact_retention: 7d
    generation_allowed: true

  pr-ci:
    base_url: $PREVIEW_URL
    browsers: [chromium]
    parallelism: 4
    headed: false
    repair_policy: never
    artifact_retention: 30d
    generation_allowed: false
    suggested_fixes: true

  nightly:
    base_url: https://staging.example.com
    browsers: [chromium, firefox, webkit]
    parallelism: 8
    headed: false
    repair_policy: never
    artifact_retention: 90d
    flaky_detection: true

  release:
    base_url: https://uat.example.com
    browsers: [chromium, firefox, webkit]
    parallelism: 4
    headed: false
    repair_policy: never
    artifact_retention: 365d
    blocking: true

audit:
  enabled: true
  output_dir: .playspec/audits
  retention_days: 90
  include_prompts: true
  include_responses: true
```

### .playspec/regression-manifest.yaml

```yaml
suites:
  smoke:
    description: Critical path validation, runs on every PR
    timeout_minutes: 10
    tags: [smoke, p0]
    blocking: true
    browsers: [chromium]
    parallelism: 4

  full:
    description: Complete regression, runs nightly
    timeout_minutes: 60
    tags: [regression]
    blocking: false
    browsers: [chromium, firefox, webkit]
    parallelism: 8

quarantine:
  - tests/e2e/flaky-animation.spec.ts

hooks:
  checkout:
    setup: scripts/seed-checkout-data.sh
    teardown: scripts/cleanup-checkout-data.sh
```

### Test File Tags

PlaySpec reads annotation comments from the header of `.spec.ts` files:

```typescript
// @tags: smoke, p0, regression, auth
// @jira: PROJ-1234
// @owner: team-checkout
// @generated: playspec-v1

import { test, expect } from '@playwright/test';
```

## CI Integration

### GitHub Actions

```yaml
name: PlaySpec Regression
on:
  pull_request:
    types: [opened, synchronize]

jobs:
  regression:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 20 }
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }

      - run: pip install playspec
      - run: npx playwright install --with-deps chromium

      - run: playspec regress --suite smoke --profile pr-ci --base-url $PREVIEW_URL
        env:
          PREVIEW_URL: ${{ steps.deploy.outputs.url }}

      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: playspec-results
          path: .playspec/runs/
```

### Azure Pipelines

```yaml
trigger:
  branches:
    include: [main]

pool:
  vmImage: ubuntu-latest

steps:
  - task: UsePythonVersion@0
    inputs: { versionSpec: '3.11' }

  - task: NodeTool@0
    inputs: { versionSpec: '20' }

  - script: |
      pip install playspec
      npx playwright install --with-deps chromium
    displayName: Install dependencies

  - script: playspec regress --suite smoke --suite checkout --profile pr-ci
    displayName: Run regression

  - task: PublishBuildArtifacts@1
    condition: always()
    inputs:
      pathToPublish: .playspec/runs
      artifactName: playspec-results
```

## Development

```bash
# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --tb=short
```

## Architecture

```
playspec/
├── cli.py              # Typer CLI with all commands
├── config.py           # Config loader (.playspec/config.yaml)
├── manifest.py         # Manifest loader and suite resolver
├── stability.py        # Per-test pass/fail history and flaky detection
├── regression.py       # Regression mode pipeline
├── author_pipeline.py  # Author mode pipeline
├── audit.py            # Audit trail management
├── run_id.py           # Unique run ID generation
├── console.py          # Shared Rich console
├── schemas/            # Pydantic v2 data contracts
│   ├── uts.py          # Unified Test Specification
│   ├── test_plan.py    # Test plan from planner agent
│   ├── execution_result.py
│   ├── audit_entry.py
│   ├── manifest_schema.py
│   └── suggested_fix.py
├── executor/           # Playwright execution engine
│   ├── runner.py       # Shells out to npx playwright test
│   ├── artifact_capture.py
│   └── diagnostics.py  # Failure classification
├── backends/           # Agent backend abstraction
│   ├── base.py         # Abstract base class
│   ├── copilot.py      # GitHub Copilot CLI
│   ├── opencode.py     # OpenCode CLI
│   └── claudecode.py   # Claude Code CLI
├── integrations/       # External service clients
│   ├── git_client.py
│   ├── jira_client.py
│   ├── confluence_client.py
│   └── figma_client.py
├── agents/             # Agent orchestration
│   ├── context_agent.py
│   ├── planner_agent.py
│   ├── generator_agent.py
│   └── repair_agent.py
├── parsers/            # Data extraction
│   ├── figma_tree.py
│   ├── copy_deck.py
│   └── codebase_scanner.py
└── prompts/            # Prompt templates (Markdown + Jinja2 variables)
    ├── context.md
    ├── planner.md
    ├── generator.md
    └── repair.md
```
