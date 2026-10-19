import { useEffect, useRef } from "react";
import { ROUTES } from "../types";
import type { RouteCode } from "../types";
import s from "./StopSheet.module.css";

interface Props {
  route: RouteCode;
  stop: string;
  onPick: (route: RouteCode, stop: string) => void;
  onClose: () => void;
}

export default function StopSheet({ route, stop, onPick, onClose }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { ref.current?.focus(); }, []);

  return (
    <div className={s.backdrop} onClick={onClose}>
      <div ref={ref} className={s.sheet} role="dialog" aria-modal="true" aria-labelledby="sheet-title" tabIndex={-1}
        onClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.key === "Escape" && onClose()}>
        <div className={s.head}>
          <h2 id="sheet-title" className={s.title}>정류장 고르기</h2>
          <button type="button" className={s.close} onClick={onClose} aria-label="닫기">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" aria-hidden="true"><path d="M6 6l12 12" /><path d="M18 6L6 18" /></svg>
          </button>
        </div>
        {(Object.keys(ROUTES) as RouteCode[]).map((code) => (
          <div key={code} className={s.group}>
            <span className={`${s.routeChip} ${s[code]}`}>{ROUTES[code].name}</span>
            {ROUTES[code].stops.map((st) => {
              const on = code === route && st.stop === stop;
              return (
                <button key={st.stop} type="button" className={`${s.stop} ${on ? s.on : ""}`} aria-current={on}
                  onClick={() => onPick(code, st.stop)} data-testid={`stop-${code}-${st.stop}`}>
                  <span className={s.text}>
                    <span className={s.name}>{st.name}</span>
                    <span className={s.ars}>ARS {st.ars}</span>
                  </span>
                  {on && (
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
                  )}
                </button>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
