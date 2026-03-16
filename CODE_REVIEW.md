# PlaySpec Code Review

**Branch reviewed:** `main` (commits `8df7e7f` through `5274abb`)
**Plan reviewed:** PlaySpec Agent Build Plan & System Prompt (all 9 phases)
**Reviewer:** Claude Code
**Date:** 2026-03-15

---

## Summary

The implementation covers all 9 phases and the file structure is solid. The
Pydantic schema design, CLI layout, and separation of regression vs. author mode
are well-executed. However, there are **7 critical bugs** that will prevent the
tool from functioning correctly at all, plus a set of medium and minor issues
documented below.

---

## Critical Bugs (will cause runtime failures)

### 1. `typer` not imported in `regression.py` — `NameError` at startup

**File:** `playspec/regression.py:46`

```python
raise typer.Exit(code=1)   # typer is never imported in this file
```

The repair-policy guard runs every time `playspec regress` is invoked. Because
`typer` is never imported, any regression run on a profile whose
`repair_policy` is not `"never"` crashes immediately with `NameError`.

**Fix:** Replace `raise typer.Exit(code=1)` with `raise SystemExit(1)` (already
used at line 124), or add `import typer` at the top of the file.

---

### 2. Playwright JSON report is never written to a file — all results lost

**File:** `playspec/executor/runner.py:36, 59-62, 75`

```python
json_report = run_dir / "results.json"
cmd = _build_command(test_files, profile, run_dir, json_report)
...
if json_report.is_file():
    return _parse_json_report(json_report, run_id)
```

`_build_command` emits `--reporter=json`. In Playwright, `--reporter=json`
prints JSON to **stdout**, not to a file. `json_report` is computed and passed
to `_build_command` but the function never uses it in the command. The file is
therefore never created, so the code always falls through to the exit-code
fallback `_parse_exit_code()`, losing all granular test data.

**Fix:** Change the reporter flag to `f"--reporter=json:{json_report}"` (Playwright
supports `reporter:outputPath` syntax), or redirect stdout to the file.

---

### 3. `StabilityStore.update()` never records passing tests

**File:** `playspec/stability.py:60-73`

```python
def update(self, result: ExecutionResult) -> int:
    updates = 0
    passed_tests = set()          # created but never populated
    for f in result.failures:
        rec = self.records.setdefault(key, TestStabilityRecord())
        rec.record_fail()
        updates += 1
        passed_tests.discard(key) # discard from an empty set — no-op

    failed_keys = {f"{f.test_file}::{f.test_name}" for f in result.failures}
    # failed_keys is never used
    return updates
```

Passing tests are never recorded. `pass_count`, `last_passed_at`, and
`last_known_good_run_id` are never updated. The flaky score can only ever
decrease — a test that recovers never gets `True` entries in `last_n_results`
so its score stays low indefinitely. The `recommend_quarantine()` threshold
logic is therefore unreliable.

**Root cause gap:** `ExecutionResult` only stores failures, not passing test
names. A list of passing test identifiers needs to be added to
`ExecutionResult`, or the runner must emit them from the JSON report.

---

### 4. `local-dev` profile blocks all local regression runs

**Files:** `playspec/regression.py:44-46`, `playspec/init_cmd.py:34`

`playspec init` creates a `local-dev` profile with `repair_policy: propose`.
`_auto_detect_profile()` returns `None` outside CI, causing `get_profile()` to
fall back to `local-dev`. The hard check at line 44 then aborts every local
regression run:

```python
if profile.repair_policy != RepairPolicy.NEVER:
    console.print("[bold red]ERROR:[/bold red] Regression mode requires repair_policy='never'. Aborting.")
    raise typer.Exit(code=1)   # also hits bug #1
```

A developer who runs `playspec regress --suite smoke` locally with the default
generated config will always get this error.

**Fix:** Either update the `local-dev` default profile in `init_cmd.py` to use
`repair_policy: never`, or enforce the repair_policy check only when the
auto-detected profile is a CI profile.

---

### 5. Copilot backend uses wrong CLI sub-command for code generation

**File:** `playspec/backends/copilot.py:44-46`

```python
proc = subprocess.run(
    ["gh", "copilot", "suggest", "-t", "shell", prompt],
    ...
)
```

`gh copilot suggest -t shell` is the *shell command suggestion* sub-command.
It is designed to suggest one-line shell commands, not to generate TypeScript
test files. Sending a 1,000-token prompt for Playwright test generation to
this endpoint will not work as intended and may be rejected or produce garbage
output.

The `gh copilot explain` command and the Copilot API do not have a direct
equivalent in the `gh copilot` CLI for general code generation. This backend
as written cannot fulfil the author-mode use case.

**Fix:** Either document that Copilot is only viable for shell-level hints and
use OpenCode/Claude as the primary author-mode backends, or switch to the
Copilot REST API (requires token, not just CLI).

---

### 6. Temp file created in `CopilotBackend.invoke()` but never deleted

**File:** `playspec/backends/copilot.py:39-41`

```python
with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
    f.write(prompt)
    prompt_file = f.name
# prompt_file is set but never passed to the command and never deleted
```

The temp file leaks on every invocation. With `delete=False`, Python does not
clean it up automatically.

**Fix:** Remove the dead code block entirely (the prompt is already passed
directly on line 44), or use it and delete after the subprocess call.

---

### 7. Repair loop does not actually retry — always breaks after attempt 1

**File:** `playspec/agents/repair_agent.py:59-68`

```python
for attempt in range(1, max_retries + 1):
    console.print(f"  Attempt {attempt}/{max_retries}…")
    response = backend.invoke(prompt)
    patch_file = repairs_dir / f"{test_path.stem}-attempt{attempt}.patch"
    patch_file.write_text(response.content, encoding="utf-8")
    console.print(f"  [yellow]Patch staged for review (not auto-applied).[/yellow]")
    break   # always breaks — loop is effectively max_retries=1
```

The plan describes a feedback loop: apply patch → re-run test → if pass stage
it, if fail retry. The implementation skips the re-run entirely and always
breaks after the first attempt regardless of `max_retries`. The `--max-retries`
flag is therefore a no-op.

**Fix:** Apply the patch to a temp copy, re-run only the affected test, check
the result, and only break on success (or exhaust retries on continued failure).

---

## Medium Issues

### 8. `--reporter=json` timeout scales with parallelism instead of suite timeout

**File:** `playspec/executor/runner.py:46`

```python
timeout=profile.parallelism * 600,
```

This sets a total process timeout of `workers × 10 minutes`. With 8 workers
that is 80 minutes; with 2 workers it is 20 minutes. More workers should
produce *shorter* wall-clock runtime, not longer timeouts. The correct source
for timeout is the suite's `timeout_minutes` field.

**Fix:** Pass the manifest suite's `timeout_minutes` into `run_tests()`, or use
a reasonable fixed maximum (e.g., 30 minutes), not a parallelism multiple.

---

### 9. `base_url: $PREVIEW_URL` is never interpolated

**File:** `playspec/init_cmd.py:42`, `playspec/config.py`

The `pr-ci` profile default sets `base_url: "$PREVIEW_URL"`. PyYAML loads this
as the literal string `"$PREVIEW_URL"`. No environment variable substitution is
implemented anywhere in `config.py`. CI runs against the literal string, not the
preview deployment URL.

**Fix:** Add env-var interpolation in `load_config()` using a regex like
`re.sub(r'\$(\w+)', lambda m: os.getenv(m.group(1), m.group(0)), value)` for
string fields.

---

### 10. `resolve_changed_files` uses overly broad basename matching

**File:** `playspec/manifest.py:48-57`

```python
changed_basenames = {Path(f).stem for f in changed_files}
for tf in test_root.rglob("*.spec.ts"):
    for basename in changed_basenames:
        if basename in content:   # substring match, not import statement
```

A changed file named `button.tsx` (stem: `button`) matches any test file
containing the string `"button"` — which could be most UI tests. The plan
specifies "test files that **import or reference** changed source files". The
implementation should search for import/require statements instead.

**Fix:** Use a regex like `r"(?:import|from)\s+['\"].*?{stem}['\"]"` or check
for `from '../{stem}'` patterns to avoid false positives.

---

### 11. `auth.jira = "cli"` config is ignored — always reads `JIRA_TOKEN` env var

**File:** `playspec/integrations/jira_client.py:56-64`

```python
def _resolve_token(config: PlaySpecConfig) -> str:
    token = os.getenv("JIRA_TOKEN", "")
    if not token:
        raise RuntimeError("JIRA_TOKEN env var is not set. ...")
    return token
```

The `config.auth.jira` field (which can be `cli` or `env`) is passed in but
never consulted. The `cli` auth path (via `atlas auth`) is not implemented.
The error message even references `atlas auth login` as an alternative but the
code never tries it.

---

### 12. `--apply-fixes` flag is accepted but not implemented

**File:** `playspec/cli.py:84`, `playspec/author_pipeline.py:36`

`run_author()` accepts `apply_fixes_run_id` but never uses it:

```python
def run_author(
    ...
    apply_fixes_run_id: str | None = None,
) -> None:
    ...
    # apply_fixes_run_id is never referenced in the function body
```

---

### 13. `QuarantineEntry` schema is defined but the manifest uses `list[str]`

**File:** `playspec/schemas/manifest_schema.py:28-34, 49`

`QuarantineEntry` has `path`, `reason`, and `added_at` fields, but
`RegressionManifest.quarantine` is `list[str]`. `quarantine add --reason` in
`quarantine_cmd.py` appends a plain string (ignoring the reason), making the
`QuarantineEntry` model dead code and the `--reason` flag lossy.

**Fix:** Either change `quarantine` to `list[QuarantineEntry]` and update
`quarantine_cmd.py` to build proper entries, or remove `QuarantineEntry`.

---

### 14. `playspec regress` environment reachability check not implemented

**Plan:** Phase 4 step e — "Check environment: verify base_url is reachable
(httpx HEAD request with timeout)"

**File:** `playspec/regression.py` — no such check exists.

This means a CI run against a preview URL that never deployed will run the full
test suite, time out every test, and produce an undifferentiated failure report
with no indication that the environment was unreachable.

---

### 15. `suggested-fixes.json` is not persisted to disk

**Plan:** Phase 4 step i — "Generate suggested-fixes.json (diagnostic only, not applied)"

**File:** `playspec/regression.py:100`

```python
suggested = generate_suggested_fixes(result)
```

The suggested fixes are generated in memory and passed to `_print_summary()` for
the count display, but they are never written to `.playspec/runs/<run-id>/`. The
runner creates the run directory and writes `stderr.log`, but no
`suggested-fixes.json` is produced.

---

### 16. Playwright JSON report parsing doesn't recurse into nested suites

**File:** `playspec/executor/runner.py:105-125`

```python
for suite in suites:
    for spec in suite.get("specs", []):
        for test in spec.get("tests", []):
```

Playwright's JSON reporter has the structure:
`suites[].suites[].specs[].tests[]` (nested describe blocks each produce a child
suite). The parser only goes one level deep so tests inside `test.describe()`
blocks are silently dropped. In practice, almost all generated tests use nested
describes.

**Fix:** Recurse into `suite.get("suites", [])` at each level.

---

### 17. Profile mutation instead of copy

**File:** `playspec/regression.py:48-49`

```python
if base_url_override:
    profile.base_url = base_url_override
```

`ExecutionProfile` is a mutable Pydantic model. Mutating it in place means the
change persists for the lifetime of the object. Use
`profile = profile.model_copy(update={"base_url": base_url_override})` to avoid
accidental mutation.

---

### 18. `StabilityStore.update()` `updates` return value is misleading

**File:** `playspec/stability.py:60-73`

`updates` only counts failures, not passes. In `regression.py:117`, this count
is stored as `stability_updates` in the audit record. A run with 100 passing
tests and 0 failures will record `stability_updates=0`, giving the false
impression that stability tracking did nothing.

---

### 19. `copilot.py` does not read `context` argument

**File:** `playspec/backends/copilot.py:35`, `playspec/backends/claudecode.py:34`

Both `invoke(prompt, context)` signatures accept `context: dict | None = None`
as defined in the base class, but neither backend uses it. Callers in
`context_agent.py` do not pass extra context, so this is harmless today, but if
the context dict is ever used by callers it will be silently dropped.

---

### 20. Missing `playspec inspect tests` stability columns

**File:** `playspec/inspect_cmd.py` (not read in detail — based on module summary)

The plan specifies that `inspect tests` shows "stability stats" and "quarantine
status" per test. Review the implementation to confirm stability data is loaded
from `stability.json` and displayed. The `StabilityStore.update()` bug (#3)
means even if the column exists, its data will be stale.

---

## Minor / Style Issues

### 21. `pyproject.toml` entry point points to `app`, not `main`

**File:** `pyproject.toml:27`

```toml
playspec = "playspec.cli:app"
```

This works because Typer's `app` object is callable, but `cli.py:252` explicitly
defines a `main()` wrapper for clarity. Using `"playspec.cli:main"` better
documents intent. Not a runtime bug.

---

### 22. `from __future__ import annotations` inconsistently applied

Used in some files (e.g., `cli.py`, `config.py`) but not others (e.g.,
`audit_entry.py`, `execution_result.py`). In Python 3.11 this has minimal
impact, but consistency aids readability.

---

### 23. `audit.py:create_audit` accepts `**kwargs` silently

**File:** `playspec/audit.py:32`

```python
def create_audit(..., **kwargs) -> AuditEntry:
    return AuditEntry(..., **kwargs)
```

Pydantic's `model_validate` will silently ignore extra kwargs by default
(unless `model_config = ConfigDict(extra='forbid')`). Typos in caller keyword
arguments will be silently swallowed. Remove `**kwargs` and add explicit
parameters, or add `extra='forbid'` to `AuditEntry`.

---

### 24. `README.md` mentions `playspec auth-check` under wrong heading

Minor doc inconsistency — not a functional issue.

---

## Plan Feature Gaps (not yet implemented)

| Plan Item | Location | Status |
|-----------|----------|--------|
| Env reachability check (Phase 4e) | `regression.py` | Missing |
| `suggested-fixes.json` written to disk (Phase 4i) | `regression.py` | Missing |
| Tag-and-register step after author approval (Phase 7e) | `author_pipeline.py` | Missing |
| `--apply-fixes` implementation (Phase 7d) | `author_pipeline.py` | Stub only |
| Retry with exponential backoff for JIRA/Confluence/Figma (Phase 9a) | integrations | Missing |
| Live progress bar during test execution (Phase 9b) | `runner.py` | Missing |
| Repair loop re-runs test after patching (Phase 7c step c-f) | `repair_agent.py` | Stub only |
| `atlas auth` / Copilot CLI auth path for JIRA (Phase 1 auth config) | `jira_client.py` | Missing |
| `JIRA_BASE_URL` / `CONFLUENCE_BASE_URL` env var substitution | `config.py` | Missing |
| Suite-level timeout passed through to Playwright | `runner.py` | Missing |

---

## Testing Coverage Assessment

The 15-module test suite is a genuine strength. Key observations:

- `test_integration.py` — good full-pipeline mocking, but relies on mocked
  subprocess, so bugs in `_build_command` (missing JSON output path) won't be
  caught.
- There are no tests that verify the Playwright JSON report is actually written
  and parsed (issue #2).
- `StabilityStore.update()` pass-recording bug (#3) is not tested — there are
  no assertions on `pass_count` after a successful run.
- The `test_backends.py` tests likely mock subprocess calls and won't catch the
  Copilot sub-command mismatch (#5).

---

## Priority Order for Fixes

1. **#1** — Import `typer` or use `SystemExit` in `regression.py` (one-liner)
2. **#2** — Fix Playwright JSON reporter output path (one-liner in `_build_command`)
3. **#4** — Fix `local-dev` repair_policy to unblock local development
4. **#16** — Fix nested suite parsing in `_parse_json_report`
5. **#3** — Fix `StabilityStore.update()` to record passes (requires adding
   passing test names to `ExecutionResult`)
6. **#7** — Fix repair loop to actually retry
7. **#9** — Add `$VAR` env interpolation in config loader
8. **#14** — Add environment reachability check
9. **#15** — Persist `suggested-fixes.json` to run directory
10. **#5** — Replace `gh copilot suggest -t shell` with a viable code-generation
    invocation

