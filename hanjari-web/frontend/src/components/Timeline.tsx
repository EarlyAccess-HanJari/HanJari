import type { PredictItem } from "../types";
import { arrivalChecking, etaText } from "../utils/format";
import LevelBadge from "./LevelBadge";
import s from "./Timeline.module.css";

const BusIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="4" y="3" width="16" height="15" rx="3" /><path d="M4 11h16" /><path d="M7 21v-3M17 21v-3" /><path d="M8 15h.01M16 15h.01" />
  </svg>
);

/** 같은 노선 정류장을 노선 순서(정류장 번호 순 = 버스가 지나가는 순서)로 세로 타임라인에 그린다.
 *  - 정류장마다 보이는 버스는 '그 정류장에 가장 먼저 오는 버스'라서 내 정류장의 버스와 다른 차일 수 있다 → '다른 버스'로 밝힌다
 *  - 버스 아이콘은 내 정류장 버스(plate)의 실제 위치: 어느 정류장에 닿기 직전이면 그 줄, 그보다 앞이면 첫 줄 위쪽에 둔다 */
export default function Timeline({ items, mine, onPick }: { items: PredictItem[]; mine: PredictItem; onPick: (i: PredictItem) => void }) {
  const ordered = [...items].sort((a, b) => Number(a.stop) - Number(b.stop));
  const at = ordered.findIndex((i) => i === mine);

  // 내 정류장 버스가 보이는 줄 중 가장 앞선(남은 정류장 수가 가장 적은) 줄 = 버스가 가장 가까이 온 정류장
  const sameBus = ordered.map((i, idx) => ({ i, idx })).filter((x) => x.i.plate === mine.plate);
  const lead = sameBus.reduce((a, b) => (b.i.stops_away < a.i.stops_away ? b : a), sameBus[0]);
  const busAtRow = lead.i.stops_away === 0;   // 0 이면 그 정류장 도착 직전 → 그 줄에 아이콘, 아니면 그 줄 위쪽 공간에 아이콘

  return (
    <section className={s.wrap} aria-label="같은 노선 앞·뒤 정류장" data-testid="timeline">
      <ol className={s.list}>
        {ordered.map((i, idx) => {
          const isMine = i === mine;
          const eta = arrivalChecking(i) ? "도착 확인 중" : etaText(i.eta_sec);
          const tag = isMine ? "내 정류장" : idx < at ? "직전" : "다음";
          const other = !isMine && i.plate !== mine.plate;
          const hasBus = busAtRow && idx === lead.idx;
          return [
            !busAtRow && idx === lead.idx && (
              <li key={`bus-${i.stop}`} className={`${s.row} ${s.gap} ${s.bus}`} data-testid="bus-marker">
                <span className={s.marker} aria-hidden="true"><BusIcon /></span>
                <span className={s.gapText}>버스 접근 중 · {mine.stops_away}정류장 전</span>
              </li>
            ),
            <li key={`${i.route}-${i.stop}`} className={`${s.row} ${isMine ? s.mine : ""} ${hasBus ? s.bus : ""}`}>
              <span className={s.marker} aria-hidden="true">{hasBus ? <BusIcon /> : null}</span>
              <button type="button" className={s.card} onClick={() => onPick(i)} data-testid={`card-${i.route}-${i.stop}`}
                aria-current={isMine ? "true" : undefined}>
                <span className={s.text}>
                  <span className={s.tag}>{tag}</span>
                  <span className={s.name}>{i.stop_name}</span>
                  <span className={s.eta}>
                    {eta === "곧 도착" || eta === "도착 확인 중" ? eta : <><b>{eta.replace(" 후", "")}</b> 후 도착</>}
                    {other && <span className={s.other}> · 다른 버스</span>}
                  </span>
                </span>
                <LevelBadge item={i} />
              </button>
            </li>,
          ];
        })}
      </ol>
    </section>
  );
}
