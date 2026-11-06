import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { fetchPredict } from "./api/predict";
import { N_MAX, N_MIN, ROUTES } from "./types";
import type { ApiError, ApiResult, RouteCode } from "./types";
import { arrivalAt, arrivalState, isOlderSnapshot, parseN, verdict } from "./utils/format";
import type { ProbState } from "./utils/format";
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
const ERROR_RETRY_MS = 60_000;
const SLOW_MS = 3_000;  // 평소 응답은 1초 안팎, 요청이 몰려도 2.6초(운영 기록). 이보다 길면 기다리는 중임을 알린다

// 첫 조회 실패 때 상태 줄. 본문 안내와 같은 말을 한다
const ERROR_STATUS: Record<ApiError["kind"], { text: string; tone: "warn" | "bad" }> = {
  server_down: { text: "연결 실패", tone: "bad" },
  timeout: { text: "응답 지연", tone: "warn" },
  unknown: { text: "버스 정보 확인 실패", tone: "bad" },
  bad_input: { text: "입력 확인 필요", tone: "warn" },
};

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
  const [loadingSince, setLoadingSince] = useState<number | null>(null);  // 화면에 알리는 요청을 보낸 시각
  const loading = loadingSince !== null;
  const [view, setView] = useState(0);  // 0: 지금 탈 수 있을까? / 1: 앞·뒤 정류장
  const [degraded, setDegraded] = useState(false);  // 이미 받은 정보가 있는데 새로고침만 실패 — 화면은 그대로 두고 상태 줄로만 알림
  const [failedN, setFailedN] = useState<number | null>(null);  // 마지막 요청이 실패한 인원
  const [online, setOnline] = useState(() => navigator.onLine);
  const reqId = useRef(0);
  const activeReq = useRef<number | null>(null);
  const activeN = useRef<number | null>(null);
  const lastGood = useRef<ApiResult | null>(null);
  const answered = useRef(false);
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
    if (!silent || !answered.current) setLoadingSince(Date.now());  // 첫 응답 전에는 자동 조회여도 화면이 기다리는 중이다
    const r = await fetchPredict(nn);
    if (id !== reqId.current) return;  // 그사이 더 최근 요청이 나갔으면 버림
    answered.current = true;
    activeReq.current = null;
    setLoadingSince(null);
    // 한 번 받은 뒤의 일시적 서버 오류는 화면을 갈아엎지 않고 마지막 정보를 유지 (카드가 사라졌다 나타나며 출렁이던 원인).
    // 시간이 지나면 arrivalState 가 오래된 정보로 바꾸므로 낡은 도착 시간이 남지 않는다.
    if (!r.ok && r.error.kind !== "bad_input" && lastGood.current) { setDegraded(true); setFailedN(nn); return; }
    setDegraded(false);
    setFailedN(null);
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

  const slow = loadingSince !== null && now - loadingSince >= SLOW_MS;
  const items = res?.ok ? res.data.results : [];
  // 응답의 n_ahead 가 입력과 다르면 화면의 확률은 이전 인원의 것이다. 응답 전·실패 때 그 확률을 보이지 않는다
  const resultN = res?.ok ? res.data.n_ahead : null;
  const prob: ProbState = n === null ? "invalid"
    : resultN === null || resultN === n ? "current"
    : !online || (failedN === n && !loading) ? "unavailable"
    : "calculating";
  const sourceStatus = res?.ok ? res.data.service?.routes[sel.route]?.status : undefined;
  const delayed = sourceStatus === "stale" || sourceStatus === "missing";
  const mine = items.find((i) => i.route === sel.route && i.stop === sel.stop) ?? null;
  const updated = mine?.source_updated?.match(/[ T](\d{2}:\d{2}:\d{2})/)?.[1] ?? mine?.updated;
  const state = mine ? arrivalState(mine, now, fetchedAt) : "upcoming";
  const near = mine ? state !== "upcoming" || mine.stops_away <= 2 || arrivalAt(mine, fetchedAt) - now <= 120_000 : items.length > 0;

  // 가까운 버스는 5초 간격으로 서버 기록 조회. 느린 요청 중에는 중복하지 않으며 서울시 API를 추가 호출하지 않는다.
  // 서버 오류일 땐 간격만 늘려 계속 시도 — 일시적 오류가 지나가면 '다시 시도'를 안 눌러도 돌아오게
  const failing = degraded || (res !== null && !res.ok && res.error.kind !== "bad_input");
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
    setView(0);
    load(queryN, true);
  };

  const status =
    !online ? { text: mine ? "인터넷 연결 끊김 · 마지막으로 받은 정보예요" : "인터넷 연결 끊김", tone: "bad" as const }
    : slow ? { text: "응답이 늦어지고 있어요…", tone: "warn" as const }
    : loading ? { text: "새로 불러오는 중…", tone: "normal" as const }
    : degraded ? { text: "연결이 불안정해요 · 마지막으로 받은 정보예요", tone: "warn" as const }
    : res && !res.ok ? ERROR_STATUS[res.error.kind]
    : delayed ? { text: "버스 정보 갱신 지연", tone: "warn" as const }
    : res && !mine ? { text: items.length === 0 && sourceStatus !== "fresh" ? "운행 시간 아님" : "도착 정보 없음", tone: "normal" as const }
    : mine ? { text: `버스 정보 ${updated} 기준`, tone: state !== "upcoming" ? "warn" as const : "normal" as const }
    : { text: "", tone: "normal" as const };

  const input = <AheadInput raw={raw} n={n} error={inputError} onChange={onInput} />;

  let body: ReactNode;
  if (!online && !mine) {  // 받아 둔 정보가 있으면 지우지 않는다. 낡으면 arrivalState 가 오래된 정보로 바꾼다
    body = <Notice kind="offline" />;
  } else if (!res) {
    body = (
      <>
        <Tabs index={0} onChange={() => {}} disabled />
        <HeroSkeleton slow={slow} />
        <OtherStops route={sel.route} stop={sel.stop} onPick={pick} now={now} fetchedAt={fetchedAt} />
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
              <HeroError kind={res.error.kind} onRetry={retry} retrying={loading} input={input} />
              <OtherStops route={sel.route} stop={sel.stop} onPick={pick} now={now} fetchedAt={fetchedAt} />
            </>
            <TimelinePlaceholder route={sel.route} stop={sel.stop} onPick={pick} />
          </Pager>
        </>
      );
  } else if (!mine && delayed) {
    body = <Notice kind="data_delayed" onRetry={retry} retrying={loading} />;
  } else if (items.length === 0 && sourceStatus !== "fresh") {
    body = <Notice kind="night" />;
  } else if (!mine) {
    body = <Notice kind="no_stop" onRetry={retry} retrying={loading} />;
  } else {
    // 위→아래: [히어로 카드: 도착 시간·판정 → 게이지·결론 → 차내 인원 → 대기 인원] → 다른 정류장 / 두 번째 화면: 앞·뒤 정류장
    const vd = verdict(mine);
    const hold = prob !== "current" || state !== "upcoming";
    const tone = hold ? lv.hold : TONE_CLASS[vd.tone];
    body = (
      <>
        <Tabs index={view} onChange={setView} />
        <Pager index={view} onChange={setView}>
          <>
            <section className={`${s.hero} ${tone}`} data-level={prob === "current" ? mine.level : "확률 보류"} data-tone={hold ? "hold" : vd.tone} data-testid="hero" aria-busy={loading}>
              <ArrivalCard item={mine} state={state} fetchedAt={fetchedAt} now={now} prob={prob} />
              <ResultCard item={mine} prob={prob} n={n} slow={slow} online={online} arrivalState={state} onRetry={retry} />
              <LoadCompare item={mine} stale={state !== "upcoming"} />
              {input}
              {loading && <div className={s.loadbar} aria-hidden="true" />}
            </section>
            <OtherStops route={mine.route} stop={mine.stop} items={items} onPick={pick} now={now} fetchedAt={fetchedAt} />
          </>
          <Timeline items={items.filter((i) => i.route === mine.route)} mine={mine} onPick={(i) => pick(i.route, i.stop)} now={now} fetchedAt={fetchedAt} prob={prob} />
        </Pager>
      </>
    );
  }

  // 탭이 있는 화면(정상·오류·첫 불러오기)은 페이지 높이에 고정, 나머지 안내는 일반 흐름
  const paged = (online || mine !== null) && (!res || (res.ok ? mine !== null && items.length > 0 : res.error.kind !== "bad_input"));

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
