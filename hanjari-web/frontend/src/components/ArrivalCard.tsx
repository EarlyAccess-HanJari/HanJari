import { useEffect, useState } from "react";
import type { PredictItem } from "../types";
import { mmss, stopsAwayText } from "../utils/format";
import s from "./ArrivalCard.module.css";

interface Props {
  item: PredictItem;
  stale: boolean;
  fetchedAt: number;  // 응답을 받은 시각(ms). eta_sec 를 여기서부터 1초씩 줄인다
}

/** 도착 시간 1초 카운트다운.
 *  수집 스냅샷 간격(07~19시 27초, 19~22시 40초, 그 외 150초)만큼 실제와 어긋날 수 있음 — 새로고침 때마다 바로잡힘.
 *  끄려면 false (받은 eta_sec 를 그대로 표시) */
const COUNTDOWN = true;
const SOON_SEC = 60;  // 남은 시간이 이보다 적으면(1분 미만) '곧 도착'

export default function ArrivalCard({ item, stale, fetchedAt }: Props) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!COUNTDOWN) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  // 받은 시각 기준이라 스냅샷 나이(최대 약 27초)만큼은 실제보다 늦게 줄 수 있음 — 다음 새로고침에서 바로잡힘
  const left = COUNTDOWN ? Math.max(0, item.eta_sec - Math.floor((now - fetchedAt) / 1000)) : item.eta_sec;
  const t = mmss(left);
  return (
    <section className={s.card} aria-label="지금 오는 버스" data-testid="arrival">
      {stale && (
        <div className={s.stale} role="status" data-testid="notice-stale">
          버스 정보가 오래됐어요. 실제와 다를 수 있어요.
        </div>
      )}
      {/* 오래된 정보(수집 중단·새벽)면 몇 시간 전 버스를 카운트다운하게 되므로 도착 시간 대신 안내만 */}
      {stale ? (
        <div className={s.body}>
          <span className={s.label}>지금 오는 버스</span>
          <span className={s.sub}>지금은 버스 위치를 확인할 수 없어요. 정류장 안내판을 확인해 주세요.</span>
        </div>
      ) : (
      <div className={s.body}>
        <span className={s.label}>지금 오는 버스</span>
        <div className={s.row}>
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
          <span className={s.away}>{stopsAwayText(item.stops_away)}</span>
        </div>
        <span className={s.sub}>{item.plate} · 지금 {item.r_now}명 타고 있어요</span>
      </div>
      )}
    </section>
  );
}
