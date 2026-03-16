import { app } from "../../scripts/app.js";

const SECTION_LABELS = {
  pov: "시점 (POV)",
  character: "캐릭터",
  action: "행동",
  clothing: "의상",
  viewer_action: "시점자 행동",
  background: "배경",
};

const SECTIONS = Object.keys(SECTION_LABELS);
const PICK_SUFFIX = "_pick";
const DEFAULT_PICK = "-- 선택 --";

// ── Preset Manager Dialog ──────────────────────────────────────────

let managerDialog = null;

function createManagerDialog() {
  if (managerDialog) return managerDialog;

  const overlay = document.createElement("div");
  Object.assign(overlay.style, {
    display: "none",
    position: "fixed",
    top: "0",
    left: "0",
    width: "100%",
    height: "100%",
    background: "rgba(0,0,0,0.6)",
    zIndex: "10001",
    justifyContent: "center",
    alignItems: "center",
  });

  const panel = document.createElement("div");
  Object.assign(panel.style, {
    background: "#1e1e1e",
    color: "#eee",
    borderRadius: "12px",
    padding: "24px",
    width: "600px",
    maxHeight: "80vh",
    overflowY: "auto",
    fontFamily: "sans-serif",
    fontSize: "13px",
  });

  overlay.appendChild(panel);
  document.body.appendChild(overlay);
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) overlay.style.display = "none";
  });

  managerDialog = { overlay, panel };
  return managerDialog;
}

function showManagerDialog() {
  const d = createManagerDialog();
  d.overlay.style.display = "flex";
  renderManagerContent(d.panel);
}

async function renderManagerContent(panel) {
  const presets = await fetch("/promptbuilder/presets").then((r) => r.json());
  panel.innerHTML = "";

  const titleBar = document.createElement("div");
  Object.assign(titleBar.style, {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: "16px",
  });

  const title = document.createElement("h2");
  title.textContent = "Prompt Builder - 프리셋 관리";
  Object.assign(title.style, { margin: "0", fontSize: "16px" });

  const closeBtn = document.createElement("button");
  closeBtn.textContent = "✕";
  Object.assign(closeBtn.style, {
    background: "none",
    border: "none",
    color: "#eee",
    fontSize: "18px",
    cursor: "pointer",
  });
  closeBtn.onclick = () => (managerDialog.overlay.style.display = "none");

  titleBar.appendChild(title);
  titleBar.appendChild(closeBtn);
  panel.appendChild(titleBar);

  for (const section of SECTIONS) {
    const items = presets[section] || [];

    const sectionDiv = document.createElement("div");
    Object.assign(sectionDiv.style, {
      marginBottom: "16px",
      padding: "12px",
      background: "#2a2a2a",
      borderRadius: "8px",
    });

    const header = document.createElement("div");
    Object.assign(header.style, {
      display: "flex",
      justifyContent: "space-between",
      alignItems: "center",
      marginBottom: "8px",
    });

    const label = document.createElement("span");
    label.textContent = SECTION_LABELS[section];
    Object.assign(label.style, { fontWeight: "bold", fontSize: "13px" });

    const count = document.createElement("span");
    count.textContent = `${items.length}개`;
    Object.assign(count.style, { color: "#888", fontSize: "12px" });

    header.appendChild(label);
    header.appendChild(count);
    sectionDiv.appendChild(header);

    const chipsDiv = document.createElement("div");
    Object.assign(chipsDiv.style, {
      display: "flex",
      flexWrap: "wrap",
      gap: "6px",
      marginBottom: "8px",
    });

    let dragItem = null;

    for (const item of items) {
      const chip = document.createElement("div");
      chip.draggable = true;
      chip.dataset.value = item;
      chip.dataset.section = section;
      Object.assign(chip.style, {
        display: "flex",
        alignItems: "center",
        gap: "4px",
        padding: "4px 10px",
        background: "#383838",
        borderRadius: "16px",
        fontSize: "12px",
        cursor: "grab",
        transition: "opacity 0.15s, transform 0.15s",
      });

      chip.addEventListener("dragstart", (e) => {
        dragItem = chip;
        chip.style.opacity = "0.4";
        e.dataTransfer.effectAllowed = "move";
      });

      chip.addEventListener("dragend", () => {
        chip.style.opacity = "1";
        dragItem = null;
        // Remove all drag-over highlights
        chipsDiv.querySelectorAll("[data-value]").forEach((c) => {
          c.style.borderLeft = "none";
          c.style.borderRight = "none";
        });
      });

      chip.addEventListener("dragover", (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        if (!dragItem || dragItem === chip) return;
        if (dragItem.dataset.section !== chip.dataset.section) return;

        // Highlight drop position
        const rect = chip.getBoundingClientRect();
        const midX = rect.left + rect.width / 2;
        chipsDiv.querySelectorAll("[data-value]").forEach((c) => {
          c.style.borderLeft = "none";
          c.style.borderRight = "none";
        });
        if (e.clientX < midX) {
          chip.style.borderLeft = "2px solid #4a9eff";
        } else {
          chip.style.borderRight = "2px solid #4a9eff";
        }
      });

      chip.addEventListener("drop", async (e) => {
        e.preventDefault();
        if (!dragItem || dragItem === chip) return;
        if (dragItem.dataset.section !== chip.dataset.section) return;

        const sec = chip.dataset.section;
        const allChips = [...chipsDiv.querySelectorAll("[data-value]")];
        const currentOrder = allChips.map((c) => c.dataset.value);

        const fromIdx = currentOrder.indexOf(dragItem.dataset.value);
        const toIdx = currentOrder.indexOf(chip.dataset.value);

        // Remove from old position
        currentOrder.splice(fromIdx, 1);

        // Determine insert position based on mouse
        const rect = chip.getBoundingClientRect();
        const midX = rect.left + rect.width / 2;
        let insertIdx = currentOrder.indexOf(chip.dataset.value);
        if (e.clientX >= midX) insertIdx++;

        currentOrder.splice(insertIdx, 0, dragItem.dataset.value);

        // Save new order
        await fetch(`/promptbuilder/presets/${sec}/reorder`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ items: currentOrder }),
        });
        await refreshAllPickWidgets();
        renderManagerContent(panel);
      });

      const gripIcon = document.createElement("span");
      gripIcon.textContent = "⠿";
      Object.assign(gripIcon.style, {
        color: "#666",
        fontSize: "11px",
        marginRight: "2px",
        cursor: "grab",
      });

      const text = document.createElement("span");
      text.textContent = item;
      text.title = item;
      Object.assign(text.style, {
        maxWidth: "200px",
        overflow: "hidden",
        textOverflow: "ellipsis",
        whiteSpace: "nowrap",
      });

      const delBtn = document.createElement("button");
      delBtn.textContent = "×";
      Object.assign(delBtn.style, {
        background: "none",
        border: "none",
        color: "#f66",
        cursor: "pointer",
        fontSize: "14px",
        padding: "0 2px",
        lineHeight: "1",
      });
      delBtn.onclick = async (e) => {
        e.stopPropagation();
        await fetch(`/promptbuilder/presets/${section}/delete`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: item }),
        });
        await refreshAllPickWidgets();
        renderManagerContent(panel);
      };

      chip.appendChild(gripIcon);
      chip.appendChild(text);
      chip.appendChild(delBtn);
      chipsDiv.appendChild(chip);
    }

    sectionDiv.appendChild(chipsDiv);

    const addRow = document.createElement("div");
    Object.assign(addRow.style, { display: "flex", gap: "6px" });

    const input = document.createElement("input");
    input.placeholder = "새 프리셋 입력...";
    Object.assign(input.style, {
      flex: "1",
      padding: "6px 10px",
      borderRadius: "6px",
      border: "1px solid #555",
      background: "#1e1e1e",
      color: "#eee",
      fontSize: "12px",
      outline: "none",
    });

    const addBtn = document.createElement("button");
    addBtn.textContent = "추가";
    Object.assign(addBtn.style, {
      padding: "6px 14px",
      borderRadius: "6px",
      border: "none",
      background: "#4a9eff",
      color: "#fff",
      cursor: "pointer",
      fontSize: "12px",
    });

    const doAdd = async () => {
      const val = input.value.trim();
      if (!val) return;
      await fetch(`/promptbuilder/presets/${section}/add`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: val }),
      });
      await refreshAllPickWidgets();
      renderManagerContent(panel);
    };

    addBtn.onclick = doAdd;
    input.onkeydown = (e) => {
      if (e.key === "Enter") doAdd();
    };

    addRow.appendChild(input);
    addRow.appendChild(addBtn);
    sectionDiv.appendChild(addRow);

    panel.appendChild(sectionDiv);
  }

  const notice = document.createElement("p");
  notice.textContent =
    "※ 프리셋 추가/삭제 시 노드 드롭다운에 즉시 반영됩니다.";
  Object.assign(notice.style, {
    color: "#888",
    fontSize: "11px",
    textAlign: "center",
    marginTop: "8px",
  });
  panel.appendChild(notice);
}

// ── Refresh pick widgets on all PromptBuilder nodes ────────────────

async function refreshAllPickWidgets() {
  const presets = await fetch("/promptbuilder/presets").then((r) => r.json());
  const graph = app.graph;
  if (!graph) return;

  for (const node of graph._nodes || []) {
    if (node.comfyClass !== "PromptBuilder") continue;

    for (const section of SECTIONS) {
      const widgetName = section + PICK_SUFFIX;
      const widget = node.widgets?.find((w) => w.name === widgetName);
      if (!widget) continue;

      const newOptions = [DEFAULT_PICK, ...(presets[section] || [])];
      widget.options = { values: newOptions };
      if (widget.value && !newOptions.includes(widget.value)) {
        widget.value = DEFAULT_PICK;
      }
    }

    node.setDirtyCanvas(true, true);
  }
}

// ── Grammar Correction ─────────────────────────────────────────────

async function grammarCorrect(text) {
  const res = await fetch("/promptbuilder/grammar", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) return text;
  const data = await res.json();
  return data.corrected || text;
}

async function grammarCorrectWidget(widget, node) {
  const original = widget.value || "";
  if (!original.trim()) return;

  widget.value = "교정 중...";
  node.setDirtyCanvas(true, true);

  const corrected = await grammarCorrect(original);
  widget.value = corrected;
  node.setDirtyCanvas(true, true);
}

async function grammarCorrectAll(node) {
  for (const section of SECTIONS) {
    const widget = node.widgets?.find((w) => w.name === section);
    if (widget && widget.value?.trim()) {
      await grammarCorrectWidget(widget, node);
    }
  }
}

// ── Register Extension ─────────────────────────────────────────────

app.registerExtension({
  name: "promptbuilder.presetManager",

  async setup() {
    // Floating button
    const floatBtn = document.createElement("button");
    floatBtn.textContent = "프리셋 관리";
    Object.assign(floatBtn.style, {
      position: "fixed",
      bottom: "16px",
      right: "16px",
      zIndex: "9999",
      padding: "8px 16px",
      borderRadius: "8px",
      border: "none",
      background: "#4a9eff",
      color: "#fff",
      fontSize: "13px",
      fontWeight: "bold",
      cursor: "pointer",
      boxShadow: "0 2px 8px rgba(0,0,0,0.3)",
    });
    floatBtn.onclick = showManagerDialog;
    document.body.appendChild(floatBtn);

    // Classic menu
    const menu = document.querySelector(".comfy-menu");
    if (menu) {
      const btn = document.createElement("button");
      btn.textContent = "프리셋 관리";
      btn.onclick = showManagerDialog;
      menu.appendChild(btn);
    }
  },

  async nodeCreated(node) {
    if (node.comfyClass !== "PromptBuilder") return;

    // Right-click context menu
    const origMenu = node.getExtraMenuOptions;
    node.getExtraMenuOptions = function (_, options) {
      if (origMenu) origMenu.apply(this, arguments);
      options.unshift(
        {
          content: "프리셋 관리",
          callback: () => showManagerDialog(),
        },
        {
          content: "전체 문법 교정",
          callback: () => grammarCorrectAll(node),
        },
      );

      // Per-section grammar correction
      for (const section of SECTIONS) {
        const textWidget = node.widgets?.find((w) => w.name === section);
        if (textWidget && textWidget.value?.trim()) {
          options.push({
            content: `문법 교정: ${SECTION_LABELS[section]}`,
            callback: () => grammarCorrectWidget(textWidget, node),
          });
        }
      }
    };

    // Wire up pick widgets: when a preset is selected from dropdown,
    // append it to the corresponding text widget
    for (const section of SECTIONS) {
      const pickWidget = node.widgets?.find((w) => w.name === section + PICK_SUFFIX);
      const textWidget = node.widgets?.find((w) => w.name === section);
      if (!pickWidget || !textWidget) continue;

      pickWidget.callback = (value) => {
        if (value === DEFAULT_PICK) return;

        // Remove trailing commas/spaces and fix double commas
        const current = (textWidget.value || "").replace(/,(\s*,)+/g, ",").replace(/,\s*$/, "").trim();
        if (current) {
          textWidget.value = current + ", " + value + ", ";
        } else {
          textWidget.value = value + ", ";
        }

        // Reset picker back to default
        setTimeout(() => {
          pickWidget.value = DEFAULT_PICK;
          node.setDirtyCanvas(true, true);
        }, 50);
      };
    }
  },
});
