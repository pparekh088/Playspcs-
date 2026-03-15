"""Unified Test Specification — the canonical intermediate representation for test generation."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class UIComponent(BaseModel):
    """A UI component extracted from Figma or described in JIRA/Confluence."""

    name: str
    states: list[str] = Field(default_factory=list)
    fields: list[str] = Field(default_factory=list)
    figma_node_id: str | None = None


class CopyDeck(BaseModel):
    """Extracted UI copy — error messages, labels, tooltips, placeholders."""

    error_messages: dict[str, str] = Field(default_factory=dict)
    labels: dict[str, str] = Field(default_factory=dict)
    placeholders: dict[str, str] = Field(default_factory=dict)
    tooltips: dict[str, str] = Field(default_factory=dict)
    aria_labels: dict[str, str] = Field(default_factory=dict)
    validation_messages: dict[str, str] = Field(default_factory=dict)


class NavigationFlow(BaseModel):
    """A user navigation flow derived from Figma prototype connections or specs."""

    name: str
    steps: list[str] = Field(default_factory=list)
    source_frame: str | None = None
    target_frame: str | None = None


class ExistingPattern(BaseModel):
    """Convention detected from the existing codebase."""

    page_objects: list[str] = Field(default_factory=list)
    fixture_style: str | None = None
    selector_strategy: str | None = None
    assertion_style: str | None = None
    file_naming: str | None = None


class UnifiedTestSpec(BaseModel):
    """The single canonical spec that drives test planning and generation."""

    model_config = ConfigDict(populate_by_name=True)

    feature_name: str
    jira_key: str | None = None
    acceptance_criteria: list[str] = Field(default_factory=list)
    business_rules: list[str] = Field(default_factory=list)
    ui_components: list[UIComponent] = Field(default_factory=list)
    copy_deck: CopyDeck = Field(default_factory=CopyDeck, alias="copy")
    navigation_flows: list[NavigationFlow] = Field(default_factory=list)
    viewports: list[int] = Field(default_factory=list)
    existing_patterns: ExistingPattern = Field(default_factory=ExistingPattern)
