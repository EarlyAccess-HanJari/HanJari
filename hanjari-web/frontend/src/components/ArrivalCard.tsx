import type { PredictItem } from "../types";
import { arrivalAt, etaText, mmss, pct, stopsAwayText, verdict } from "../utils/format";
import type { ArrivalState, ProbState } from "../utils/format";
import s from "./ArrivalCard.module.css";

interface Props {
  item: PredictItem;
  state: ArrivalState;
  fetchedAt: number;  // 응답을 받은 시각(ms)
  now: number;
  prob: ProbState;    // 지금 입력한 인원의 확률이 아니면 이전 인원으로 계산한 판정을 보이지 않는다
}

const SOON_SEC = 60;  // 남은 시간이 이보다 적으면(1분 미만) '곧 도착'

export default function ArrivalCard({ item, state, fetchedAt, now, prob }: Props) {
  // 차량/제공 시각이 바뀌면 새 ETA를 즉시 반영한다. 이전 차량의 예정 시각을 이어 쓰지 않는다.
  const left = Math.max(0, Math.ceil((arrivalAt(item, fetchedAt) - now) / 1000));
  const t = mmss(left);
  const v = verdict(item);
  const current = state === "upcoming" && prob === "current";
  const showP = current && item.level !== "확률 보류" && item.level !== "판단하기 일러요" && item.p_board != null;
  const badge = current ? v.badge : state === "upcoming" && prob === "calculating" ? "계산 중" : "확률 보류";
  const stale = state === "stale";
  return (
    <section className={s.arrival} aria-label="남은 시간" data-testid="arrival">
      {stale && (
        <div className={s.stale} role="status" data-testid="notice-stale">
          버스 정보가 오래됐어요. 실제와 다를 수 있어요.
        </div>
      )}
      <div className={s.top}>
        <span className={s.label}>이번 버스</span>
        {!stale && <span className={s.away}>{stopsAwayText(item.stops_away)}</span>}
      </div>
      {/* 오래된 정보(수집 중단·새벽)면 몇 시간 전 버스를 카운트다운하게 되므로 도착 시간 대신 안내만 */}
      {stale ? (
        <div className={s.timeRow}>
          <span className={s.sub}>지금은 버스 위치를 확인할 수 없어요. 정류장 안내판을 확인해 주세요.</span>
        </div>
      ) : (
        <div className={s.timeRow}>
          {state === "checking" ? (
            <span className={s.sub} role="status" data-testid="arrival-checking">새 도착 정보를 확인하고 있어요.</span>
          ) : (
            <span className={s.eta}>
              {left < SOON_SEC ? (
                <span className={s.soon}>곧 도착</span>
              ) : (
                <>
                  <span className={s.num}>{t.m}</span><span className={s.unit}>분</span>
                  <span className={s.num}>{t.s}</span><span className={s.unit}>초</span>
                </>
              )}
            </span>
          )}
          {prob !== "invalid" && (
            <span className={s.verdict} data-testid="verdict">
              {badge}{showP ? ` · ${pct(item.p_board!)}%` : ""}
            </span>
          )}
        </div>
      )}
      {/* 자리를 항상 잡아 둔다 — 다음 버스가 생기고 없어져도 아래 내용이 밀리지 않게 */}
      {!stale && (
        <span className={s.next}>
          {item.eta2_sec != null && <span data-testid="next-bus">다음 버스 {etaText(item.eta2_sec)}</span>}
        </span>
      )}
    </section>
  );
}
