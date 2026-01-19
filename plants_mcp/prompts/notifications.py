"""Prompt helpers for composing notifications."""

from fastmcp import FastMCP


def register_notification_prompts(mcp: FastMCP) -> None:
    """Register prompts for notification composition."""

    @mcp.prompt
    def compose_notification_prompt(
        device: str = "",
        intent: str = "",
        audience: str = "",
        urgency: str = "normal",
    ) -> str:
        """Guide the model to craft a Home Assistant notification."""
        device_hint = (
            f'Device slug: "{device}".'
            if device
            else "Device slug is unknown. Read mcp://notification/devices first."
        )
        intent_hint = f'Intent: "{intent}".' if intent else "Intent is not specified."
        audience_hint = (
            f'Audience: "{audience}".' if audience else "Audience is not specified."
        )
        return (
            "You are creating a Home Assistant push notification. "
            "Return ONLY a JSON object with keys: title, message, subtitle, sound, data.\n"
            f"{device_hint} {intent_hint} {audience_hint} Urgency: {urgency}.\n"
            "Guidelines: title <= 60 chars, message <= 240 chars, "
            "subtitle is optional and short, sound is a short string (default: \"default\"), "
            "data is a JSON object for optional fields (use {} if none). "
            "Use clear, concise language."
        )
