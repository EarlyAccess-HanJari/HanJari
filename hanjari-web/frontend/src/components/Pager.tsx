import { useRef, useState } from "react";
import type { ReactNode, TouchEvent } from "react";
import s from "./Pager.module.css";

const SWIPE_PX = 56;     // 이만큼 끌면 넘어감
const INTENT_PX = 10;    // 가로/세로 의도를 가리는 최소 이동

/** 좌우 2장 슬라이드. 탭으로도, 화면을 좌우로 밀어도 넘어간다.
 *  세로로 밀 땐 가로 이동을 막지 않게 touch-action: pan-y 로 맡기고, 가로 의도일 때만 따라 움직인다 */
export default function Pager({ index, onChange, children }: { index: number; onChange: (i: number) => void; children: [ReactNode, ReactNode] }) {
  const [dx, setDx] = useState(0);
  const [dragging, setDragging] = useState(false);
  const dxRef = useRef(0);  // 렌더를 기다리지 않고 마지막 이동량을 읽기 위해
  const start = useRef<{ x: number; y: number; dir: "h" | "v" | null } | null>(null);
  const last = children.length - 1;

  const onStart = (e: TouchEvent) => {
    const t = e.touches[0];
    start.current = { x: t.clientX, y: t.clientY, dir: null };
  };
  const onMove = (e: TouchEvent) => {
    const st = start.current;
    if (!st) return;
    const t = e.touches[0];
    const mx = t.clientX - st.x;
    const my = t.clientY - st.y;
    if (st.dir === null) {
      if (Math.abs(mx) < INTENT_PX && Math.abs(my) < INTENT_PX) return;
      st.dir = Math.abs(mx) > Math.abs(my) ? "h" : "v";
    }
    if (st.dir !== "h") return;
    // 양 끝에선 저항을 줘서 더 못 간다는 느낌
    const edge = (index === 0 && mx > 0) || (index === last && mx < 0);
    setDragging(true);
    dxRef.current = edge ? mx * 0.25 : mx;
    setDx(dxRef.current);
  };
  const onEnd = () => {
    const st = start.current;
    start.current = null;
    const d = dxRef.current;
    dxRef.current = 0;
    if (st?.dir === "h") {
      if (d <= -SWIPE_PX && index < last) onChange(index + 1);
      else if (d >= SWIPE_PX && index > 0) onChange(index - 1);
    }
    setDragging(false);
    setDx(0);
  };

  return (
    <div className={s.viewport} onTouchStart={onStart} onTouchMove={onMove} onTouchEnd={onEnd} onTouchCancel={onEnd}
      data-testid="pager">
      <div className={`${s.track} ${dragging ? s.drag : ""}`}
        style={{ transform: `translateX(calc(${-index * 50}% + ${dx}px))` }}>
        {children.map((c, i) => (
          <div key={i} id={`pane-${i}`} role="tabpanel" aria-labelledby={`tab-${i}`} className={s.pane}
            aria-hidden={index !== i} inert={index !== i}>
            {c}
          </div>
        ))}
      </div>
    </div>
  );
}
