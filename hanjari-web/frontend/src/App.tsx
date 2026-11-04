import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { fetchPredict } from "./api/predict";
import { N_MAX, N_MIN, ROUTES } from "./types";
import type { ApiResult, RouteCode } from "./types";
import { isStale, parseN, verdict } from "./utils/format";
import Header from "./components/Header";
import ArrivalCard from "./components/ArrivalCard";
import AheadInput from "./components/AheadInput";
import ResultCard from "./components/ResultCard";
import LoadCompare from "./components/LoadCompare";
import Tabs from "./components/Tabs";
import Pager from "./components/Pager";
import Timeline from "./components/Timeline";
import OtherStops from "./components/OtherStops";
import StopSheet from "./components/StopSheet";
import Notice from "./components/Notice";
import { HeroError, HeroSkeleton, TimelinePlaceholder } from "./components/Offline";
import { TONE_CLASS } from "./components/LevelBadge";
import lv from "./components/levels.module.css";
import s from "./App.module.css";

interface Sel { route: RouteCode; stop: string }

const KEY = "hanjari.sel";
const FIRST: Sel = { route: "sb02", stop: ROUTES.sb02.stops[0].stop };
const AUTO_REFRESH_MS = 30_000;
const NEAR_REFRESH_MS = 5_000;
const NEAR_ETA_SEC = 120;
const NEAR_STOPS = 2;
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
  const [view, setView] = useState(0);  // 0: 지금 탈 수 있을까? / 1: 앞·뒤 정류장
  const [offline, setOffline] = useState(false);  // 이미 받은 정보가 있는데 새로고침만 실패 — 화면은 그대로 두고 상태 줄로만 알림
  const reqId = useRef(0);
  const hasData = useRef(false);
  const pending = useRef(0);

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
    // 자동 새로고침은 앞 요청이 끝난 뒤에만 — 응답이 간격보다 느릴 때 앞 응답이 계속 버려져 화면이 멈추지 않게
    if (silent && pending.current > 0) return;
    pending.current++;
    const id = ++reqId.current;
    if (!silent) setLoading(true);
    const r = await fetchPredict(nn);
    pending.current--;
    if (id !== reqId.current) return;  // 그사이 더 최근 요청이 나갔으면 버림
    setLoading(false);
    // 한 번 받은 뒤의 일시적 서버 오류는 화면을 갈아엎지 않고 마지막 정보를 유지 (카드가 사라졌다 나타나며 출렁이던 원인)
    if (!r.ok && r.error.kind !== "bad_input" && hasData.current) { setOffline(true); return; }
    setOffline(false);
    hasData.current = r.ok;
    setRes(r);
    setFetchedAt(Date.now());
  }, []);

  // 인원이 바뀌면 잠깐 기다렸다 조회 — +/− 를 연달아 누를 때 요청이 몰리지 않게
  useEffect(() => {
    const t = setTimeout(() => load(queryN), 250);
    return () => clearTimeout(t);
  }, [queryN, load]);

  const items = res?.ok ? res.data.results : [];
  const mine = items.find((i) => i.route === sel.route && i.stop === sel.stop) ?? null;
  const stale = mine !== null && isStale(mine);
  const near = mine !== null && !stale && (mine.stops_away <= NEAR_STOPS || mine.eta_sec <= NEAR_ETA_SEC
    || (mine.arrival_status !== undefined && mine.arrival_status !== "upcoming"));

  // 자동 새로고침: 평소 30초, 버스가 가까우면 5초(우리 서버의 수집 기록만 읽고 버스 API 는 부르지 않음). 화면이 안 보이면 쉬고, 돌아오면 바로 조회.
  // 서버 오류일 땐 간격만 늘려 계속 시도 — 일시적 오류가 지나가면 '다시 시도'를 안 눌러도 돌아오게
  const failing = offline || (res !== null && !res.ok && res.error.kind !== "bad_input");
  const refreshMs = failing ? ERROR_RETRY_MS : near ? NEAR_REFRESH_MS : AUTO_REFRESH_MS;
  useEffect(() => {
    const visible = () => document.visibilityState === "visible";
    const t = setInterval(() => { if (visible()) load(queryN, true); }, refreshMs);
    const onVis = () => { if (visible()) load(queryN, true); };
    document.addEventListener("visibilitychange", onVis);
    return () => { clearInterval(t); document.removeEventListener("visibilitychange", onVis); };
  }, [refreshMs, queryN, load]);

  const retry = () => load(queryN);

  const pick = (route: RouteCode, stop: string) => {
    const v = { route, stop };
    setSel(v);
    saveSel(v);
    setSheetOpen(false);
    setView(0);
  };

  const status =
    loading ? { text: "새로 불러오는 중…", tone: "normal" as const }
    : offline ? { text: "연결이 불안정해요 · 마지막으로 받은 정보예요", tone: "warn" as const }
    : res && !res.ok ? { text: "연결 실패", tone: "bad" as const }
    : res && items.length === 0 ? { text: "운행 시간 아님", tone: "normal" as const }
    : mine ? { text: `버스 정보 ${mine.updated} 기준`, tone: stale ? "warn" as const : "normal" as const }
    : { text: "", tone: "normal" as const };

  const input = <AheadInput raw={raw} n={n} error={inputError} onChange={onInput} />;

  let body: ReactNode;
  if (!res) {
    body = (
      <>
        <Tabs index={0} onChange={() => {}} disabled />
        <HeroSkeleton />
        <OtherStops route={sel.route} stop={sel.stop} onPick={pick} />
      </>
    );
  } else if (!res.ok) {
    body = res.error.kind === "bad_input"
      ? <><section className={s.card}>{input}</section><Notice kind="bad_input" detail={res.error.message} /></>
      : (
        <>
          <Tabs index={view} onChange={setView} />
          <Pager index={view} onChange={setView}>
            <>
              <HeroError kind={res.error.kind} detail={res.error.kind === "unknown" ? res.error.message : undefined}
                onRetry={retry} retrying={loading} input={input} />
              <OtherStops route={sel.route} stop={sel.stop} onPick={pick} />
            </>
            <TimelinePlaceholder route={sel.route} stop={sel.stop} onPick={pick} />
          </Pager>
        </>
      );
  } else if (items.length === 0) {
    body = <Notice kind="night" />;
  } else if (!mine) {
    body = <Notice kind="no_stop" onRetry={retry} retrying={loading} />;
  } else {
    // 위→아래: [히어로 카드: 도착 시간·판정 → 게이지·결론 → 차내 인원 → 대기 인원] → 다른 정류장 / 두 번째 화면: 앞·뒤 정류장
    const vd = verdict(mine);
    const hold = n === null || stale;
    const tone = hold ? lv.hold : TONE_CLASS[vd.tone];
    body = (
      <>
        <Tabs index={view} onChange={setView} />
        <Pager index={view} onChange={setView}>
          <>
            <section className={`${s.hero} ${tone}`} data-level={mine.level} data-tone={hold ? "hold" : vd.tone} data-testid="hero" aria-busy={loading}>
              <ArrivalCard item={mine} stale={stale} fetchedAt={fetchedAt} invalid={n === null} />
              <ResultCard item={mine} invalid={n === null} />
              <LoadCompare item={mine} stale={stale} />
              {input}
              {loading && <div className={s.loadbar} aria-hidden="true" />}
            </section>
            <OtherStops route={mine.route} stop={mine.stop} items={items} onPick={pick} />
          </>
          <Timeline items={items.filter((i) => i.route === mine.route)} mine={mine} onPick={(i) => pick(i.route, i.stop)} />
        </Pager>
      </>
    );
  }

  // 탭이 있는 화면(정상·오류·첫 불러오기)은 페이지 높이에 고정, 나머지 안내는 일반 흐름
  const paged = !res || (res.ok ? mine !== null && items.length > 0 : res.error.kind !== "bad_input");

  return (
    <div className={s.app}>
      <Header route={sel.route} stop={sel.stop} status={status} refreshing={loading}
        onRefresh={retry} onOpenStops={() => setSheetOpen(true)} />
      <main className={`${s.main} ${paged ? s.fill : ""}`}>
        {body}
      </main>
      {sheetOpen && (
        <StopSheet route={sel.route} stop={sel.stop} onPick={pick} onClose={() => setSheetOpen(false)} />
      )}
    </div>
  );
}
