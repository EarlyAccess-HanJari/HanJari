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
  eta_sec: number;       // 도착까지 초
  r_now: number;         // 지금 재차
  load_pred: number;     // 도착 때 예상 재차
  load_10: number;
  load_90: number;
  p_board: number;       // 0~1
  level: Level;
  reason: string;
  updated: string;       // "HH:MM:SS" KST
}

/** GET /api/predict 응답. results 가 빈 배열이면 운행 시간 아님(새벽). */
export interface PredictResponse {
  n_ahead: number;
  results: PredictItem[];
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