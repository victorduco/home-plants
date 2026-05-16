DEFINE_NOTIFICATIONS_SYSTEM_TEMPLATE = """You are deciding which plant care issues to notify the user about.

You will receive:
1. A list of issues found in THIS check (from the current session)
2. Issues YOU reported in PREVIOUS checks (your own history — not someone else's)

Your job: return only issues that are GENUINELY NEW compared to what you already reported.
Compare semantically — minor wording differences don't matter. Skip if same underlying
problem was already reported (same affected plants, same root cause).

Previous issues you reported:
{previous_issues}
"""

DEFINE_NOTIFICATIONS_HUMAN_TEMPLATE = """Issues found in this check:
{current_issues}

Return JSON only:
{{"notifications": ["issue 1", "issue 2"]}}
If no new issues compared to previous — return {{"notifications": []}}"""


def render_notifications_system(previous_issues: str) -> str:
    return DEFINE_NOTIFICATIONS_SYSTEM_TEMPLATE.format(previous_issues=previous_issues)


def render_notifications_human(current_issues: str) -> str:
    return DEFINE_NOTIFICATIONS_HUMAN_TEMPLATE.format(current_issues=current_issues)
