"""Figma document tree parser — extract components, text, viewports, and flows."""

from __future__ import annotations

from typing import Any

from playspec.schemas.uts import NavigationFlow, UIComponent


def extract_components(doc: dict[str, Any]) -> list[UIComponent]:
    """Walk the Figma document tree and extract component nodes."""
    components: list[UIComponent] = []
    _walk_for_components(doc.get("document", {}), components)
    return components


def extract_text_map(doc: dict[str, Any]) -> dict[str, str]:
    """Build a map of component name → text content found within."""
    text_map: dict[str, str] = {}
    _walk_for_text(doc.get("document", {}), text_map, parent_name="")
    return text_map


def extract_viewports(doc: dict[str, Any]) -> list[int]:
    """Extract unique frame widths (used to infer viewport breakpoints)."""
    widths: set[int] = set()
    _walk_for_frames(doc.get("document", {}), widths)
    return sorted(widths)


def extract_flows(doc: dict[str, Any]) -> list[NavigationFlow]:
    """Extract navigation flows from Figma prototype connections."""
    flows: list[NavigationFlow] = []
    _walk_for_flows(doc.get("document", {}), flows)
    return flows


def _walk_for_components(node: dict, out: list[UIComponent]) -> None:
    ntype = node.get("type", "")
    if ntype in ("COMPONENT", "COMPONENT_SET"):
        states: list[str] = []
        fields: list[str] = []
        for child in node.get("children", []):
            if child.get("type") == "VARIANT":
                states.append(child.get("name", ""))
            if child.get("type") == "TEXT":
                fields.append(child.get("characters", ""))
        out.append(UIComponent(
            name=node.get("name", ""),
            states=states,
            fields=fields,
            figma_node_id=node.get("id"),
        ))
    for child in node.get("children", []):
        _walk_for_components(child, out)


def _walk_for_text(node: dict, out: dict[str, str], parent_name: str) -> None:
    ntype = node.get("type", "")
    name = node.get("name", parent_name)
    if ntype == "TEXT":
        chars = node.get("characters", "")
        if chars:
            out[name] = chars
    for child in node.get("children", []):
        _walk_for_text(child, out, parent_name=name)


def _walk_for_frames(node: dict, out: set[int]) -> None:
    ntype = node.get("type", "")
    if ntype == "FRAME":
        bbox = node.get("absoluteBoundingBox", {})
        w = bbox.get("width")
        if w and isinstance(w, (int, float)) and w > 100:
            out.add(int(w))
    for child in node.get("children", []):
        _walk_for_frames(child, out)


def _walk_for_flows(node: dict, out: list[NavigationFlow]) -> None:
    connections = node.get("transitionNodeID")
    if connections:
        out.append(NavigationFlow(
            name=node.get("name", ""),
            source_frame=node.get("id"),
            target_frame=connections,
        ))
    for child in node.get("children", []):
        _walk_for_flows(child, out)
