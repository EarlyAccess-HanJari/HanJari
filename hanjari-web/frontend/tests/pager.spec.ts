import { test, expect } from "@playwright/test";
import type { Page } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.clear());
});

// 손가락으로 미는 동작을 터치 이벤트로 흉내
const swipe = (page: Page, dx: number, dy = 0) =>
  page.getByTestId("pager").evaluate(async (el, [mx, my]) => {
    const r = el.getBoundingClientRect();
    const x0 = r.left + r.width / 2, y0 = r.top + 40;
    const mk = (type: string, x: number, y: number) => {
      const t = new Touch({ identifier: 1, target: el, clientX: x, clientY: y });
      el.dispatchEvent(new TouchEvent(type, { bubbles: true, cancelable: true, touches: type === "touchend" ? [] : [t], changedTouches: [t] }));
    };
    mk("touchstart", x0, y0);
    for (let i = 1; i <= 5; i++) mk("touchmove", x0 + (mx * i) / 5, y0 + (my * i) / 5);
    mk("touchend", x0 + mx, y0 + my);
  }, [dx, dy]);

test("탭으로 두 화면을 오간다", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("stop-sb02-32").click();
  await expect(page.getByTestId("tab-0")).toHaveAttribute("aria-selected", "true");
  await page.getByTestId("tab-1").click();
  await expect(page.getByTestId("timeline")).toBeVisible();
  await page.getByTestId("tab-0").click();
  await expect(page.getByTestId("hero")).toBeVisible();
});

test("좌우로 밀어서 화면이 넘어간다 / 세로로 밀면 안 넘어간다", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("stop-sb02-32").click();
  await page.getByTestId("hero").waitFor();
  await swipe(page, -30, 120);                                   // 세로 의도 → 그대로
  await expect(page.getByTestId("tab-0")).toHaveAttribute("aria-selected", "true");
  await swipe(page, -20);                                        // 짧게 → 그대로
  await expect(page.getByTestId("tab-0")).toHaveAttribute("aria-selected", "true");
  await swipe(page, -140);                                       // 왼쪽으로 밀기 → 두 번째
  await expect(page.getByTestId("tab-1")).toHaveAttribute("aria-selected", "true");
  await swipe(page, 140);                                        // 오른쪽으로 밀기 → 첫 번째
  await expect(page.getByTestId("tab-0")).toHaveAttribute("aria-selected", "true");
});

test("타임라인은 노선 순서(5번출구 → 2번출구 → 녹십자약국)이고 직전·다음이 맞다", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("stop-sb02-31").click();               // 한성대입구역2번출구
  await page.getByTestId("tab-1").click();
  const cards = page.getByTestId("timeline").locator("button");
  await expect(cards).toHaveCount(3);
  await expect(cards.nth(0)).toContainText("한성대입구역5번출구");
  await expect(cards.nth(0)).toContainText("직전");
  await expect(cards.nth(1)).toContainText("한성대입구역2번출구");
  await expect(cards.nth(1)).toContainText("내 정류장");
  await expect(cards.nth(1)).toHaveAttribute("aria-current", "true");
  await expect(cards.nth(2)).toContainText("녹십자약국");
  await expect(cards.nth(2)).toContainText("다음");
  await expect(cards.nth(2)).toContainText("다른 버스");           // 녹십자약국은 이미 앞서간 다른 차
  await expect(cards.nth(0)).not.toContainText("다른 버스");       // 5번출구는 같은 차
});

test("버스 아이콘은 내 버스의 실제 위치에 하나만 있다", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("stop-sb02-31").click();
  await page.getByTestId("tab-1").click();
  // 내 버스는 5번출구보다도 9정류장 앞 → 첫 줄 위쪽에 '접근 중' 표시
  await expect(page.getByTestId("bus-marker")).toContainText("버스 접근 중");
  await expect(page.getByTestId("timeline").locator("svg rect")).toHaveCount(1);
  await page.getByTestId("tab-0").click();
  await page.getByTestId("stop-switch").click();
  await page.getByTestId("stop-sb02-32").click();              // 녹십자약국: 버스가 곧 도착 → 그 줄에 아이콘
  await page.getByTestId("tab-1").click();
  await expect(page.getByTestId("bus-marker")).toHaveCount(0);
  await expect(page.getByTestId("timeline").locator("svg rect")).toHaveCount(1);
});
