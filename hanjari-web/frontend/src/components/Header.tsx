import { ROUTES } from "../types";
import type { RouteCode } from "../types";
import s from "./Header.module.css";

interface Props {
  route: RouteCode;
  stop: string;
  status: { text: string; tone: "normal" | "warn" | "bad" };
  refreshing: boolean;
  onRefresh: () => void;
  onOpenStops: () => void;
  onAbout: () => void;
}

export default function Header({ route, stop, status, refreshing, onRefresh, onOpenStops, onAbout }: Props) {
  const st = ROUTES[route].stops.find((x) => x.stop === stop);
  return (
    <header className={s.header}>
      <div className={s.line}>
        <button type="button" className={s.stopBtn} onClick={onOpenStops} aria-label={`정류장 바꾸기, 지금 ${st?.name ?? stop}`} data-testid="stop-switch">
          <span className={`${s.routeChip} ${s[route]}`}>{ROUTES[route].name}</span>
          <span className={s.name} data-testid="stop-name">{st?.name ?? stop}</span>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M6 9l6 6 6-6" />
          </svg>
        </button>
        <div className={s.actions}>
          <button type="button" className={s.refresh} onClick={onAbout} aria-label="이 안내는 어떻게 나왔나요" data-testid="about">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <circle cx="12" cy="12" r="9" /><path d="M12 11v5.2" /><path d="M12 7.8h.01" />
            </svg>
          </button>
          <button type="button" className={s.refresh} onClick={onRefresh} disabled={refreshing}
            aria-label="버스 정보 새로고침" data-testid="refresh">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M20 11a8 8 0 1 0-2.3 5.7" /><path d="M20 4v7h-7" />
            </svg>
          </button>
        </div>
      </div>
      <p className={`${s.status} ${s[status.tone]}`} aria-live="polite">{status.text}</p>
    </header>
  );
}
