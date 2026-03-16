import { app } from "/scripts/app.js";

const SECTION_LABELS = {
  pov: "시점 (POV)",
  character: "캐릭터",
  action: "행동",
  clothing: "의상",
  viewer_action: "시점자 행동",
  background: "배경",
};

const SECTIONS = Object.keys(SECTION_LABELS);

let dialog = null;

function createDialog() {
  if (dialog) return dialog;

  const overlay = document.createElement("div");
  Object.assign(overlay.style, {
    display: "none",
    position: "fixed",
    top: "0",
    left: "0",
    width: "100%",
    height: "100%",
    background: "rgba(0,0,0,0.6)",
    zIndex: "10000",
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
    if (e.target === overlay) hideDialog();
  });

  dialog = { overlay, panel };
  return dialog;
}

function showDialog() {
  const d = createDialog();
  d.overlay.style.display = "flex";
  renderContent(d.panel);
}

function hideDialog() {
  if (dialog) dialog.overlay.style.display = "none";
}

async function fetchPresets() {
  const res = await fetch("/promptbuilder/presets");
  return res.json();
}

async function addPreset(section, text) {
  await fetch(`/promptbuilder/presets/${section}/add`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
}

async function deletePreset(section, text) {
  await fetch(`/promptbuilder/presets/${section}/delete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
}

async function renderContent(panel) {
  const presets = await fetchPresets();

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
  closeBtn.onclick = hideDialog;

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

    for (const item of items) {
      const chip = document.createElement("div");
      Object.assign(chip.style, {
        display: "flex",
        alignItems: "center",
        gap: "4px",
        padding: "4px 10px",
        background: "#383838",
        borderRadius: "16px",
        fontSize: "12px",
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
      delBtn.onclick = async () => {
        await deletePreset(section, item);
        renderContent(panel);
      };

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
      await addPreset(section, val);
      renderContent(panel);
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
    "※ 프리셋 변경 후 ComfyUI를 재시작하면 노드 드롭다운에 반영됩니다.";
  Object.assign(notice.style, {
    color: "#888",
    fontSize: "11px",
    textAlign: "center",
    marginTop: "8px",
  });
  panel.appendChild(notice);
}

app.registerExtension({
  name: "promptbuilder.presetManager",
  async setup() {
    const menu = document.querySelector(".comfy-menu");
    if (menu) {
      const btn = document.createElement("button");
      btn.textContent = "프리셋 관리";
      btn.onclick = showDialog;
      menu.appendChild(btn);
    }
  },
});
