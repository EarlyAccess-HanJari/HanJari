import { test, expect } from "@playwright/test";
import type { Page } from "@playwright/test";
import fixture from "../src/mock/predict_n3.json" with { type: "json" };

// 색·안내 문구가 서버 판정(level)을 따르는지 실제 fetch·응답 검증을 거쳐 본다. VITE_MOCK=0 npx playwright test tests/verdict 로 실행한다
test.use({ serviceWorkers: "block" });
test.skip(process.env.VITE_MOCK !== "0", "VITE_MOCK=0으로 HTTP 경로 검사");

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.clear());
});

// 녹십자약국 응답만 바꿔서 연다
const open = async (page: Page, patch: Record<string, unknown>) => {
  const results = fixture.results.map((i) => (i.route === "sb02" && i.stop === "32" ? { ...i, ...patch } : i));
  await page.route("**/api/predict?*", (r) => r.fulfill({ json: { ...fixture, results } }));
  await page.goto("/");
  await page.getByTestId("stop-sb02-32").click();
};

const CASES = [
  { level: "여유 있음", p: 0.96, tone: "ok", guide: "줄을 서면 안정적으로 탑승할 수 있어요." },
  { level: "빠듯함", p: 0.92, tone: "warn", guide: "대체로 타지만, 사람이 몰리면 못 탈 수도 있어요." },
  { level: "빠듯함", p: 0.7, tone: "warn", guide: "앞줄에 서면 탈 수 있지만, 못 탈 수도 있어요." },
  { level: "빠듯함", p: 0.35, tone: "warn", guide: "탑승이 불확실해요." },
  { level: "어려울 수 있음", p: 0.3, tone: "bad", guide: "이번 버스는 타기 힘들어요." },
];

for (const c of CASES) {
  test(`${c.level} ${Math.round(c.p * 100)}%는 ${c.tone} 색과 맞는 문구를 쓴다`, async ({ page }) => {
    await open(page, { level: c.level, p_board: c.p });
    await expect(page.getByTestId("hero")).toHaveAttribute("data-tone", c.tone);
    await expect(page.getByTestId("verdict")).toContainText(`탑승 확률 · ${Math.round(c.p * 100)}%`);
    await expect(page.getByTestId("result")).toContainText(c.guide);
  });
}

// serve.py hold_result(result, "calibration_hold", why)와 같은 모양
const HELD = { level: "확률 보류", prediction_status: "calibration_hold", data_status: "ok", p_board: null, load_pred: null, load_10: null, load_90: null };

test("일요일·공휴일은 '예측 없음'과 쉬어요 문장을 보이고 서버 이유는 숨긴다", async ({ page }) => {
  await open(page, { ...HELD, reason: "일요일·공휴일(수업 없는 날은 아직 검증 전)" });
  await expect(page.getByTestId("hero")).toHaveAttribute("data-tone", "hold");
  await expect(page.getByTestId("verdict")).toHaveText("예측 없음");
  const result = page.getByTestId("result");
  await expect(result).toHaveText("오늘은 탑승 예측을 쉬어요. 위의 도착 정보만 참고해 주세요.");
  await expect(page.getByTestId("arrival")).toContainText("이번 버스");
  await expect(page.locator("body")).not.toContainText("확률 보류");
});

test("다른 보류는 '예측 없음'과 서버 이유를 그대로 보인다", async ({ page }) => {
  await open(page, { ...HELD, reason: "이 시간대·거리는 검증 데이터 부족" });
  await expect(page.getByTestId("verdict")).toHaveText("예측 없음");
  const result = page.getByTestId("result");
  await expect(result).toContainText("이번 버스는 탑승 예측이 없어요. 위의 도착 정보만 참고해 주세요.");
  await expect(result).toContainText("이 시간대·거리는 검증 데이터 부족");
  await expect(page.locator("body")).not.toContainText("확률 보류");
});

test("두 번째 화면의 정류장 줄도 같은 뱃지를 쓴다", async ({ page }) => {
  await open(page, { ...HELD, reason: "일요일·공휴일(수업 없는 날은 아직 검증 전)" });
  await page.getByTestId("tab-1").click();
  await expect(page.getByTestId("card-sb02-32")).toContainText("예측 없음");
  await expect(page.getByTestId("card-sb02-32")).not.toContainText("확률 보류");
});
