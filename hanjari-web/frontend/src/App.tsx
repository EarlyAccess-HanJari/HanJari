import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { fetchPredict } from "./api/predict";
import { N_MAX, N_MIN, ROUTES } from "./types";
import type { ApiResult, RouteCode } from "./types";
import { arrivalAt, arrivalState, isOlderSnapshot, parseN } from "./utils/format";
import Header from "./components/Header";
import ArrivalCard from "./components/ArrivalCard";
import AheadInput from "./components/AheadInput";
import ResultCard from "./components/ResultCard";
import LoadCompare from "./components/LoadCompare";
import OtherStops from "./components/OtherStops";
import StopSheet from "./components/StopSheet";
import Notice from "./components/Notice";
import s from "./App.module.css";

interface Sel { route: RouteCode; stop: string }

const KEY = "hanjari.sel";
const FIRST: Sel = { route: "sb02", stop: ROUTES.sb02.stops[0].stop };
const AUTO_REFRESH_MS = 30_000;
const NEAR_REFRESH_MS = 5_000;
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
  const [online, setOnline] = useState(() => navigator.onLine);
  const reqId = useRef(0);
  const activeReq = useRef<number | null>(null);
  const activeN = useRef<number | null>(null);
  const lastGood = useRef<ApiResult | null>(null);
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

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
    if (activeReq.current !== null && (silent || activeN.current === nn)) return;
    const id = ++reqId.current;
    activeReq.current = id;
    activeN.current = nn;
    if (!silent) setLoading(true);
    const r = await fetchPredict(nn);
    if (id !== reqId.current) return;  // 그사이 더 최근 요청이 나갔으면 버림
    activeReq.current = null;
    const previous = lastGood.current;
    const next: ApiResult = r.ok && previous?.ok
      ? { ...r, data: { ...r.data, results: r.data.results.map(item => {
        const before = previous.data.results.find(i => i.route === item.route && i.stop === item.stop);
        if (!before || !isOlderSnapshot(item, before)) return item;
        if (previous.data.n_ahead === nn) return before;
        // 입력 인원이 바뀌었다면 옛 인원으로 계산한 확률도 재사용하지 않는다.
        return { ...before, level: "확률 보류" as const, load_pred: null, load_10: null, load_90: null,
          p_board: null, prediction_status: "source_regressed", reason: "최신 버스 정보로 다시 계산하고 있어요" };
      }) } } : r;
    if (next.ok) lastGood.current = next;
    setRes(next);
    setFetchedAt(Date.now());
    setNow(Date.now());
    setLoading(false);
  }, []);

  // 인원이 바뀌면 잠깐 기다렸다 조회 — +/− 를 연달아 누를 때 요청이 몰리지 않게
  useEffect(() => {
    const t = setTimeout(() => load(queryN), 250);
    return () => clearTimeout(t);
  }, [queryN, load]);

  useEffect(() => {
    const connected = () => { setOnline(true); load(queryN, true); };
    const disconnected = () => setOnline(false);
    window.addEventListener("online", connected);
    window.addEventListener("offline", disconnected);
    return () => { window.removeEventListener("online", connected); window.removeEventListener("offline", disconnected); };
  }, [load, queryN]);

  const items = res?.ok ? res.data.results : [];
  const sourceStatus = res?.ok ? res.data.service?.routes[sel.route]?.status : undefined;
  const delayed = sourceStatus === "stale" || sourceStatus === "missing";
  const mine = items.find((i) => i.route === sel.route && i.stop === sel.stop) ?? null;
  const updated = mine?.source_updated?.match(/[ T](\d{2}:\d{2}:\d{2})/)?.[1] ?? mine?.updated;
  const state = mine ? arrivalState(mine, now, fetchedAt) : "upcoming";
  const near = mine ? state !== "upcoming" || mine.stops_away <= 2 || arrivalAt(mine, fetchedAt) - now <= 120_000 : items.length > 0;

  // 가까운 버스는 5초 간격으로 서버 기록 조회. 느린 요청 중에는 중복하지 않으며 서울시 API를 추가 호출하지 않는다.
  // 서버 오류일 땐 간격만 늘려 계속 시도 — 일시적 오류가 지나가면 '다시 시도'를 안 눌러도 돌아오게
  const failing = res !== null && !res.ok && res.error.kind !== "bad_input";
  const refreshMs = failing ? ERROR_RETRY_MS : near ? NEAR_REFRESH_MS : AUTO_REFRESH_MS;
  useEffect(() => {
    const visible = () => document.visibilityState === "visible" && navigator.onLine;
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
    load(queryN, true);
  };

  const status =
    !online ? { text: "인터넷 연결 끊김", tone: "bad" as const }
    : loading ? { text: "새로 불러오는 중…", tone: "normal" as const }
    : res && !res.ok ? { text: "연결 실패", tone: "bad" as const }
    : delayed ? { text: "버스 정보 갱신 지연", tone: "warn" as const }
    : res && items.length === 0 ? { text: sourceStatus === "fresh" ? "도착 정보 확인 중" : "운행 시간 아님", tone: "normal" as const }
    : mine ? { text: `버스 정보 ${updated} 기준`, tone: state !== "upcoming" ? "warn" as const : "normal" as const }
    : { text: "", tone: "normal" as const };

  const input = <AheadInput raw={raw} n={n} error={inputError} onChange={onInput} />;

  let body: ReactNode;
  if (!online) {
    body = <Notice kind="offline" />;
  } else if (!res) {
    body = <><section className={s.card}>{input}</section><p className={s.loading}>버스 정보를 불러오는 중…</p></>;
  } else if (!res.ok) {
    body = res.error.kind === "bad_input"
      ? <><section className={s.card}>{input}</section><Notice kind="bad_input" detail={res.error.message} /></>
      : <Notice kind={res.error.kind} detail={res.error.kind === "unknown" ? res.error.message : undefined}
          onRetry={retry} retrying={loading} />;
  } else if (!mine && delayed) {
    body = <Notice kind="data_delayed" onRetry={retry} retrying={loading} />;
  } else if (items.length === 0 && sourceStatus !== "fresh") {
    body = <Notice kind="night" />;
  } else if (!mine) {
    body = <Notice kind="no_stop" onRetry={retry} retrying={loading} />;
  } else {
    // 한 카드 안에서 위→아래: 남은 시간 → 탑승 가능성 → 차내 인원 → 대기 인원 입력
    body = (
      <>
        <section className={s.card}>
          <ArrivalCard item={mine} state={state} fetchedAt={fetchedAt} now={now} />
          <ResultCard item={mine} invalid={n === null} busy={loading} arrivalState={state} />
          <LoadCompare item={mine} stale={state !== "upcoming"} />
          <div className={s.divider} />
          {input}
        </section>
        <OtherStops items={items.filter((i) => i.route === mine.route && i !== mine)}
          onPick={(i) => pick(i.route, i.stop)} now={now} fetchedAt={fetchedAt} />
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
      {sheetOpen && (
        <StopSheet route={sel.route} stop={sel.stop} onPick={pick} onClose={() => setSheetOpen(false)} />
      )}
    </div>
  );
}
