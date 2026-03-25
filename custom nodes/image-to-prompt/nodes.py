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
    "ChatGPT": [
        "gpt-5.4",
        "gpt-5.4-mini",
        "gpt-5.4-nano",
    ],
    "Gemini": [
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-2.5-flash-lite",
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
    "Just the raw prompt text, nothing else. "
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
    _last_signatures = {}  # {unique_id: signature}

    def _compute_signature(self, image, provider, model, style, first_person_pov, nsfw, realistic, korean, structured_order, custom_override, custom_instruction, background_image):
        import hashlib
        img_hash = hashlib.md5(image.cpu().numpy().tobytes()).hexdigest()
        parts = [img_hash, provider, model, style, str(first_person_pov), str(nsfw), str(realistic), str(korean), str(structured_order), str(custom_override), custom_instruction or ""]
        if background_image is not None:
            parts.append(hashlib.md5(background_image.cpu().numpy().tobytes()).hexdigest())
        return hashlib.md5("|".join(parts).encode()).hexdigest()

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "provider": (["ChatGPT", "Gemini", "Grok"],),
                "model": (ALL_MODELS,),
                "style": (list(PROMPT_STYLES.keys()),),
                "first_person_pov": ("BOOLEAN", {"default": True}),
                "nsfw": ("BOOLEAN", {"default": True}),
                "realistic": ("BOOLEAN", {"default": True}),
                "korean": ("BOOLEAN", {"default": True}),
                "always_run": ("BOOLEAN", {"default": False}),
                "custom_override": ("BOOLEAN", {"default": False}),
                "structured_order": ("BOOLEAN", {"default": True}),
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
        return float("NaN")

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
            "max_completion_tokens": 4096,
        }).encode("utf-8")

        req = urllib.request.Request(endpoint, data=payload, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "ComfyUI-ImageToPrompt/1.0",
        })
        result = self._api_request(req)
        return result["choices"][0]["message"]["content"].strip()

    def generate(self, image, provider, model, style, first_person_pov, nsfw, realistic, korean, always_run, custom_override=True, structured_order=False, background_image=None, custom_instruction="", edited_prompt="", unique_id=None):
        # Compute signature of generation conditions
        sig = self._compute_signature(image, provider, model, style, first_person_pov, nsfw, realistic, korean, structured_order, custom_override, custom_instruction, background_image)
        prev_sig = ImageToPrompt._last_signatures.get(unique_id)
        conditions_changed = (prev_sig is not None and sig != prev_sig)

        # If user edited the prompt and not forcing re-run and conditions unchanged, use edited version
        if edited_prompt and edited_prompt.strip() and not always_run and not conditions_changed:
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
                "Write the prompt from a first-person POV perspective. "
                "Refer to the viewer as 'the male viewer' instead of I, my, or me."
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
            sections = [
                "1) Camera angle and composition",
                "2) Character appearance (face, hair, body)",
                "3) Clothing and accessories",
                "4) Subject's action, pose, and body position",
            ]
            if first_person_pov:
                sections.append("5) Viewer's hands and arm actions only; briefly describe any other visible body parts")
                sections.append("6) Background and environment (keep this brief)")
            else:
                sections.append("5) Background and environment (keep this brief)")
            modifiers.append(
                "Structure the prompt in this exact order, using only the section numbers (1), 2), etc.) as separators. "
                "Do not include section titles or headers after the numbers: "
                + ", ".join(sections) + "."
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
        else:
            raise ValueError(f"Unknown provider: {provider}")

        if structured_order:
            import re
            prompt = re.sub(r'\s*\|{2,}\s*', '\n', prompt)
            prompt = prompt.strip()

        # Save signature after successful API call
        ImageToPrompt._last_signatures[unique_id] = sig

        return {"ui": {"text": [prompt]}, "result": (prompt,)}


NODE_CLASS_MAPPINGS = {
    "ImageToPrompt": ImageToPrompt,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ImageToPrompt": "Image to Prompt (AI)",
}
