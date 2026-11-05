import type { ReactNode } from "react";
import type { NoticeKind } from "./Notice";

type IconName = "wifi-off" | "cloud-off" | "clock" | "info" | "moon";

// 실제로 연결이 끊겼을 때만 빨간 끊김 아이콘. 늦어지거나 정보가 없는 것은 고장이 아니므로 모양과 색을 다르게 한다
const ICON: Record<NoticeKind, { name: IconName; color: string }> = {
  offline: { name: "wifi-off", color: "var(--bad)" },
  server_down: { name: "cloud-off", color: "var(--bad)" },
  timeout: { name: "clock", color: "var(--warn)" },
  data_delayed: { name: "clock", color: "var(--warn)" },
  no_stop: { name: "info", color: "var(--ink-2)" },
  unknown: { name: "info", color: "var(--ink-2)" },
  bad_input: { name: "info", color: "var(--ink-2)" },
  night: { name: "moon", color: "var(--ink-2)" },
};

const PATHS: Record<IconName, ReactNode> = {
  "wifi-off": <><path d="M3 3l18 18" /><path d="M8.5 16.5a5 5 0 0 1 7 0" /><path d="M5 12.5a10 10 0 0 1 4-2.3" /><path d="M14.5 10.3a10 10 0 0 1 4.5 2.2" /><path d="M12 20h.01" /></>,
  "cloud-off": <><path d="M3 3l18 18" /><path d="M8 8.2A4.5 4.5 0 0 0 7 17h9.5" /><path d="M11 6.2A6 6 0 0 1 18 11a3.5 3.5 0 0 1 2.3 5.4" /></>,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3.2 2" /></>,
  info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v5.2" /><path d="M12 7.8h.01" /></>,
  moon: <path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z" />,
};

export default function StatusIcon({ kind, size }: { kind: NoticeKind; size: number }) {
  const { name, color } = ICON[kind];
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"
      style={{ flex: "none" }} aria-hidden="true" data-icon={name}>
      {PATHS[name]}
    </svg>
  );
}
