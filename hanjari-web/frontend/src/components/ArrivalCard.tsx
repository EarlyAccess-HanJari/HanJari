import { useEffect, useReducer, useRef } from "react";
import type { PredictItem } from "../types";
import { arrivalAt, etaText, mmss, pct, stopsAwayText, verdict } from "../utils/format";
import s from "./ArrivalCard.module.css";

interface Props {
  item: PredictItem;
  stale: boolean;
  fetchedAt: number;  // 응답을 받은 시각(ms)
  invalid: boolean;   // 입력이 잘못됐으면 이전 인원으로 계산한 판정을 보이지 않는다
}

/** 도착 시간 1초 카운트다운.
 *  eta_sec 는 스냅샷(updated) 시각의 값이라 스냅샷 시각부터 센다 → 같은 스냅샷을 다시 받아도 숫자가 되감기지 않음.
 *  끄려면 false (받은 eta_sec 를 그대로 표시) */
const COUNTDOWN = true;
const SOON_SEC = 60;    // 남은 시간이 이보다 적으면(1분 미만) '곧 도착'
const DEADBAND_SEC = 15;   // 서버 예정과 화면 값 차이가 이 안쪽이면 무시 — 버스 API ETA 의 잔떨림에 숫자가 튀지 않게
const SETTLED_SEC = 3;     // 보정을 시작하면 차이가 이만큼 줄 때까지 이어감
const SNAP_SEC = 120;      // 이보다 크게 어긋나면 보정이 의미 없으니 바로 맞춤
const SLEW = 0.5;          // 보정 중 시계 속도 ±50% — 숫자가 뒤로 늘거나 점프하지 않고 천천히 따라감
const GAP_RESET_MS = 5000; // 탭이 오래 멈췄다 돌아오면 바로 맞춤

/** 화면에 보일 남은 초. 서버 예정 시각(target)이 크게 바뀌어도 점프하지 않고 시계를 조금 빠르게/느리게 돌려 따라간다.
 *  속도가 항상 0보다 커서 7분 9초 → 7분 31초 같은 역주행이 없다. */
function useCountdown(key: string, target: number): number {
  const [, tick] = useReducer((n: number) => n + 1, 0);
  const ref = useRef<{ key: string; shown: number; last: number; fixing: boolean } | null>(null);
  useEffect(() => {
    if (!COUNTDOWN) return;
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, []);

  const now = Date.now();
  const want = (target - now) / 1000;
  let c = ref.current;
  if (!c || c.key !== key || now - c.last > GAP_RESET_MS) {
    c = ref.current = { key, shown: want, last: now, fixing: false };
  } else {
    const dt = (now - c.last) / 1000;
    c.last = now;
    const gap = want - c.shown;  // + : 서버가 더 늦게 도착한다고 함
    if (Math.abs(gap) > SNAP_SEC) {
      c.shown = want; c.fixing = false;
    } else {
      if (Math.abs(gap) > DEADBAND_SEC) c.fixing = true;
      else if (Math.abs(gap) <= SETTLED_SEC) c.fixing = false;
      c.shown -= dt * (c.fixing ? (gap > 0 ? 1 - SLEW : 1 + SLEW) : 1);
    }
  }
  return Math.max(0, Math.ceil(c.shown));
}

export default function ArrivalCard({ item, stale, fetchedAt, invalid }: Props) {
  const key = `${item.route}-${item.stop}-${item.plate}`;
  const ticking = useCountdown(key, arrivalAt(item, fetchedAt));
  const left = COUNTDOWN ? ticking : item.eta_sec;
  const t = mmss(left);
  const v = verdict(item);
  const showP = item.level !== "확률 보류" && item.level !== "판단하기 일러요";
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
          {!invalid && (
            <span className={s.verdict} data-testid="verdict">{v.badge}{showP ? ` · ${pct(item.p_board)}%` : ""}</span>
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
