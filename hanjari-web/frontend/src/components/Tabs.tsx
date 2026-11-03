import s from "./Tabs.module.css";

const LABELS = ["지금 탈 수 있을까?", "앞·뒤 정류장"];

/** 애플/토스 스타일 세그먼트 컨트롤. 선택 표시(thumb)가 좌우로 미끄러진다 */
export default function Tabs({ index, onChange, disabled = false }: { index: number; onChange: (i: number) => void; disabled?: boolean }) {
  return (
    <div className={s.tabs} role="tablist" aria-label="화면 전환">
      <span className={s.thumb} style={{ transform: `translateX(${index * 100}%)` }} aria-hidden="true" />
      {LABELS.map((t, i) => (
        <button key={t} type="button" role="tab" id={`tab-${i}`} aria-selected={index === i} aria-controls={`pane-${i}`}
          className={`${s.tab} ${index === i ? s.on : ""}`} onClick={() => onChange(i)} disabled={disabled} data-testid={`tab-${i}`}>
          {t}
        </button>
      ))}
    </div>
  );
}
