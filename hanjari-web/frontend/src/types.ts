export const LEVELS = [
  "여유 있음",
  "빠듯함",
  "어려울 수 있음",
  "판단하기 일러요",
  "확률 보류",
] as const;
export type Level = (typeof LEVELS)[number];

export type RouteCode = "sb02" | "jr03";

export interface PredictItem {
  route: RouteCode;
  stop: string;          // 정류장 순번 — 백엔드가 문자열로 줌 ("30","31","32" / "19","20","23")
  stop_name: string;
  plate: string;
  stops_away: number;    // 몇 정류장 전
  eta_sec: number;       // 이번 버스 도착까지 초
  eta2_sec?: number | null;  // 다음 버스 도착까지 초. 없으면 null
  r_now: number | null;  // API 인원(실측 아님). 결측은 null
  load_pred: number | null; // 확률 보류이면 예상 인원·확률 모두 null
  load_10: number | null;
  load_90: number | null;
  p_board: number | null;
  level: Level;
  reason: string;
  updated: string;       // "HH:MM:SS" KST
  updated_at?: string;   // 날짜·시간대 포함 수집 시각
  source_updated?: string | null; // API 제공 시각(인원 자체의 갱신 시각은 아님)
  vehicle_id?: string;
  data_status?: string;
  prediction_status?: string;
  arrival_stale?: boolean;
  arrival_at?: string;   // 제공 시각 + ETA, 날짜·시간대 포함
  arrival_status?: "upcoming" | "checking" | "passed";
  p_by_n?: number[] | null;  // 앞 인원 0~40명 각각의 탑승 확률. 있으면 인원을 바꿔도 서버를 다시 부르지 않는다
  n_ok?: number | null;      // '여유 있음'이 유지되는 앞 인원 상한. 여유 구간이 없으면 null
  n_hard?: number | null;    // 탈 수 있는(빠듯함까지) 앞 인원 상한. 없으면 null
}

/** GET /api/predict 응답. results 가 빈 배열이면 운행 시간 아님(새벽). */
export interface PredictResponse {
  n_ahead: number;
  results: PredictItem[];
  service?: { mode: string; data_status: string; release: string; routes: Partial<Record<RouteCode, {
    status: "fresh" | "stale" | "missing" | "outside_service";
    collected_at: string | null; age_sec: number | null;
  }>> };
}

export type ApiError =
  | { kind: "bad_input"; message: string }     // 400/422 { detail }
  | { kind: "server_down"; message: string }   // 502/503/연결 실패 (백엔드 재시작·꺼짐)
  | { kind: "timeout"; message: string }       // 느린 응답
  | { kind: "unknown"; message: string };

export type ApiResult =
  | { ok: true; data: PredictResponse }
  | { ok: false; error: ApiError };

export const N_MIN = 0;
export const N_MAX = 40;

export const ROUTES: Record<RouteCode, { name: string; stops: { stop: string; name: string; ars: string }[] }> = {
  sb02: {
    name: "성북02",
    stops: [
      { stop: "30", name: "한성대입구역5번출구", ars: "08596" },
      { stop: "31", name: "한성대입구역2번출구", ars: "08718" },
      { stop: "32", name: "녹십자약국", ars: "08744" },
    ],
  },
  jr03: {
    name: "종로03",
    stops: [
      { stop: "19", name: "동대문역.흥인지문", ars: "01023" },
      { stop: "20", name: "동묘앞역", ars: "01240" },
      { stop: "23", name: "창신역4번출구", ars: "01239" },
    ],
  },
};
