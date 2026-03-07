from typing import Any

def build_messages(
    operator_goal: str,
    named_regions: dict[str, list[float]] | None = None,
    past_actions: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    regions = named_regions or {}
    schema_text = (
        'Return only valid JSON with this exact shape: '
        '{"action":"wait|click|double_click|drag|type_text|press_hotkey",'
        '"parameters":{"x_loc":number|null,"y_loc":number|null,'
        '"end_x_loc":number|null,"end_y_loc":number|null,'
        '"text":string|null,"keys":string[]},'
        '"task":{"inferred_goal":string|null,"success_criteria":string|null,"is_complete":boolean,'
        '"completion_confidence":0-100,"completion_reason":string|null},'
        '"reason":string,"confidence":0-100}. '
        'Do not use keys like "args" or omit required fields. '
        'For click/double_click/drag actions, you MUST use the normalized 0-1000 coordinate system for x_loc/y_loc/end_x_loc/end_y_loc. '
        '0, 0 is the top-left of the image, and 1000, 1000 is the bottom-right. '
        'Do NOT use percentages. '
        'Use action="type_text" only when parameters.text is non-empty and an input is ready for typing. '
        'If you recently clicked an input field, assume it is focused and proceed to type_text. '
        'Use action="press_hotkey" only when parameters.keys contains at least one key. '
        'Do not use type_text as a placeholder for scrolling or navigation. '
        'Always evaluate task progress in task.inferred_goal and task.is_complete each cycle. '
        'Explicitly formulate the success_criteria for the entire goal (e.g. "Comment is typed AND post button is clicked"). Do not set is_complete=true until all success_criteria are unmistakably met. '
        'Set task.is_complete=true only when the requested outcome is visibly achieved, with completion_confidence and completion_reason. '
        'ONLY use action="wait" if you are waiting for a temporal event like a page loading or an animation finishing. '
        'If content is off-screen and you need to scroll, DO NOT use wait. Instead, use action="press_hotkey" with keys like ["pagedown"] or ["space"], or click a scrollbar. '
        'If unsure what to do, return action="wait" with a low confidence score.'
    )
    history_text = ""
    if past_actions:
        history_text = "\nRecent actions taken by you (use this to avoid repeating your last step):\n"
        for i, act in enumerate(past_actions):
            act_name = act.get("action", "unknown")
            act_reason = act.get("reason", "No reason provided")
            history_text += f"{i+1}. {act_name} - {act_reason}\n"

    return [
        {
            "role": "system",
            "content": "You are a desktop vision automation analyst. Return only valid JSON.",
        },
        {
            "role": "user",
            "content": f"Goal: {operator_goal}\nRegions: {regions}{history_text}\n{schema_text}",
        },
    ]
