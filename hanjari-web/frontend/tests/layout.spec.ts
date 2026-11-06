import { test, expect } from "@playwright/test";

const PHONES: [number, number][] = [
  [320, 568], [360, 560], [390, 844], [480, 800], [768, 1024], [1440, 900],
];

for (const [width, height] of PHONES) {
  test(`${width}x${height}: 로컬 UI 순서와 가로 넘침 확인`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await page.goto("/");
    await page.getByTestId("stop-sb02-30").click();
    await expect(page.getByTestId("loads")).toBeVisible();
    const top = async (id: string) => (await page.getByTestId(id).boundingBox())!.y;
    expect(await top("arrival")).toBeLessThan(await top("loads"));
    expect(await top("loads")).toBeLessThan(await top("result"));
    expect(await top("result")).toBeLessThan(await top("n-input"));
    // 첫 화면은 세로 스크롤 없이 한 화면 안에 — 페이지 자체는 스크롤하지 않음
    expect(await page.evaluate(() => document.documentElement.scrollHeight)).toBeLessThanOrEqual(height);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await expect(page.getByRole("button", { name: "20명", exact: true })).toHaveCount(1);
    await expect(page.getByTestId("dev-switcher")).toHaveCount(0);
    await page.getByTestId("tab-1").click();
    await expect(page.getByTestId("card-sb02-31")).toBeVisible();
  });
}

test("재계산 중 카드는 그대로 두고 흐리게만 하며 입력 위치를 유지한다", async ({ page }) => {
  await page.clock.install({ time: new Date("2026-09-30T08:00:00+09:00") });
  await page.goto("/");
  await page.getByTestId("stop-sb02-32").click();
  await page.clock.runFor(1000);
  const input = page.getByTestId("n-input");
  const hero = page.getByTestId("hero");
  const before = (await input.boundingBox())!.y;
  const heroH = (await hero.boundingBox())!.height;
  await page.getByTestId("n-plus").click();
  await page.clock.runFor(260);
  await expect(hero).toHaveAttribute("aria-busy", "true");
  expect((await input.boundingBox())!.y).toBe(before);
  expect((await hero.boundingBox())!.height).toBe(heroH);
  await page.clock.runFor(400);
  await expect(hero).toHaveAttribute("aria-busy", "false");
  expect((await input.boundingBox())!.y).toBe(before);
});

// 상태·문구 길이가 달라져도 대기 인원 버튼은 같은 자리 (누르던 버튼이 손 밑에서 밀리지 않게)
for (const [width, height] of [[375, 812], [360, 780], [412, 915]] as [number, number][]) {
  test(`${width}x${height}: 상태가 바뀌어도 대기 인원 버튼 위치가 같다`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    const ys: Record<string, number> = {};
    for (const scenario of ["", "stale", "wide", "down"]) {
      await page.goto(`/?scenario=${scenario}`);
      await page.evaluate(() => localStorage.setItem("hanjari.sel", JSON.stringify({ route: "sb02", stop: "32" })));
      await page.reload();
      await expect(page.getByTestId("n-minus")).toBeVisible();
      await expect(page.getByTestId("hero-skeleton")).toHaveCount(0);
      ys[scenario || "normal"] = (await page.getByTestId("n-minus").boundingBox())!.y;
    }
    await page.goto("/");
    await page.getByTestId("n-input").fill("20");                // 목업 n30: 확률이 낮아 안내 문구가 길어짐
    await expect(page.getByTestId("hero")).toHaveAttribute("data-level", "어려울 수 있음");
    await expect(page.getByTestId("hero")).toHaveAttribute("aria-busy", "false");
    ys.low = (await page.getByTestId("n-minus").boundingBox())!.y;
    expect(Math.max(...Object.values(ys)) - Math.min(...Object.values(ys))).toBeLessThanOrEqual(1);
  });
}

// 칩을 누르는 손가락에 가리지 않도록 결론은 입력 바로 위에 온다
for (const width of [320, 360, 412]) {
  test(`${width}px: 결론이 입력 바로 위에 있다`, async ({ page }) => {
    await page.setViewportSize({ width, height: 780 });
    await page.goto("/");
    await page.evaluate(() => localStorage.setItem("hanjari.sel", JSON.stringify({ route: "sb02", stop: "30" })));
    await page.reload();
    const verdict = (await page.getByTestId("verdict").boundingBox())!;
    const input = (await page.getByTestId("n-input").boundingBox())!;
    expect(verdict.y + verdict.height).toBeLessThanOrEqual(input.y);
    expect(input.y - (verdict.y + verdict.height)).toBeLessThanOrEqual(100);  // 결론 줄 수가 달라져도 입력이 안 밀리도록 잡아 둔 여백 포함
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  });
}
