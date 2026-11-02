import { test, expect } from "@playwright/test";
import { arrivalAt } from "../src/utils/format";
import sample from "../src/mock/predict_n3.json" with { type: "json" };
import type { PredictItem } from "../src/types";

const item = sample.results[2] as PredictItem;
const timestamp = (clock: string) => Date.parse(`2026-09-30T${clock}+09:00`);

test("같은 스냅샷의 도착 예정 시각은 수신 시각과 무관하게 일정하다", () => {
  const expected = timestamp("13:13:13");
  expect(arrivalAt(item, timestamp("13:11:43"))).toBe(expected);
  expect(arrivalAt(item, timestamp("13:12:13"))).toBe(expected);
});

test("스냅샷 나이 180초까지 보정하고 181초부터 수신 시각으로 계산한다", () => {
  expect(arrivalAt(item, timestamp("13:14:33"))).toBe(timestamp("13:13:13"));
  const received = timestamp("13:14:34");
  expect(arrivalAt(item, received)).toBe(received + item.eta_sec * 1000);
});

test("미래 또는 잘못된 스냅샷 시각은 수신 시각으로 계산한다", () => {
  const received = timestamp("13:11:23");
  expect(arrivalAt(item, received)).toBe(received + item.eta_sec * 1000);
  expect(arrivalAt({ ...item, updated: "invalid" }, received)).toBe(received + item.eta_sec * 1000);
});

test("자정을 넘긴 KST 스냅샷도 정상 계산한다", () => {
  const received = timestamp("00:00:10");
  expect(arrivalAt({ ...item, updated: "23:59:50", eta_sec: 100 }, received)).toBe(received + 80_000);
});

test("원본 제공 시각으로 ETA를 계산하여 수집 지연을 더하지 않는다", () => {
  const i = { ...item, updated_at: "2026-11-02T17:40:39+09:00", source_updated: "2026-11-02 17:40:14.0", eta_sec: 96 };
  expect(arrivalAt(i, Date.parse("2026-11-02T17:40:40+09:00"))).toBe(Date.parse("2026-11-02T17:41:50+09:00"));
});
