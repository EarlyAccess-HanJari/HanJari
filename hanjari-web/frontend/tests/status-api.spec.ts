import { test, expect } from "@playwright/test";
import fixture from "../src/mock/predict_n3.json" with { type: "json" };

// 실제 fetch·응답 검증을 거치는 안내 검사. VITE_MOCK=0 npx playwright test tests/status-api 로 실행한다
test.use({ serviceWorkers: "block" });
test.skip(process.env.VITE_MOCK !== "0", "VITE_MOCK=0으로 HTTP 경로 검사");

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.clear());
});

const service = (status: string) => ({
  mode: "latest", release: "test", data_status: status === "fresh" ? "ok" : "degraded",
  routes: { sb02: { status, collected_at: null, age_sec: null } },
});

test("수집이 늦어지면 시계 아이콘을 쓰고 끊김으로 보이지 않는다", async ({ page }) => {
  await page.route("**/api/predict?*", (r) => r.fulfill({ json: { n_ahead: 3, results: [], service: service("stale") } }));
  await page.goto("/");
  await page.getByTestId("stop-sb02-32").click();
  const notice = page.getByTestId("notice-data_delayed");
  await expect(notice).toContainText("버스 정보 갱신이 늦어지고 있어요");
  await expect(notice.locator("[data-icon]")).toHaveAttribute("data-icon", "clock");
  await expect(page.getByText("버스 정보 갱신 지연")).toBeVisible();
});

test("이 정류장 정보가 없으면 상태 줄과 본문이 같은 말을 하고 끊김으로 보이지 않는다", async ({ page }) => {
  const results = fixture.results.filter((i) => !(i.route === "sb02" && i.stop === "32"));
  await page.route("**/api/predict?*", (r) => r.fulfill({ json: { n_ahead: 3, results, service: service("fresh") } }));
  await page.goto("/");
  await page.getByTestId("stop-sb02-32").click();
  const notice = page.getByTestId("notice-no_stop");
  await expect(notice).toContainText("이 정류장 버스 정보가 없어요");
  await expect(notice.locator("[data-icon]")).toHaveAttribute("data-icon", "info");
  await expect(page.getByText("도착 정보 없음")).toBeVisible();
  await expect(page.locator("body")).not.toContainText("확인 중");
});

test("결과가 비어 있어도 수집이 정상이면 운행 시간이 아니라고 단정하지 않는다", async ({ page }) => {
  await page.route("**/api/predict?*", (r) => r.fulfill({ json: { n_ahead: 3, results: [], service: service("fresh") } }));
  await page.goto("/");
  await page.getByTestId("stop-sb02-32").click();
  await expect(page.getByTestId("notice-no_stop")).toBeVisible();
  await expect(page.getByTestId("notice-night")).toHaveCount(0);
  await expect(page.getByText("도착 정보 없음")).toBeVisible();
});

test("서버가 운행 시간 밖이라고 알려 주면 운행 시간 안내를 보여 준다", async ({ page }) => {
  await page.route("**/api/predict?*", (r) => r.fulfill({ json: { n_ahead: 3, results: [], service: service("outside_service") } }));
  await page.goto("/");
  await page.getByTestId("stop-sb02-32").click();
  const notice = page.getByTestId("notice-night");
  await expect(notice).toBeVisible();
  await expect(notice).not.toContainText("새벽");
  await expect(page.getByText("운행 시간 아님")).toBeVisible();
});

test("알 수 없는 오류에 상태 코드를 보여 주지 않고 입력칸은 그대로 둔다", async ({ page }) => {
  await page.route("**/api/predict?*", (r) => r.fulfill({ status: 500, body: "Internal Server Error" }));
  await page.goto("/");
  await page.getByTestId("stop-sb02-32").click();
  const notice = page.getByTestId("notice-unknown");
  await expect(notice).toContainText("버스 정보를 확인할 수 없어요");
  await expect(notice.locator("[data-icon]")).toHaveAttribute("data-icon", "info");
  await expect(page.locator("body")).not.toContainText("500");
  await expect(page.locator("body")).not.toContainText("서버 오류");
  await expect(page.getByTestId("n-input")).toBeVisible();
  await expect(page.getByText("버스 정보 확인 실패")).toBeVisible();
});

test("실제 응답에서도 인원을 바꾸면 응답 전까지 이전 확률을 보이지 않는다", async ({ page }) => {
  const reply: Record<string, () => void> = {};
  await page.route("**/api/predict?*", async (r) => {
    const n = Number(new URL(r.request().url()).searchParams.get("n"));
    if (n !== 3) await new Promise<void>((done) => { reply[n] = done; });
    await r.fulfill({ json: { ...fixture, n_ahead: n } });
  });
  await page.goto("/");
  await page.getByTestId("stop-sb02-32").click();
  await expect(page.getByTestId("verdict")).toContainText(/\d+%/);
  await page.getByTestId("n-input").fill("9");
  await expect(page.getByTestId("verdict")).toHaveText("계산 중");
  await expect(page.getByTestId("result")).toContainText("9명 기준으로 다시 계산");
  await expect(page.locator("[data-testid^=other-]").first()).not.toContainText(/\d+%/);
  await expect.poll(() => typeof reply[9]).toBe("function");
  reply[9]();
  await expect(page.getByTestId("verdict")).toContainText(/\d+%/);
});

test("실제 응답에서 인원을 바꾼 요청이 실패하면 이전 확률이 남지 않는다", async ({ page }) => {
  await page.route("**/api/predict?*", (r) => {
    const n = Number(new URL(r.request().url()).searchParams.get("n"));
    return n === 3 ? r.fulfill({ json: fixture }) : r.fulfill({ status: 503, body: "" });
  });
  await page.goto("/");
  await page.getByTestId("stop-sb02-32").click();
  await expect(page.getByTestId("verdict")).toContainText(/\d+%/);
  await page.getByTestId("n-input").fill("9");
  await expect(page.getByTestId("result")).toContainText("9명 기준 확률을 못 받았어요");
  await expect(page.getByTestId("verdict")).toHaveText("확률 보류");
  await expect(page.locator("[data-testid^=other-]").first()).not.toContainText(/\d+%/);
  await expect(page.getByTestId("arrival")).toContainText("이번 버스");
  await expect(page.getByText("연결이 불안정해요")).toBeVisible();
});
