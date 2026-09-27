import Link from "next/link";

const NAV_ITEMS = [
  { label: "업로드", href: "/upload" },
  { label: "분석 대시보드", href: "/dashboard" },
  { label: "상세 분석", href: "/detail-analysis" },
  { label: "예측", href: "/prediction" },
] as const;

export function TopBar({ active }: { active: (typeof NAV_ITEMS)[number]["label"] }) {
  return (
    <div className="topbar">
      <div className="brand">
        <div className="brand-mark">EB</div>
        <div className="brand-text">
          <div className="title">AI 포화도 예측 시스템</div>
          <div className="sub">세방전지 품질경영팀 · 창원공장</div>
        </div>
      </div>
      <div className="topbar-right">
        <div className="nav-links">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.label}
              href={item.href}
              className={item.label === active ? "active" : undefined}
            >
              {item.label}
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
