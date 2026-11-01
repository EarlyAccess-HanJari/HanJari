import { test, expect } from "@playwright/test";
import type { Page } from "@playwright/test";

// 시선 흔들림 점검: 상태가 바뀌어도 도착·결과 카드 높이와 입력칸 위치가 같아야 한다
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.clear());
});

const open = async (page: Page, scenario = "") => {
  await page.goto(scenario ? `/?scenario=${scenario}` : "/");
  await page.getByTestId("stop-sb02-32").click();
};

const measure = async (page: Page, card = "result") => {
  await page.waitForTimeout(500);  // 목업 응답(300ms) 뒤
  const r = (await page.getByTestId(card).boundingBox())!;
  const a = card === "result" ? (await page.getByTestId("arrival").boundingBox())! : null;
  const i = (await page.getByTestId("n-input").boundingBox())!;
  const scrollY = await page.evaluate(() => window.scrollY);  // 버튼을 누르며 스크롤돼도 문서 기준 위치로 비교
  return { arrival: a ? Math.round(a.height) : null, result: Math.round(r.height), inputY: Math.round(i.y + scrollY) };
};

test("단계·보류·입력 오류가 바뀌어도 카드 높이와 입력칸 위치가 그대로", async ({ page }) => {
  await open(page);
  const base = await measure(page);                                         // 여유 있음 (앞 3명)

  await page.getByRole("button", { name: "20명" }).click();                  // 어려울 수 있음
  expect(await measure(page)).toEqual(base);

  await page.getByTestId("n-input").fill("abc");                            // 입력 오류 — 입력 중인 칸이 튀면 안 됨
  expect(await measure(page)).toEqual(base);

  for (const sc of ["wide", "tight", "ok", "hard"]) {
    await open(page, sc);
    expect(await measure(page), sc).toEqual(base);
  }

  await open(page, "stale");                                               // 보류 — 도착 카드는 안내 문구로 바뀜
  expect(await measure(page)).toEqual(base);
});

test("첫 로딩 스켈레톤도 결과 화면과 같은 자리를 차지한다", async ({ page }) => {
  await open(page);
  const loaded = await measure(page);
  await open(page, "loading");
  await expect(page.getByTestId("skeleton")).toBeVisible();
  const sk = await measure(page, "skeleton");
  expect(sk.inputY).toBe(loaded.inputY);
});
