import json
import os

from aiohttp import web
from server import PromptServer

PRESETS_PATH = os.path.join(os.path.dirname(__file__), "presets.json")


def load_presets():
    with open(PRESETS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_presets(data):
    with open(PRESETS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_preset_list(section):
    presets = load_presets()
    return ["-- 선택 --"] + presets.get(section, [])


# ── API routes ──────────────────────────────────────────────────────

@PromptServer.instance.routes.get("/promptbuilder/presets")
async def get_presets(request):
    return web.json_response(load_presets())


@PromptServer.instance.routes.post("/promptbuilder/presets/{section}/add")
async def add_preset(request):
    section = request.match_info["section"]
    body = await request.json()
    text = body.get("text", "").strip()
    if not text:
        return web.json_response({"error": "text is required"}, status=400)

    presets = load_presets()
    if section not in presets:
        presets[section] = []
    if text not in presets[section]:
        presets[section].append(text)
        save_presets(presets)

    return web.json_response({"ok": True, "presets": presets[section]})


@PromptServer.instance.routes.post("/promptbuilder/presets/{section}/delete")
async def delete_preset(request):
    section = request.match_info["section"]
    body = await request.json()
    text = body.get("text", "").strip()

    presets = load_presets()
    if section in presets and text in presets[section]:
        presets[section].remove(text)
        save_presets(presets)

    return web.json_response({"ok": True, "presets": presets.get(section, [])})


@PromptServer.instance.routes.post("/promptbuilder/presets/{section}/reorder")
async def reorder_presets(request):
    section = request.match_info["section"]
    body = await request.json()
    items = body.get("items", [])

    presets = load_presets()
    if section in presets:
        presets[section] = items
        save_presets(presets)

    return web.json_response({"ok": True, "presets": presets.get(section, [])})


# ── Grammar correction ──────────────────────────────────────────────

_grammar_tool = None

def get_grammar_tool():
    global _grammar_tool
    if _grammar_tool is None:
        import language_tool_python
        _grammar_tool = language_tool_python.LanguageTool("en-US")
    return _grammar_tool


@PromptServer.instance.routes.post("/promptbuilder/grammar")
async def grammar_check(request):
    body = await request.json()
    text = body.get("text", "")
    if not text.strip():
        return web.json_response({"corrected": text})

    try:
        tool = get_grammar_tool()
        corrected = tool.correct(text)
        return web.json_response({"corrected": corrected})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# ── Node ────────────────────────────────────────────────────────────

class PromptBuilder:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "pov": ("STRING", {"default": "", "multiline": True}),
                "pov_pick": (get_preset_list("pov"),),
                "character": ("STRING", {"default": "", "multiline": True}),
                "character_pick": (get_preset_list("character"),),
                "action": ("STRING", {"default": "", "multiline": True}),
                "action_pick": (get_preset_list("action"),),
                "clothing": ("STRING", {"default": "", "multiline": True}),
                "clothing_pick": (get_preset_list("clothing"),),
                "viewer_action": ("STRING", {"default": "", "multiline": True}),
                "viewer_action_pick": (get_preset_list("viewer_action"),),
                "background": ("STRING", {"default": "", "multiline": True}),
                "background_pick": (get_preset_list("background"),),
                "separator": (["comma", "newline", "period"],),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("prompt",)
    FUNCTION = "build"
    CATEGORY = "prompt"

    def build(self, pov, pov_pick, character, character_pick, action, action_pick,
              clothing, clothing_pick, viewer_action,
              viewer_action_pick, background, background_pick, separator):
        import re
        def clean(s):
            s = s.strip()
            # Replace double+ commas with single comma
            s = re.sub(r',(\s*,)+', ',', s)
            return s.strip()

        sections = [
            clean(pov),
            clean(character),
            clean(action),
            clean(clothing),
            clean(viewer_action),
            clean(background),
        ]
        sections = [s for s in sections if s]

        sep_map = {"comma": ", ", "newline": "\n", "period": ". "}
        prompt = sep_map[separator].join(sections)

        return (prompt,)


NODE_CLASS_MAPPINGS = {
    "PromptBuilder": PromptBuilder,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PromptBuilder": "Prompt Builder",
}
