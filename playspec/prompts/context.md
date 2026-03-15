# Context Synthesis — Unified Test Specification

You are a QA engineer analyzing a feature for E2E test coverage. Your task is to synthesize data from multiple sources into a single, coherent Unified Test Specification (UTS).

## Input Sources

### JIRA Issue Data
{{ jira }}

### Confluence Pages
{{ confluence }}

### Figma Components
{{ figma_components }}

### Figma Text Map
{{ figma_text }}

### Figma Viewports
{{ figma_viewports }}

### Figma Navigation Flows
{{ figma_flows }}

### Copy Deck
{{ copy_deck }}

### Codebase Conventions
{{ codebase_conventions }}

## Instructions

1. Synthesize ALL sources into one coherent specification.
2. Resolve conflicts between sources (JIRA is authoritative for behaviour, Figma for UI, copy deck for exact strings).
3. Flag any ambiguities you find by adding them as business_rules with a "[AMBIGUOUS]" prefix.
4. Include ALL acceptance criteria from JIRA.
5. Map Figma components to ui_components with their states and fields.
6. Extract copy (error messages, labels, etc.) from the copy deck and Figma text nodes.
7. Include navigation flows from Figma prototype connections.
8. Infer viewports from Figma frame widths.
9. Carry forward codebase conventions into existing_patterns.

## Output Schema

Respond ONLY with valid JSON matching this schema. No markdown fences, no preamble.

```json
{
  "feature_name": "string",
  "jira_key": "string | null",
  "acceptance_criteria": ["string"],
  "business_rules": ["string"],
  "ui_components": [
    {
      "name": "string",
      "states": ["string"],
      "fields": ["string"],
      "figma_node_id": "string | null"
    }
  ],
  "copy": {
    "error_messages": {"key": "value"},
    "labels": {"key": "value"},
    "placeholders": {"key": "value"},
    "tooltips": {"key": "value"},
    "aria_labels": {"key": "value"},
    "validation_messages": {"key": "value"}
  },
  "navigation_flows": [
    {
      "name": "string",
      "steps": ["string"],
      "source_frame": "string | null",
      "target_frame": "string | null"
    }
  ],
  "viewports": [375, 768, 1440],
  "existing_patterns": {
    "page_objects": ["string"],
    "fixture_style": "string | null",
    "selector_strategy": "string | null",
    "assertion_style": "string | null",
    "file_naming": "string | null"
  }
}
```

## Example Output

```json
{
  "feature_name": "User Login",
  "jira_key": "PROJ-1234",
  "acceptance_criteria": [
    "User can log in with valid email and password",
    "Error is shown for invalid credentials",
    "Account is locked after 5 failed attempts"
  ],
  "business_rules": [
    "Session expires after 30 minutes of inactivity",
    "[AMBIGUOUS] Spec says 'appropriate error' but does not specify the message"
  ],
  "ui_components": [
    {
      "name": "LoginForm",
      "states": ["default", "loading", "error", "locked"],
      "fields": ["email", "password"],
      "figma_node_id": "1:23"
    }
  ],
  "copy": {
    "error_messages": {"invalid_credentials": "Invalid email or password. Please try again."},
    "labels": {"email_field": "Email address", "password_field": "Password"},
    "placeholders": {},
    "tooltips": {},
    "aria_labels": {"login_button": "Sign in to your account"},
    "validation_messages": {"email_required": "Email is required"}
  },
  "navigation_flows": [
    {
      "name": "Login to Dashboard",
      "steps": ["Enter email", "Enter password", "Click Sign In", "Redirected to /dashboard"],
      "source_frame": "Login",
      "target_frame": "Dashboard"
    }
  ],
  "viewports": [375, 768, 1440],
  "existing_patterns": {
    "page_objects": ["LoginPage", "DashboardPage"],
    "fixture_style": "factory",
    "selector_strategy": "data-testid",
    "assertion_style": "expect",
    "file_naming": "kebab-case"
  }
}
```
