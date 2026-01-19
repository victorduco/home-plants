"""Prompt helpers for the Plants tools."""

from fastmcp import FastMCP


def register_plants_prompts(mcp: FastMCP) -> None:
    """Register prompts for plant tool usage."""

    @mcp.prompt
    def plants_tool_prompt(
        intent: str = "",
        identifier: str = "",
        updates: str = "",
    ) -> str:
        """Guide the model to call the Plants tools safely."""
        intent_hint = f'Intent: "{intent}".' if intent else "Intent is not specified."
        identifier_hint = (
            f'Plant identifier: "{identifier}".'
            if identifier
            else "Plant identifier is unknown."
        )
        updates_hint = f'Updates: "{updates}".' if updates else "No updates specified."
        return (
            "You are operating Home Assistant Plants via tools. "
            "Choose the smallest tool for the intent and return ONLY tool calls.\n"
            f"{intent_hint} {identifier_hint} {updates_hint}\n"
            "Tools: get_plants_status, add_plant, water_plant, edit_plant, delete_plant.\n"
            "Identifiers can be config entry_id or exact plant name. "
            "Use get_plants_status if you need to discover identifiers."
        )
