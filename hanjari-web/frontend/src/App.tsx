import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { fetchPredict, USE_MOCK } from "./api/predict";
import type { Scenario } from "./api/predict";
import { N_MAX, N_MIN, ROUTES } from "./types";
import type { ApiResult, RouteCode } from "./types";
import { isStale, parseN } from "./utils/format";
import Header from "./components/Header";
import ArrivalCard from "./components/ArrivalCard";
import AheadInput from "./components/AheadInput";
import ResultCard from "./components/ResultCard";
import OtherStops from "./components/OtherStops";
import StopSheet from "./components/StopSheet";
import Notice from "./components/Notice";
import HeroSkeleton from "./components/HeroSkeleton";
import DevSwitcher from "./components/DevSwitcher";
import s from "./App.module.css";

interface Sel { route: RouteCode; stop: string }

const KEY = "hanjari.sel";
const FIRST: Sel = { route: "sb02", stop: ROUTES.sb02.stops[0].stop };
const AUTO_REFRESH_MS = 30_000;
const ERROR_RETRY_MS = 60_000;

function loadSel(): Sel | null {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? "null") as Sel | null;
    if (v && ROUTES[v.route]?.stops.some((x) => x.stop === v.stop)) return v;
  } catch { /* ignore */ }
  return null;
}

function saveSel(v: Sel) {
  try { localStorage.setItem(KEY, JSON.stringify(v)); } catch { /* 사생활 보호 모드 등 — 기억만 못 함 */ }
}

export default function App() {
  const [remembered] = useState(loadSel);
  const [sel, setSel] = useState<Sel>(remembered ?? FIRST);
  const [sheetOpen, setSheetOpen] = useState(!remembered);  // 첫 방문엔 정류장부터 고르게
  const [raw, setRaw] = useState("3");
  // 조회에 쓰는 인원 = 마지막으로 올바르게 입력한 값. 입력이 잠깐 틀려도 도착 정보는 계속 보이게
  const [queryN, setQueryN] = useState(3);
  const [res, setRes] = useState<ApiResult | null>(null);
  const [fetchedAt, setFetchedAt] = useState(0);  // 도착 시간 카운트다운 기준
  const [loading, setLoading] = useState(false);
  const reqId = useRef(0);

  const parsed = parseN(raw, N_MIN, N_MAX);
  const n = "n" in parsed ? parsed.n : null;
  const inputError = "error" in parsed ? parsed.error : null;

  const onInput = (v: string) => {
    setRaw(v);
    const p = parseN(v, N_MIN, N_MAX);
    if ("n" in p) setQueryN(p.n);
  };

  // silent: 자동 새로고침 — 화면을 흐리게 하거나 '불러오는 중'을 띄우지 않음
  const load = useCallback(async (nn: number, silent = false) => {
    const id = ++reqId.current;
    if (!silent) setLoading(true);
    const r = await fetchPredict(nn);
    if (id !== reqId.current) return;  // 그사이 더 최근 요청이 나갔으면 버림
    setRes(r);
    setFetchedAt(Date.now());
    setLoading(false);
  }, []);

  // 인원이 바뀌면 잠깐 기다렸다 조회 — +/− 를 연달아 누를 때 요청이 몰리지 않게
  useEffect(() => {
    const t = setTimeout(() => load(queryN), 250);
    return () => clearTimeout(t);
  }, [queryN, load]);

  // 자동 새로고침: 수집기가 약 27초마다 새 스냅샷을 쓰므로 30초. 화면이 안 보이면 쉬고, 돌아오면 바로 조회.
  // 서버 오류일 땐 간격만 늘려 계속 시도 — 일시적 오류가 지나가면 '다시 시도'를 안 눌러도 돌아오게
  const failing = res !== null && !res.ok && res.error.kind !== "bad_input";
  useEffect(() => {
    const visible = () => document.visibilityState === "visible";
    const t = setInterval(() => { if (visible()) load(queryN, true); }, failing ? ERROR_RETRY_MS : AUTO_REFRESH_MS);
    const onVis = () => { if (visible()) load(queryN, true); };
    document.addEventListener("visibilitychange", onVis);
    return () => { clearInterval(t); document.removeEventListener("visibilitychange", onVis); };
  }, [failing, queryN, load]);

  const retry = () => load(queryN);

  // 개발용 상태 전환 — 목업은 요청마다 주소의 ?scenario 를 읽음
  const devSwitch = (sc: Scenario | null) => {
    const u = new URL(window.location.href);
    if (sc) u.searchParams.set("scenario", sc); else u.searchParams.delete("scenario");
    history.replaceState(null, "", u);
    if (sc === "loading") setRes(null);
    load(queryN);
  };

  const pick = (route: RouteCode, stop: string) => {
    const v = { route, stop };
    setSel(v);
    saveSel(v);
    setSheetOpen(false);
  };

  const items = res?.ok ? res.data.results : [];
  const mine = items.find((i) => i.route === sel.route && i.stop === sel.stop) ?? null;
  const stale = mine !== null && isStale(mine);

  const status =
    loading ? { text: "새로 불러오는 중…", tone: "normal" as const }
    : res && !res.ok ? { text: "연결 실패", tone: "bad" as const }
    : res && items.length === 0 ? { text: "운행 시간 아님", tone: "normal" as const }
    : mine ? { text: `버스 정보 ${mine.updated} 기준`, tone: stale ? "warn" as const : "normal" as const }
    : { text: "", tone: "normal" as const };

  const input = <AheadInput raw={raw} n={n} error={inputError} onChange={onInput} />;

  let body: ReactNode;
  if (!res) {
    // 첫 조회 전에도 결과가 올 자리를 같은 크기로 잡아 둠
    body = <><div className={s.hero} data-testid="hero"><HeroSkeleton /></div>{input}<div className={s.dock}><OtherStops items={[]} onPick={() => {}} /></div></>;
  } else if (!res.ok) {
    body = res.error.kind === "bad_input"
      ? <>{input}<Notice kind="bad_input" detail={res.error.message} /></>
      : <Notice kind={res.error.kind} detail={res.error.kind === "unknown" ? res.error.message : undefined}
          onRetry={retry} retrying={loading} />;
  } else if (items.length === 0) {
    body = <Notice kind="night" />;
  } else if (!mine) {
    body = <Notice kind="no_stop" onRetry={retry} retrying={loading} />;
  } else {
    body = (
      <>
        {/* 핵심 '지금 오는 버스에 탈 수 있을까?' — 도착 시간과 탑승 가능성을 한 카드에. 다른 정류장은 맨 아래 접어 둠 */}
        <div className={s.hero} data-testid="hero">
          <ArrivalCard item={mine} stale={stale} fetchedAt={fetchedAt} />
          <ResultCard item={mine} invalid={n === null} busy={loading} />
        </div>
        {input}
        <div className={s.dock}>
          <OtherStops items={items.filter((i) => i.route === mine.route && i !== mine)}
            onPick={(i) => pick(i.route, i.stop)} />
        </div>
      </>
    );
  }

  return (
    <div className={s.app}>
      <Header route={sel.route} stop={sel.stop} status={status} refreshing={loading}
        onRefresh={retry} onOpenStops={() => setSheetOpen(true)} />
      <main className={s.main}>
        {body}
      </main>
      {USE_MOCK && <DevSwitcher onSwitch={devSwitch} />}
      {sheetOpen && (
        <StopSheet route={sel.route} stop={sel.stop} onPick={pick} onClose={() => setSheetOpen(false)} />
      )}
    </div>
  );
}
