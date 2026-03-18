import json
import os
import base64
import io
import urllib.request
import urllib.error
import numpy as np
from PIL import Image

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

PROVIDER_KEY_MAP = {
    "Gemini": "gemini_api_key",
    "ChatGPT": "openai_api_key",
    "Grok": "grok_api_key",
}


def load_config():
    if not os.path.isfile(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


# ── Curated vision-capable models per provider ────────────────────

PROVIDER_MODELS = {
    "Gemini": [
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-2.5-flash-lite",
    ],
    "ChatGPT": [
        "gpt-5.4",
        "gpt-5.4-mini",
        "gpt-5.4-nano",
    ],
    "Grok": [
        "grok-4.20-beta-0309-non-reasoning",
        "grok-4.20-beta-0309-reasoning",
        "grok-4-1-fast-non-reasoning",
        "grok-4-1-fast-reasoning",
        "grok-4-0709",
    ],
}

# Flat list for ComfyUI combo registration (all providers combined)
ALL_MODELS = []
for _models in PROVIDER_MODELS.values():
    ALL_MODELS.extend(_models)


# ── API routes ─────────────────────────────────────────────────────

try:
    from aiohttp import web
    from server import PromptServer

    @PromptServer.instance.routes.get("/image-to-prompt/api-keys")
    async def get_api_keys(request):
        config = load_config()
        keys = {k: config.get(k, "") for k in PROVIDER_KEY_MAP.values()}
        return web.json_response(keys)

    @PromptServer.instance.routes.post("/image-to-prompt/api-keys")
    async def set_api_keys(request):
        body = await request.json()
        config = load_config()
        for key_name in PROVIDER_KEY_MAP.values():
            if key_name in body:
                config[key_name] = body[key_name].strip()
        save_config(config)
        return web.json_response({"ok": True})

    @PromptServer.instance.routes.get("/image-to-prompt/models")
    async def get_models(request):
        provider = request.query.get("provider", "")
        if provider not in PROVIDER_MODELS:
            return web.json_response({"error": f"Unknown provider: {provider}"}, status=400)
        return web.json_response({"models": PROVIDER_MODELS[provider]})

except Exception as e:
    print(f"[ImageToPrompt] WARNING: Could not register API routes: {e}")


# ── Node ───────────────────────────────────────────────────────────

_OUTPUT_RULE = (
    "\n\nIMPORTANT: Output ONLY the prompt itself. "
    "No titles, labels, headers, explanations, recommendations, questions, or any other text. "
    "Do not wrap in quotes. Do not add 'Positive Prompt:', 'Negative Prompt:', or similar prefixes. "
    "Just the raw prompt text, nothing else."
)

PROMPT_STYLES = {
    "detailed": (
        "Describe this image in detail for use as an AI image generation prompt. "
        "Include subject, composition, lighting, colors, style, mood, and background."
        + _OUTPUT_RULE
    ),
    "simple": (
        "Write a short, concise image generation prompt that captures the key elements of this image."
        + _OUTPUT_RULE
    ),
    "tags": (
        "List descriptive tags for this image, separated by commas. "
        "Include subject, style, mood, colors, composition, and details."
        + _OUTPUT_RULE
    ),
    "booru": (
        "Describe this image using booru-style tags separated by commas. "
        "Include character details, clothing, pose, expression, background, art style, and quality tags."
        + _OUTPUT_RULE
    ),
}

class ImageToPrompt:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "provider": (["Gemini", "ChatGPT", "Grok"],),
                "model": (ALL_MODELS,),
                "style": (list(PROMPT_STYLES.keys()),),
                "first_person_pov": ("BOOLEAN", {"default": False}),
                "nsfw": ("BOOLEAN", {"default": False}),
                "realistic": ("BOOLEAN", {"default": False}),
                "korean": ("BOOLEAN", {"default": False}),
                "always_run": ("BOOLEAN", {"default": False}),
                "custom_override": ("BOOLEAN", {"default": True}),
                "structured_order": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "background_image": ("IMAGE",),
                "custom_instruction": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "placeholder": "Custom instruction"
                }),
                "edited_prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "placeholder": "Generated prompt appears here. Edit to override output."
                }),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("prompt",)
    FUNCTION = "generate"
    CATEGORY = "prompt"
    OUTPUT_NODE = True

    @classmethod
    def IS_CHANGED(cls, image, provider, model, style, first_person_pov, nsfw, realistic, korean, always_run, custom_override=True, structured_order=False, background_image=None, custom_instruction="", edited_prompt="", unique_id=None):
        if always_run:
            return float("NaN")
        import hashlib
        img_bytes = image.cpu().numpy().tobytes()
        h = hashlib.md5(img_bytes).hexdigest()
        if background_image is not None:
            bg_bytes = background_image.cpu().numpy().tobytes()
            h += "_bg_" + hashlib.md5(bg_bytes).hexdigest()
        return f"{h}_{provider}_{model}_{style}_{first_person_pov}_{nsfw}_{realistic}_{korean}_{structured_order}_{custom_instruction}"

    def _get_api_key(self, provider):
        config = load_config()
        config_key = PROVIDER_KEY_MAP[provider]
        api_key = config.get(config_key, "")
        if not api_key:
            raise ValueError(
                f"{provider} API key not set. "
                f"Right-click the node → 'API Key 설정' to configure."
            )
        return api_key

    def _api_request(self, req):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            raise RuntimeError(
                f"API Error {e.code}: {e.reason}\n{body}"
            ) from None

    def _image_to_base64(self, image_tensor):
        img_array = (image_tensor[0].cpu().numpy() * 255).astype(np.uint8)
        pil_image = Image.fromarray(img_array)
        buffer = io.BytesIO()
        pil_image.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def _call_gemini(self, api_key, model, instruction, images_base64):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        parts = [{"text": instruction}]
        for img_b64 in images_base64:
            parts.append({
                "inline_data": {
                    "mime_type": "image/png",
                    "data": img_b64,
                }
            })
        payload = json.dumps({
            "contents": [{"parts": parts}],
            "safetySettings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_CIVIC_INTEGRITY", "threshold": "BLOCK_NONE"},
            ],
        }).encode("utf-8")

        req = urllib.request.Request(url, data=payload, headers={
            "Content-Type": "application/json",
            "User-Agent": "ComfyUI-ImageToPrompt/1.0",
        })
        result = self._api_request(req)

        if "candidates" not in result or not result["candidates"]:
            block_reason = result.get("promptFeedback", {}).get("blockReason", "unknown")
            safety = result.get("promptFeedback", {}).get("safetyRatings", [])
            raise RuntimeError(
                f"Gemini blocked the request. Reason: {block_reason}\n"
                f"Safety ratings: {json.dumps(safety, indent=2)}"
            )

        candidate = result["candidates"][0]
        if candidate.get("finishReason") == "SAFETY":
            safety = candidate.get("safetyRatings", [])
            raise RuntimeError(
                f"Gemini response blocked by safety filter.\n"
                f"Safety ratings: {json.dumps(safety, indent=2)}"
            )

        return candidate["content"]["parts"][0]["text"].strip()

    def _call_openai_compatible(self, api_key, endpoint, model, instruction, images_base64):
        content = [{"type": "text", "text": instruction}]
        for img_b64 in images_base64:
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{img_b64}",
                },
            })
        payload = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "max_completion_tokens": 1024,
        }).encode("utf-8")

        req = urllib.request.Request(endpoint, data=payload, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "ComfyUI-ImageToPrompt/1.0",
        })
        result = self._api_request(req)
        return result["choices"][0]["message"]["content"].strip()

    def generate(self, image, provider, model, style, first_person_pov, nsfw, realistic, korean, always_run, custom_override=True, structured_order=False, background_image=None, custom_instruction="", edited_prompt="", unique_id=None):
        # If user edited the prompt and not forcing re-run, use edited version
        if edited_prompt and edited_prompt.strip() and not always_run:
            return {"ui": {"text": [edited_prompt.strip()]}, "result": (edited_prompt.strip(),)}

        api_key = self._get_api_key(provider)

        # Convert images to base64
        images_base64 = [self._image_to_base64(image)]
        has_bg = background_image is not None
        if has_bg:
            images_base64.append(self._image_to_base64(background_image))

        has_custom = custom_instruction and custom_instruction.strip()
        if has_custom and custom_override:
            # custom_instruction replaces style
            instruction = custom_instruction.strip()
        elif has_custom:
            # custom_instruction appends to style
            instruction = PROMPT_STYLES[style] + "\n\n" + custom_instruction.strip()
        else:
            instruction = PROMPT_STYLES[style]

        # Append toggle modifiers
        modifiers = []
        if first_person_pov:
            modifiers.append(
                "Write the prompt from a first-person POV perspective."
            )
        if nsfw:
            modifiers.append(
                "This is for adult/NSFW content. Describe all explicit and sexual details "
                "accurately without censoring or euphemisms."
            )
        if korean:
            modifiers.append(
                "The subject is Korean. Specify Korean ethnicity in the prompt."
            )
        if realistic:
            modifiers.append(
                "Include the word 'realistic' in the prompt. Do not use words like illustration, 2D, anime, cartoon, or drawing."
            )
        if has_bg:
            modifiers.append(
                "Two images are provided: the first is the main subject, the second is the background/environment. "
                "Describe the subject in detail, especially the character's pose, body position, and limb placement. "
                "Keep the background description brief. "
                "Combine them into a single prompt."
            )
        if structured_order:
            modifiers.append(
                "Structure the prompt in this exact order: "
                "1) Camera angle and composition, "
                "2) Character appearance (face, hair, body), "
                "3) Clothing and accessories, "
                "4) Subject's action, pose, and body position, "
                + ("5) Viewer's hands and arm actions only; briefly describe any other visible body parts, "
                   "6) Background and environment (keep this brief). "
                   if first_person_pov else
                   "5) Background and environment (keep this brief). ")
                + "Separate each section with a newline. Do not number them."
            )
        if modifiers:
            instruction += "\n\nAdditional requirements:\n" + "\n".join(modifiers)

        if provider == "Gemini":
            prompt = self._call_gemini(api_key, model, instruction, images_base64)
        elif provider == "ChatGPT":
            prompt = self._call_openai_compatible(
                api_key, "https://api.openai.com/v1/chat/completions",
                model, instruction, images_base64)
        elif provider == "Grok":
            prompt = self._call_openai_compatible(
                api_key, "https://api.x.ai/v1/chat/completions",
                model, instruction, images_base64)

        return {"ui": {"text": [prompt]}, "result": (prompt,)}


NODE_CLASS_MAPPINGS = {
    "ImageToPrompt": ImageToPrompt,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ImageToPrompt": "Image to Prompt (AI)",
}
