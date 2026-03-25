import { app } from "../../scripts/app.js";

const PROVIDERS = ["Gemini", "ChatGPT", "Grok"];
const KEY_NAMES = {
  Gemini: "gemini_api_key",
  ChatGPT: "openai_api_key",
  Grok: "grok_api_key",
};

// Generation parameters that affect output — changing any should clear edited_prompt
const GENERATION_PARAMS = [
  "provider", "model", "style", "first_person_pov",
  "nsfw", "realistic", "korean", "structured_order", "custom_override",
];

// Cache fetched model lists per provider
const modelCache = {};

async function fetchModels(provider) {
  if (modelCache[provider]) return modelCache[provider];
  try {
    const resp = await fetch(
      `/image-to-prompt/models?provider=${encodeURIComponent(provider)}`
    );
    const data = await resp.json();
    modelCache[provider] = data.models && data.models.length > 0 ? data.models : [];
  } catch {
    modelCache[provider] = [];
  }
  return modelCache[provider];
}

function updateModelWidget(node, provider, forceReset = false) {
  const modelWidget = node.widgets?.find((w) => w.name === "model");
  if (!modelWidget) return;

  fetchModels(provider).then((models) => {
    modelWidget.options.values = models;
    if (forceReset || !models.includes(modelWidget.value)) {
      modelWidget.value = models[0] || "";
    }
    app.graph.setDirtyCanvas(true);
  });
}

app.registerExtension({
  name: "imageToPrompt.apiKeyManager",

  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== "ImageToPrompt") return;

    const origGetExtraMenuOptions = nodeType.prototype.getExtraMenuOptions;
    nodeType.prototype.getExtraMenuOptions = function (_, options) {
      if (origGetExtraMenuOptions) {
        origGetExtraMenuOptions.apply(this, arguments);
      }

      options.unshift(
        {
          content: "🔑 API Key 설정",
          callback: () => showApiKeyDialog(),
        },
        {
          content: "🔄 모델 목록 새로고침",
          callback: () => {
            const providerWidget = this.widgets?.find(
              (w) => w.name === "provider"
            );
            if (providerWidget) {
              delete modelCache[providerWidget.value];
              updateModelWidget(this, providerWidget.value);
            }
          },
        }
      );
    };

    // Clear edited_prompt when generation parameters change
    function setupAutoReset(node) {
      const editWidget = node.widgets?.find((w) => w.name === "edited_prompt");
      if (!editWidget) return;

      for (const name of GENERATION_PARAMS) {
        const w = node.widgets?.find((x) => x.name === name);
        if (!w || w._autoResetSetup) continue;
        w._autoResetSetup = true;
        const orig = w.callback;
        w.callback = function (value) {
          if (orig) orig.call(this, value);
          editWidget.value = "";
          app.graph.setDirtyCanvas(true);
          console.log(`[image-to-prompt] edited_prompt cleared (${name} changed)`);
        };
      }

      // custom_instruction: detect changes on focus-out (callback fires on every keystroke)
      const ciWidget = node.widgets?.find((w) => w.name === "custom_instruction");
      if (ciWidget && !ciWidget._autoResetSetup) {
        ciWidget._autoResetSetup = true;
        let lastValue = ciWidget.value;
        const origCb = ciWidget.callback;
        ciWidget.callback = function (value) {
          if (origCb) origCb.call(this, value);
          if (value !== lastValue) {
            lastValue = value;
            editWidget.value = "";
            app.graph.setDirtyCanvas(true);
            console.log("[image-to-prompt] edited_prompt cleared (custom_instruction changed)");
          }
        };
      }
    }

    // Set up provider→model sync
    function setupProviderSync(node) {
      const providerWidget = node.widgets?.find(
        (w) => w.name === "provider"
      );
      if (!providerWidget) return;

      // Always sync model list to current provider
      updateModelWidget(node, providerWidget.value, true);

      // Only attach callback once
      if (!providerWidget._modelSyncSetup) {
        providerWidget._modelSyncSetup = true;
        const origCallback = providerWidget.callback;
        providerWidget.callback = function (value) {
          if (origCallback) origCallback.call(this, value);
          updateModelWidget(node, value, true);
        };
      }
    }

    // Clear edited_prompt when image inputs are connected/disconnected
    const origOnConnectionsChange = nodeType.prototype.onConnectionsChange;
    nodeType.prototype.onConnectionsChange = function (side, slot, connected, link_info, output) {
      if (origOnConnectionsChange) origOnConnectionsChange.apply(this, arguments);
      if (side === 1) {  // input side
        const inputName = this.inputs?.[slot]?.name;
        if (inputName === "image" || inputName === "background_image") {
          const editWidget = this.widgets?.find((w) => w.name === "edited_prompt");
          if (editWidget) {
            editWidget.value = "";
            app.graph.setDirtyCanvas(true);
            console.log(`[image-to-prompt] edited_prompt cleared (${inputName} ${connected ? "connected" : "disconnected"})`);
          }
        }
      }
    };

    // New node creation
    const origOnNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      if (origOnNodeCreated) origOnNodeCreated.apply(this, arguments);
      setupProviderSync(this);
      setupAutoReset(this);
    };

    // Workflow load / existing node — delay to ensure widgets are loaded
    const origOnConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function (info) {
      if (origOnConfigure) origOnConfigure.call(this, info);
      const self = this;
      setTimeout(() => {
        setupProviderSync(self);
        setupAutoReset(self);
      }, 100);
    };

    // After execution, populate edited_prompt widget with the result
    const origOnExecuted = nodeType.prototype.onExecuted;
    nodeType.prototype.onExecuted = function (data) {
      if (origOnExecuted) origOnExecuted.call(this, data);

      const text = data?.text?.[0];
      if (!text) return;

      const editWidget = this.widgets?.find(
        (w) => w.name === "edited_prompt"
      );
      const alwaysRunWidget = this.widgets?.find(
        (w) => w.name === "always_run"
      );
      const alwaysRun = alwaysRunWidget?.value === true;

      if (editWidget) {
        // Always update if always_run is on, or if empty
        if (alwaysRun || !editWidget.value?.trim()) {
          editWidget.value = text;
          app.graph.setDirtyCanvas(true);
        }
      }

    };
  },
});

// ── API Key Dialog ────────────────────────────────────────────────

async function loadKeys() {
  try {
    const resp = await fetch("/image-to-prompt/api-keys");
    return await resp.json();
  } catch {
    return {};
  }
}

async function saveKeys(keys) {
  await fetch("/image-to-prompt/api-keys", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(keys),
  });
}

function showApiKeyDialog() {
  loadKeys().then((keys) => {
    const dialog = document.createElement("dialog");
    dialog.style.cssText =
      "padding:20px;border-radius:8px;border:1px solid #555;background:#2a2a2a;color:#ddd;min-width:420px;font-family:sans-serif;";

    const title = document.createElement("h3");
    title.textContent = "API Key 설정";
    title.style.cssText = "margin:0 0 16px 0;font-size:16px;";
    dialog.appendChild(title);

    const inputs = {};

    for (const provider of PROVIDERS) {
      const configKey = KEY_NAMES[provider];
      const saved = keys[configKey] || "";

      const row = document.createElement("div");
      row.style.cssText = "margin-bottom:12px;";

      const label = document.createElement("label");
      label.textContent = provider;
      label.style.cssText =
        "display:block;margin-bottom:4px;font-weight:bold;font-size:13px;";

      const input = document.createElement("input");
      input.type = "text";
      input.value = saved;
      input.placeholder = `${provider} API Key`;
      input.style.cssText =
        "width:100%;padding:6px 8px;border-radius:4px;border:1px solid #555;background:#1a1a1a;color:#ddd;font-size:13px;box-sizing:border-box;";

      inputs[configKey] = input;
      row.appendChild(label);
      row.appendChild(input);
      dialog.appendChild(row);
    }

    const btnRow = document.createElement("div");
    btnRow.style.cssText =
      "display:flex;justify-content:flex-end;gap:8px;margin-top:16px;";

    const cancelBtn = document.createElement("button");
    cancelBtn.textContent = "취소";
    cancelBtn.style.cssText =
      "padding:6px 16px;border-radius:4px;border:1px solid #555;background:#3a3a3a;color:#ddd;cursor:pointer;";
    cancelBtn.onclick = () => {
      dialog.close();
      dialog.remove();
    };

    const saveBtn = document.createElement("button");
    saveBtn.textContent = "저장";
    saveBtn.style.cssText =
      "padding:6px 16px;border-radius:4px;border:none;background:#4a9eff;color:#fff;cursor:pointer;font-weight:bold;";
    saveBtn.onclick = async () => {
      const newKeys = {};
      for (const [key, input] of Object.entries(inputs)) {
        newKeys[key] = input.value.trim();
      }
      await saveKeys(newKeys);
      // Clear model cache so new keys trigger fresh model fetch
      for (const p of PROVIDERS) delete modelCache[p];
      dialog.close();
      dialog.remove();
    };

    btnRow.appendChild(cancelBtn);
    btnRow.appendChild(saveBtn);
    dialog.appendChild(btnRow);

    document.body.appendChild(dialog);
    dialog.showModal();
  });
}
