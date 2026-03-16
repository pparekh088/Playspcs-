# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**PlaySpec** is a regression platform with agentic test generation for Playwright. Two modes:
- **Regression Mode**: Deterministic Playwright E2E execution for CI — never mutates test files, never auto-repairs
- **Author Mode**: AI-assisted test generation from JIRA/Confluence/Figma using pluggable agent backends (claudecode, opencode, copilot)

## Commands

### Python (core package)
```bash
pip install -e ".[dev]"              # Install editable with dev deps
pytest tests/ -v                     # Run all Python unit tests
pytest tests/test_config.py -v       # Run a single test file
playspec regress --suite smoke       # Run regression suite
playspec author --jira PROJ-1234     # Run author pipeline
playspec inspect tests               # List tests with tags/stability
```

### Playwright (E2E tests)
```bash
npm test                             # Run all Playwright tests
npx playwright test                  # Same as above
npx playwright test --headed         # Headed mode
npx playwright test login.spec.ts    # Run a single spec
python3 example-app/serve.py         # Start example app server (port 3000)
npx playwright install --with-deps   # Install browsers (first-time setup)
```

## Architecture

### Core Python Package (`playspec/`)
- **CLI** (`cli.py`): Typer-based command routing — `regress`, `author`, `inspect`, `quarantine`, `audit`, `report`
- **Config** (`config.py`): Loads `.playspec/config.yaml`, Pydantic validation, env var interpolation
- **Manifest** (`manifest.py`): Suite definitions from `.playspec/regression-manifest.yaml`, resolves test files by tags/JIRA keys
- **Regression pipeline** (`regression.py`): Execute → classify failures → track stability → post to JIRA → auto-file bugs
- **Author pipeline** (`author_pipeline.py`): Context gather → plan → generate → execute → repair loop

### Key Data Flow
1. **Schemas** (`schemas/`): Pydantic v2 contracts — `UnifiedTestSpec` (UTS) is the canonical intermediate format between context gathering and code generation
2. **Executor** (`executor/runner.py`): Shells out to `npx playwright test --reporter=json`, parses results into `ExecutionResult`
3. **Backends** (`backends/`): Abstract `AgentBackend` base class with implementations for Claude Code, OpenCode, GitHub Copilot CLI
4. **Integrations** (`integrations/`): HTTP clients for JIRA, Confluence, Figma, Git

### Test Annotations
Playwright test files use comment annotations for traceability:
```typescript
// @tags: smoke, crud, auth
// @jira: PLAY-2
// @owner: team-qa
// @generated: playspec-v1
```

### Configuration
- `.playspec/config.yaml` — main config with profiles (`local-dev`, `pr-ci`, `nightly`, `release`)
- `.playspec/regression-manifest.yaml` — suite definitions, quarantine list, hooks
- `.playspec/stability.json` — per-test pass/fail history for flaky detection
- `.playspec/audits/` — immutable audit trail records
- `playwright.config.ts` — Playwright config (testDir: `./example-app/tests`, baseURL: `http://localhost:3000`)

### Environment Variables
Required in `.env` for integrations: `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `FIGMA_API_TOKEN`

## Key Design Rules
- **Immutability in regression mode**: Regression NEVER mutates test files or auto-repairs — it only reports
- **Flaky detection**: Tests with <50% pass rate after 5 runs get auto-quarantined
- **Agent backend fallback**: Tries backends in priority order from config (default: claudecode → opencode → copilot)

## Known Issues (from CODE_REVIEW.md)
- `regression.py` uses `typer.Exit()` but typer may not be imported in that scope
- Playwright JSON reporter needs `--reporter=json:path` to write to file (not stdout)
- `stability.py` only records failures, not passes — flaky scoring unreliable
