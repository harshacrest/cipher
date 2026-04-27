"use client";

import { ReactNode, useState } from "react";

interface Props {
  title: string;
  subtitle?: string;
  defaultOpen?: boolean;
  children: ReactNode;
  rightSlot?: ReactNode;
}

/**
 * Research Framework's Collapsible wrapper. Panel + panel-head whose header
 * click toggles the body, with a small rotating chevron on the left of the
 * title. Used on every analytical section in StrategyPanel.
 */
export default function Collapsible({
  title,
  subtitle,
  defaultOpen = true,
  children,
  rightSlot,
}: Props) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="panel">
      <div
        className="panel-head"
        onClick={() => setOpen((o) => !o)}
        style={{ cursor: "pointer", userSelect: "none" }}
      >
        <h2 style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span
            style={{
              fontSize: 10,
              color: "var(--accent)",
              transform: open ? "rotate(90deg)" : "rotate(0deg)",
              transition: "transform 120ms ease",
              display: "inline-block",
              width: 10,
            }}
          >
            ▶
          </span>
          {title}
        </h2>
        <span style={{ display: "flex", gap: 12, alignItems: "center" }}>
          {subtitle && <span className="muted">{subtitle}</span>}
          {rightSlot}
        </span>
      </div>
      {open && children}
    </div>
  );
}
