import { useEffect, useRef, useState } from "react";
import type { PredictItem } from "../types";
import { etaText, stopsAwayText } from "../utils/format";
import LevelBadge, { LEVEL_CLASS } from "./LevelBadge";
import s from "./OtherStops.module.css";

/** 같은 노선의 다른 탑승 정류장 — 한 정류장 앞뒤로 걸어가 볼지 판단용.
 *  화면 맨 아래 한 줄로 접어 두고, 누르면 아래에서 올라오는 목록으로 봄 (핵심 화면 배치는 그대로) */
export default function OtherStops({ items, onPick }: { items: PredictItem[]; onPick: (i: PredictItem) => void }) {
  const [open, setOpen] = useState(false);
  // 불러오기 전에도 같은 자리를 차지해 둠 → 응답이 와도 위 카드·입력칸이 밀리지 않음
  if (items.length === 0) {
    return <div className={`${s.bar} ${s.empty}`} aria-hidden="true"><span className={s.barTitle}>같은 노선 다른 정류장</span></div>;
  }
  return (
    <>
      <button type="button" className={s.bar} onClick={() => setOpen(true)} aria-haspopup="dialog" data-testid="other-stops">
        <span className={s.barTitle}>같은 노선 다른 정류장 {items.length}곳</span>
        {/* 좁은 화면에서도 잘리지 않게 단계는 색 점으로만 (자세한 건 펼친 목록에서) */}
        <span className={s.dots}>
          {items.map((i) => <span key={`${i.route}-${i.stop}`} className={`${s.dot} ${LEVEL_CLASS[i.level]}`} title={`${i.stop_name} ${i.level}`} />)}
        </span>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M6 15l6-6 6 6" /></svg>
      </button>
      {open && <Sheet items={items} onPick={(i) => { setOpen(false); onPick(i); }} onClose={() => setOpen(false)} />}
    </>
  );
}

function Sheet({ items, onPick, onClose }: { items: PredictItem[]; onPick: (i: PredictItem) => void; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { ref.current?.focus(); }, []);
  return (
    <div className={s.backdrop} onClick={onClose}>
      <div ref={ref} className={s.sheet} role="dialog" aria-modal="true" aria-labelledby="other-title" tabIndex={-1}
        onClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.key === "Escape" && onClose()}>
        <div className={s.head}>
          <h2 id="other-title" className={s.title}>같은 노선 다른 정류장</h2>
          <button type="button" className={s.close} onClick={onClose} aria-label="닫기">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" aria-hidden="true"><path d="M6 6l12 12" /><path d="M18 6L6 18" /></svg>
          </button>
        </div>
        {items.map((i) => (
          <button key={`${i.route}-${i.stop}`} type="button" className={s.item} onClick={() => onPick(i)}
            data-testid={`card-${i.route}-${i.stop}`}>
            <span className={s.text}>
              <span className={s.name}>{i.stop_name}</span>
              <span className={s.sub}>{stopsAwayText(i.stops_away)} · {etaText(i.eta_sec)}</span>
            </span>
            <LevelBadge level={i.level} />
          </button>
        ))}
      </div>
    </div>
  );
}
