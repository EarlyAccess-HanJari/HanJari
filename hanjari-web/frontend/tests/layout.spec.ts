import { test, expect } from "@playwright/test";
import type { Page } from "@playwright/test";

// 시선 흔들림 점검: 상태가 바뀌어도 핵심 카드(도착+결과) 자리와 입력칸 위치가 같아야 한다.
// 내용이 길면 카드 안에서만 스크롤되므로 안쪽 카드 높이가 아니라 바깥 자리(hero)를 비교
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.clear());
});

const open = async (page: Page, scenario = "") => {
  await page.goto(scenario ? `/?scenario=${scenario}` : "/");
  await page.getByTestId("stop-sb02-32").click();
};

const measure = async (page: Page) => {
  await page.waitForTimeout(500);  // 목업 응답(300ms) 뒤
  const h = (await page.getByTestId("hero").boundingBox())!;
  const i = (await page.getByTestId("n-input").boundingBox())!;
  const scrollY = await page.evaluate(() => window.scrollY);  // 버튼을 누르며 스크롤돼도 문서 기준 위치로 비교
  return { heroY: Math.round(h.y + scrollY), heroH: Math.round(h.height), inputY: Math.round(i.y + scrollY) };
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
  expect(await measure(page)).toEqual(loaded);
});

// 한 화면 고정: 페이지 스크롤이 없어야 주소창이 나타났다 사라지며 화면이 덜컹이지 않음
const PHONES: [string, number, number][] = [
  ["폴드 커버", 344, 744], ["갤럭시 S24", 360, 656], ["갤럭시 S24 울트라", 384, 712],
  ["아이폰 15", 393, 659], ["갤럭시 A", 412, 780], ["작은 폰", 360, 560],
];
for (const [name, width, height] of PHONES) {
  test(`${name} ${width}x${height}: 페이지 스크롤 없이 핵심이 다 보이고, 상태가 바뀌어도 입력칸이 그대로`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await open(page);
    const base = await measure(page);
    const fits = () => page.evaluate(() => ({
      scroll: document.documentElement.scrollHeight - window.innerHeight,
      bottom: Math.round(document.querySelector("[data-testid=other-stops]")!.getBoundingClientRect().bottom),
      quick: Math.round([...document.querySelectorAll("button")].find((b) => b.textContent === "20명")!.getBoundingClientRect().bottom),
    }));
    for (const sc of ["", "tight", "hard", "wide", "stale"]) {
      if (sc) await open(page, sc);
      expect(await measure(page), sc).toEqual(base);
      const f = await fits();
      expect(f.scroll, `${sc} 페이지 스크롤`).toBeLessThanOrEqual(0);
      expect(f.quick, `${sc} 인원 버튼이 화면 안`).toBeLessThanOrEqual(height);
      expect(f.bottom, `${sc} 다른 정류장 줄이 화면 안`).toBeLessThanOrEqual(height);
    }
    await page.getByTestId("n-input").fill("abc");
    expect(await measure(page)).toEqual(base);
  });
}
