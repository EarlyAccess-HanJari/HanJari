import { useEffect, useState } from "react";
import { currentScenario } from "../api/predict";
import type { Scenario } from "../api/predict";
import s from "./DevSwitcher.module.css";

/** 개발용 상태 전환 (목업 모드에서만 보임 — 운영 빌드엔 없음).
 *  상태를 바로 바꿔 보며 시선이 흔들리는지 확인. 입력칸 위치·카드 높이를 같이 보여줌 */
const ITEMS: [Scenario | null, string][] = [
  [null, "목업 기본"], ["loading", "로딩"], ["ok", "여유"], ["tight", "빠듯"], ["hard", "어려움"],
  ["wide", "판단 일러요"], ["stale", "보류"], ["night", "운행 종료"], ["down", "서버 꺼짐"], ["slow", "느림"], ["error", "입력 오류"],
];

export default function DevSwitcher({ onSwitch }: { onSwitch: (sc: Scenario | null) => void }) {
  const [open, setOpen] = useState(false);
  const [cur, setCur] = useState(currentScenario);
  const [probe, setProbe] = useState("");

  useEffect(() => {
    if (!open) return;
    const t = setInterval(() => {
      const box = (id: string) => document.querySelector(`[data-testid="${id}"]`)?.getBoundingClientRect();
      const inp = box("n-input"), res = box("result") ?? box("skeleton");
      setProbe(`입력칸 y ${inp ? Math.round(inp.top + scrollY) : "-"} · 결과 h ${res ? Math.round(res.height) : "-"}`);
    }, 250);
    return () => clearInterval(t);
  }, [open]);

  const pick = (sc: Scenario | null) => { setCur(sc); onSwitch(sc); };
  return (
    <div className={s.dock} data-testid="dev-switcher">
      {open && (
        <div className={s.panel}>
          <div className={s.grid}>
            {ITEMS.map(([sc, label]) => (
              <button key={label} type="button" className={`${s.item} ${cur === sc ? s.on : ""}`} onClick={() => pick(sc)}>{label}</button>
            ))}
          </div>
          <p className={s.probe}>{probe}</p>
        </div>
      )}
      <button type="button" className={s.toggle} onClick={() => setOpen(!open)} aria-expanded={open}>
        {open ? "닫기" : "DEV 상태"}
      </button>
    </div>
  );
}
