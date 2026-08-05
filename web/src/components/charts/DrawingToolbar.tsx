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
  return (
    <div className="drawing-toolbar">
      {TOOLBAR.map((item) => (
        <div key={item.id} className="tool-group">
          <button
            type="button"
            className={tool === item.id ? "active" : ""}
            title={item.label}
            onClick={() => onToolChange(item.id)}
          >
            {item.icon}
          </button>
          {tool === item.id && (
            <select
              value={toolVariant[item.id] ?? item.options[0]}
              onChange={(event) => onVariantChange(item.id, event.target.value)}
              aria-label={`${item.label}选项`}
            >
              {item.options.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          )}
        </div>
      ))}
      <button type="button" className={locked ? "active" : ""} onClick={() => onLockedChange(!locked)}>
        {locked ? "锁定" : "未锁"}
      </button>
      <button
        type="button"
        className={drawingsVisible ? "active" : ""}
        onClick={() => onVisibleChange(!drawingsVisible)}
      >
        {drawingsVisible ? "显示画线" : "隐藏画线"}
      </button>
      <button type="button" disabled={!hasSelectedDrawing} onClick={onDelete}>
        删除选中
      </button>
    </div>
  );
}

export type { ToolId };
