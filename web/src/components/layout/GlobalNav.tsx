import { NavLink } from "react-router-dom";

const ITEMS: { to: string; label: string; end?: boolean }[] = [
  { to: "/", label: "个股", end: true },
  { to: "/portfolios", label: "组合" },
  { to: "/strategies", label: "策略" },
  { to: "/market", label: "市场" },
];

export function GlobalNav() {
  return (
    <header className="global-nav">
      <div className="home-brand">
        <span>知</span>
        <b>知研</b>
        <em>QUANT</em>
      </div>
      <nav aria-label="主菜单">
        {ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) => (isActive ? "active" : undefined)}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
    </header>
  );
}
