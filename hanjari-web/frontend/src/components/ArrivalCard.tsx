import { useEffect, useState } from "react";
import type { PredictItem } from "../types";
import { arrivalAt, mmss, stopsAwayText } from "../utils/format";
import s from "./ArrivalCard.module.css";

interface Props {
  item: PredictItem;
  stale: boolean;
  fetchedAt: number;  // 응답을 받은 시각(ms)
}

/** 도착 시간 1초 카운트다운.
 *  eta_sec 는 스냅샷(updated) 시각의 값이라 스냅샷 시각부터 센다 → 같은 스냅샷을 다시 받아도 숫자가 되감기지 않음.
 *  끄려면 false (받은 eta_sec 를 그대로 표시) */
const COUNTDOWN = true;
const SOON_SEC = 60;    // 남은 시간이 이보다 적으면(1분 미만) '곧 도착'
const JITTER_SEC = 15;  // 같은 버스의 도착 예정이 이만큼 안쪽으로만 바뀌면 무시 — 버스 API ETA 의 잔떨림에 숫자가 튀지 않게

export default function ArrivalCard({ item, stale, fetchedAt }: Props) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!COUNTDOWN) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  // 같은 정류장·같은 버스면 직전 도착 예정 시각을 이어 쓴다 (차이가 크면 새 값으로 바로잡음)
  const stopKey = `${item.route}-${item.stop}`;
  const key = `${stopKey}-${item.vehicle_id ?? ""}-${item.plate}`;
  const [vehicle, setVehicle] = useState({ stopKey, key, plate: item.plate, previous: "" });
  const currentVehicle = vehicle.key === key ? vehicle : {
    stopKey, key, plate: item.plate, previous: vehicle.stopKey === stopKey ? vehicle.plate : "",
  };
  if (vehicle.key !== key) setVehicle(currentVehicle);
  const at = arrivalAt(item, fetchedAt);
  const [held, setHeld] = useState({ key, at });
  const keep = held.key === key && Math.abs(held.at - at) <= JITTER_SEC * 1000;
  if (!keep) setHeld({ key, at });  // 렌더 중 상태 맞추기(React 권장 방식) — 이번 렌더는 아래에서 새 값으로 바로 계산
  const target = keep ? held.at : at;

  const left = COUNTDOWN ? Math.max(0, Math.ceil((target - now) / 1000)) : item.eta_sec;
  const t = mmss(left);
  return (
    <section className={s.arrival} aria-label="남은 시간" data-testid="arrival">
      <div className={s.vehicle} data-testid="vehicle">
        <span>조회 차량</span><strong>{item.plate || "차량번호 확인 중"}</strong>
      </div>
      <p className={s.vehicleHint}>선택한 정류장에 오는 첫 번째 버스 기준이에요.</p>
      {currentVehicle.previous && (
        <div className={s.changed} role="status" data-testid="vehicle-changed">
          안내 차량이 바뀌었어요.<br />
          {currentVehicle.previous} → {item.plate}
        </div>
      )}
      {stale && (
        <div className={s.stale} role="status" data-testid="notice-stale">
          버스 정보가 오래됐어요. 실제와 다를 수 있어요.
        </div>
      )}
      {/* 오래된 정보(수집 중단·새벽)면 몇 시간 전 버스를 카운트다운하게 되므로 도착 시간 대신 안내만 */}
      {stale ? (
        <div className={s.row}>
          <span className={s.label}>남은 시간</span>
          <span className={s.sub}>지금은 버스 위치를 확인할 수 없어요. 정류장 안내판을 확인해 주세요.</span>
        </div>
      ) : (
        <div className={s.row}>
          <span className={s.label}>남은 시간</span>
          <span className={s.group}>
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
            <span className={s.away}>· {stopsAwayText(item.stops_away)}</span>
          </span>
        </div>
      )}
    </section>
  );
}
