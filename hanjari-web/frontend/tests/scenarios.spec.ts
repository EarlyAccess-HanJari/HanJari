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

test("stale: '확률 보류' → 오래됨 안내 + 확률·도착 시간 숨김", async ({ page }) => {
  await run(page, "stale");
  await expect(page.getByTestId("notice-stale")).toBeVisible();
  const result = page.getByTestId("result");
  await expect(result).toHaveAttribute("data-level", "확률 보류");
  await expect(result).not.toContainText("탈 확률");
  await expect(result).not.toContainText("예상 인원");
  await expect(result).toContainText("95분 전");                 // 보류 이유 노출
  // 오래된 정보면 도착 시간·정류장 수 대신 안내만 (몇 시간 전 버스를 카운트다운하지 않게)
  await expect(page.getByTestId("arrival")).toContainText("버스 위치를 확인할 수 없어요");
  await expect(page.getByTestId("arrival")).not.toContainText("바로 앞 정류장");
});

test("wide: '판단하기 일러요' → 확률 대신 예상 범위 안내", async ({ page }) => {
  await run(page, "wide");
  const result = page.getByTestId("result");
  await expect(result).toHaveAttribute("data-level", "판단하기 일러요");
  await expect(result).not.toContainText("탈 확률");
  await expect(result).toContainText("16~46명");
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
  await expect(page.getByTestId("result")).toBeVisible();
});

test("slow: 느린 응답 → 타임아웃 안내", async ({ page }) => {
  test.setTimeout(30_000);
  await run(page, "slow");
  await expect(page.getByTestId("notice-timeout")).toBeVisible({ timeout: 15_000 });
});

test("단계별 색이 서로 다르다", async ({ page }) => {
  const colors = new Map<string, string>();
  for (const sc of ["", "stale", "wide"]) {
    await run(page, sc);
    await page.getByTestId("result").waitFor();
    for (const el of await page.locator("[data-level]").all()) {
      const level = (await el.getAttribute("data-level"))!;
      const bg = await el.evaluate((e) => getComputedStyle(e).backgroundColor);
      if (colors.has(level)) expect(colors.get(level)).toBe(bg);
      colors.set(level, bg);
    }
  }
  expect(new Set(colors.values()).size).toBe(colors.size);     // 단계 수 == 색 수
  expect(colors.size).toBeGreaterThanOrEqual(3);
});
