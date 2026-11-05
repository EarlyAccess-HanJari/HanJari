import { ROUTES } from "../types";
import type { PredictItem, RouteCode } from "../types";
import { arrivalText } from "../utils/format";
import s from "./OtherStops.module.css";

interface Props {
  route: RouteCode;
  stop: string;
  items?: PredictItem[];
  onPick: (route: RouteCode, stop: string) => void;
  now: number;
  fetchedAt: number;
}

/** 첫 화면 아래 같은 노선의 다른 정류장. 정보가 없어도(오류·불러오는 중) 줄은 그대로 두어 위쪽 카드 크기가 변하지 않게 한다.
 *  탑승 확률은 보이지 않는다. 그 정류장의 대기 인원을 모르는데 확률을 보이면 실측처럼 오해할 수 있다(2026-11-04 팀 결정) */
export default function OtherStops({ route, stop, items = [], onPick, now, fetchedAt }: Props) {
  return (
    <section className={s.wrap} aria-label="같은 노선 다른 정류장">
      <h3 className={s.title}>같은 노선 다른 정류장</h3>
      <div className={s.list}>
        {ROUTES[route].stops.filter((x) => x.stop !== stop).map((x) => {
          const i = items.find((r) => r.route === route && r.stop === x.stop);
          return (
            <button key={x.stop} type="button" className={s.row} onClick={() => onPick(route, x.stop)} data-testid={`other-${route}-${x.stop}`}>
              <span className={s.name}>{x.name}</span>
              <span className={s.eta}>{i ? arrivalText(i, now, fetchedAt) : "정보 없음"}</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
