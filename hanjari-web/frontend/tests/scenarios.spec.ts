import { test, expect } from "@playwright/test";
import type { Page } from "@playwright/test";

// 시나리오를 연달아 돌릴 때 '마지막 정류장 기억' 때문에 시트를 건너뛰지 않도록
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.clear());
});

const run = async (page: Page, scenario: string) => {
  await page.goto(`/?scenario=${scenario}`);
  await page.getByTestId("stop-sb02-32").click();               // 녹십자약국, 앞 3명(기본값)
};

test("stale: 오래된 인원과 도착 시간을 숨긴다", async ({ page }) => {
  await run(page, "stale");
  await expect(page.getByTestId("notice-stale")).toBeVisible();
  await expect(page.getByTestId("loads")).not.toContainText(/\d/);
  await expect(page.getByTestId("arrival")).toContainText("버스 위치를 확인할 수 없어요");
});

test("예측값이 와도 현재 인원만 표시하고 탑승 판단은 노출하지 않는다", async ({ page }) => {
  await run(page, "wide");
  await expect(page.getByTestId("loads")).toContainText("현재 차내 인원");
  await expect(page.getByTestId("loads")).not.toContainText("16~46명");
  await expect(page.locator("main")).not.toContainText(/탑승 가능성|여유 있음|빠듯함|확률 보류|\d+%/);
  await expect(page.getByTestId("n-input")).toHaveCount(0);
});

test("night: 결과 없음 → 운행 시간 아님", async ({ page }) => {
  await run(page, "night");
  await expect(page.getByTestId("notice-night")).toContainText("다니지 않아요");
});

test("error: 서버가 입력 오류를 돌려주면 detail 을 보여준다", async ({ page }) => {
  await run(page, "error");
  await expect(page.getByTestId("notice-bad_input")).toContainText("0~40 정수");
});

test("down: 백엔드 꺼짐(502) → 안내 + 다시 시도 버튼", async ({ page }) => {
  await run(page, "down");
  const n = page.getByTestId("notice-server_down");
  await expect(n).toContainText("서버에 연결할 수 없어요");
  await expect(n.getByRole("button", { name: "다시 시도" })).toBeVisible();
});

test("down 뒤 서버가 살아나면 버튼 없이 60초 안에 저절로 돌아온다", async ({ page }) => {
  await page.clock.install();
  await run(page, "down");
  await page.clock.runFor(1_000);
  await expect(page.getByTestId("notice-server_down")).toBeVisible();
  // 서버 복구 흉내: 목업은 요청마다 주소의 ?scenario 를 읽음
  await page.evaluate(() => history.replaceState(null, "", "/"));
  await page.clock.runFor(61_000);
  await expect(page.getByTestId("loads")).toBeVisible();
});

test("slow: 느린 응답 → 타임아웃 안내", async ({ page }) => {
  test.setTimeout(30_000);
  await run(page, "slow");
  await expect(page.getByTestId("notice-timeout")).toBeVisible({ timeout: 15_000 });
});
