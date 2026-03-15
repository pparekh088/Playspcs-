# Test Repair — Targeted Patch for Failing Test

You are debugging a failing Playwright test. Your task is to produce a MINIMAL diff patch that fixes the specific failure.

## Failure Details

**Test file:** {{ test_file }}
**Test name:** {{ test_name }}
**Error message:** {{ error_message }}
**Stack trace:** {{ stack_trace }}

## Original Test Code

```typescript
{{ original_code }}
```

## Instructions

1. Diagnose the root cause from the error message and stack trace.
2. Produce a MINIMAL patch — change only what is necessary to fix the failure.
3. **NEVER** weaken assertions (e.g. do not replace `toHaveText('exact')` with `toContainText`).
4. **NEVER** remove test coverage (do not delete test cases or assertions).
5. **NEVER** add hardcoded sleeps (`page.waitForTimeout`).
6. Fix the actual issue:
   - Broken selector → update to match current DOM (use data-testid or role if available)
   - Timing issue → add proper Playwright wait (waitForLoadState, waitForSelector)
   - Wrong assertion value → update the expected value if the spec changed
   - Missing import → add the import
7. Preserve the test's original INTENT — it should still verify the same behaviour.

## Output Format

Respond ONLY with valid JSON. No markdown fences, no preamble.

```json
{
  "diagnosis": "Brief explanation of what went wrong",
  "patch": "The complete corrected test file content",
  "changes_made": ["List of specific changes"]
}
```

## Example

```json
{
  "diagnosis": "The login button selector changed from #login-btn to [data-testid='login-submit']",
  "patch": "// @tags: smoke, p0\n// @jira: PROJ-1234\n\nimport { test, expect } from '@playwright/test';\n\ntest('logs in', async ({ page }) => {\n  await page.goto('/login');\n  await page.fill('[data-testid=\"email\"]', 'user@example.com');\n  await page.click('[data-testid=\"login-submit\"]');\n  await expect(page).toHaveURL('/dashboard');\n});\n",
  "changes_made": ["Updated login button selector from '#login-btn' to '[data-testid=\"login-submit\"]'"]
}
```
