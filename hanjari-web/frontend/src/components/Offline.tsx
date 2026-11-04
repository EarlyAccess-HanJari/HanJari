import type { ReactNode } from "react";
import { ROUTES } from "../types";
import type { RouteCode } from "../types";
import { TEXT } from "./Notice";
import type { NoticeKind } from "./Notice";
import { LoadPlaceholder } from "./LoadCompare";
import lv from "./levels.module.css";
import app from "../App.module.css";
import a from "./ArrivalCard.module.css";
import t from "./Timeline.module.css";
import s from "./Offline.module.css";

/** 첫 불러오기: 실제 카드와 같은 틀(시간 · 결론 · 대기 인원 · 차내 인원)에 반짝이는 자리표시 */
export function HeroSkeleton() {
  return (
    <section className={`${app.hero} ${lv.hold}`} role="status" aria-label="버스 정보를 불러오는 중" data-testid="hero-skeleton">
      <div className={s.block}>
        <div className={app.sk} style={{ width: 70, height: 14 }} />
        <div className={app.sk} style={{ width: "62%", height: 56, marginTop: 12 }} />
      </div>
      <div className={s.block}>
        <div className={app.sk} style={{ width: "100%", height: 8, borderRadius: 999 }} />
        <div className={app.sk} style={{ width: "74%", height: 16, marginTop: 14 }} />
      </div>
      <div className={app.sk} style={{ width: "100%", marginTop: "auto", borderRadius: 16,
        height: "calc(2 * clamp(12px, 2dvh, 20px) + 40px + clamp(8px, 1.6dvh, 16px) + clamp(36px, 5dvh, 46px))" }} />
      <div className={app.sk} style={{ width: "100%", height: 31 }} />
    </section>
  );
}

const OffIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#DC2626" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M3 3l18 18" /><path d="M8.5 16.5a5 5 0 0 1 7 0" /><path d="M5 12.5a10 10 0 0 1 4-2.3" /><path d="M14.5 10.3a10 10 0 0 1 4.5 2.2" /><path d="M12 20h.01" />
  </svg>
);

/** 오류: 화면 전체를 갈아엎지 않고 카드 안에 안내만 — 대기 인원 입력은 그대로 쓸 수 있다 */
export function HeroError({ kind, detail, onRetry, retrying, input }:
  { kind: NoticeKind; detail?: string; onRetry: () => void; retrying: boolean; input: ReactNode }) {
  const m = TEXT[kind];
  return (
    <section className={`${app.hero} ${lv.hold}`} data-tone="hold" data-testid="hero-error" aria-busy={retrying}>
      <div className={s.block}>
        <div className={a.top}><span className={a.label}>이번 버스</span></div>
        <p className={s.noinfo}>정보 없음</p>
      </div>
      <div className={s.box} role="status" data-testid={`notice-${kind}`}>
        <div className={s.boxTop}>
          <span className={s.title}><OffIcon />{m.title}</span>
          <button type="button" className={s.retry} onClick={onRetry} disabled={retrying}>
            {retrying ? "연결 중…" : "다시 시도"}
          </button>
        </div>
        {m.body && <p className={s.body}>{m.body}</p>}
        {detail && <p className={s.detail}>{detail}</p>}
      </div>
      {input}
      <LoadPlaceholder />
    </section>
  );
}

/** 오류일 때 두 번째 화면: 정류장 순서는 보여주되 도착 정보만 비워 둔다 */
export function TimelinePlaceholder({ route, stop, onPick }: { route: RouteCode; stop: string; onPick: (route: RouteCode, stop: string) => void }) {
  const stops = [...ROUTES[route].stops].sort((x, y) => Number(x.stop) - Number(y.stop));
  const at = stops.findIndex((x) => x.stop === stop);
  return (
    <section className={t.wrap} aria-label="같은 노선 앞·뒤 정류장" data-testid="timeline">
      <ol className={t.list}>
        {stops.map((x, idx) => {
          const isMine = idx === at;
          return (
            <li key={x.stop} className={`${t.row} ${isMine ? t.mine : ""}`}>
              <span className={t.marker} aria-hidden="true" />
              <button type="button" className={t.card} onClick={() => onPick(route, x.stop)} data-testid={`card-${route}-${x.stop}`}
                aria-current={isMine ? "true" : undefined}>
                <span className={t.text}>
                  <span className={t.tag}>{isMine ? "내 정류장" : idx < at ? "직전" : "다음"}</span>
                  <span className={t.name}>{x.name}</span>
                  <span className={t.eta}>도착 정보 없음</span>
                </span>
                <span className={s.dash}>—</span>
              </button>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
