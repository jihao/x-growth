import { useState } from "react";

const TOOLBAR = [
  { id: "cursor", icon: "⌖", label: "光标", options: ["十字光标", "普通光标"] },
  { id: "trend", icon: "╱", label: "画线", options: ["线段", "射线"] },
  { id: "horizontal", icon: "─", label: "水平线", options: ["水平线段"] },
  { id: "shape", icon: "□", label: "形状", options: ["矩形", "椭圆"] },
  { id: "note", icon: "T", label: "文字注释", options: ["箭头注释", "价格注释", "日期注释"] },
  { id: "measure", icon: "↔", label: "测量", options: ["区间测量", "价格测量", "时间测量"] },
] as const;

type ToolId = (typeof TOOLBAR)[number]["id"];

export function DrawingToolbar({
  tool,
  toolVariant,
  locked,
  drawingsVisible,
  hasSelectedDrawing,
  onToolChange,
  onVariantChange,
  onLockedChange,
  onVisibleChange,
  onDelete,
}: {
  tool: string;
  toolVariant: Record<string, string>;
  locked: boolean;
  drawingsVisible: boolean;
  hasSelectedDrawing: boolean;
  onToolChange: (id: ToolId) => void;
  onVariantChange: (tool: string, variant: string) => void;
  onLockedChange: (locked: boolean) => void;
  onVisibleChange: (visible: boolean) => void;
  onDelete: () => void;
}) {
  const [toolMenu, setToolMenu] = useState<string | null>(null);

  const glyphClass = (id: string) => {
    if (id === "cursor") {
      return toolVariant.cursor === "普通光标"
        ? "tool-glyph mouse-pointer-icon"
        : "tool-glyph crosshair-tool-icon";
    }
    if (id === "shape") return "tool-glyph shape-tool-icon";
    return "tool-glyph";
  };

  const glyphContent = (id: (typeof TOOLBAR)[number]["id"], icon: string) => {
    if (id === "cursor") return "";
    if (id === "shape") return toolVariant.shape === "椭圆" ? "○" : "□";
    return icon;
  };

  return (
    <aside className="drawing-toolbar" aria-label="画线工具栏">
      {TOOLBAR.map((item) => (
        <button
          key={item.id}
          type="button"
          className={tool === item.id ? "active" : ""}
          title={`${item.label}；再次点击选择类型`}
          aria-label={item.label}
          onClick={() => {
            if (tool === item.id) {
              setToolMenu(toolMenu === item.id ? null : item.id);
            } else {
              onToolChange(item.id);
              setToolMenu(null);
            }
          }}
        >
          <span className={glyphClass(item.id)}>
            {glyphContent(item.id, item.icon)}
          </span>
          <small>›</small>
        </button>
      ))}
      {toolMenu && (
        <div className="tool-options">
          {TOOLBAR.find((item) => item.id === toolMenu)?.options.map((option) => (
            <button
              key={option}
              type="button"
              className={toolVariant[toolMenu] === option ? "selected" : ""}
              onClick={() => {
                onVariantChange(toolMenu, option);
                setToolMenu(null);
              }}
            >
              {option}
            </button>
          ))}
        </div>
      )}
      <i />
      <button
        type="button"
        className={locked ? "active" : ""}
        onClick={() => onLockedChange(!locked)}
        title={locked ? "解锁画线" : "锁定画线"}
        aria-label={locked ? "解锁画线" : "锁定画线"}
      >
        <span className={`lock-icon ${locked ? "locked" : ""}`} />
      </button>
      <button
        type="button"
        className={!drawingsVisible ? "active" : ""}
        onClick={() => onVisibleChange(!drawingsVisible)}
        title="显示或隐藏画线"
        aria-label="显示或隐藏画线"
      >
        <span className={`eye-icon ${drawingsVisible ? "" : "hidden"}`} />
      </button>
      <button
        type="button"
        className={`delete-drawing ${hasSelectedDrawing && !locked ? "enabled" : ""}`}
        disabled={!hasSelectedDrawing || locked}
        onClick={onDelete}
        title={
          hasSelectedDrawing ? "删除选中的画线" : "请先用普通光标选中画线"
        }
        aria-label="删除选中的画线"
      >
        <span className="trash-icon" />
      </button>
    </aside>
  );
}

export type { ToolId };
