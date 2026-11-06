import { test, expect } from "@playwright/test";
import type { Page } from "@playwright/test";

// 저장된 실제 모델 값(?scenario=curve). 녹십자약국: 앞 3명 98%, 10명 92%, 25명 1%. 창신역4번출구: 2정류장 전
const open = async (page: Page, stop = "sb02-32") => {
  await page.goto("/?scenario=curve");
  await page.getByTestId(`stop-${stop}`).click();
  await expect(page.getByTestId("hero")).toBeVisible();
};
const chip = (page: Page, n: number) => page.getByRole("button", { name: `${n}명`, exact: true });

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.clear());
});

test("입력 전에는 탈 수 있는지 말하지 않고 신호등 색도 쓰지 않는다", async ({ page }) => {
  await open(page);
  const hero = page.getByTestId("hero");
  await expect(hero).toHaveAttribute("data-tone", "idle");
  await expect(page.getByTestId("n-input")).toHaveValue("");
  await expect(page.getByTestId("verdict")).toContainText("앞 사람 수를 고르면 알려 드려요");
  await expect(page.getByTestId("result")).not.toContainText(/\d+%|번쯤|탈 수 있어요/);
  await expect(page.getByTestId("verdict-icon")).toHaveAttribute("data-tone", "idle");
  // 줄과 무관한 버스 쪽 정보는 입력 없이 보인다
  await expect(page.getByTestId("arrival")).toContainText(/\d+분\d+초/);
  await expect(page.getByTestId("next-bus")).toContainText("약 12분 후");
  await expect(page.getByTestId("loads")).toContainText("약 39명");
  await expect(page.getByTestId("loads")).toContainText("약 43명");
});

test("앞 사람 수를 고르면 그 조건의 추정값이라고 밝혀 보여 준다", async ({ page }) => {
  await open(page);
  await chip(page, 10).click();
  const result = page.getByTestId("result");
  await expect(result).toContainText("약 43명에 내 앞 10명이 타면 약 53명");   // 위의 버스 인원과 결론이 이어지게
  await expect(result).toContainText("10번 중 9번쯤 타요");
  await expect(result).toContainText("그러면 10번 중 9번쯤 타요");
  await expect(result).toContainText("예상 약 92%");
  await expect(page.getByTestId("hero")).toHaveAttribute("data-tone", "warn");
  await chip(page, 20).click();
  await expect(result).toContainText("약 43명에 내 앞 20명이 타면 약 63명");
  await expect(result).toContainText("10번 중 1번쯤 타요");
  await expect(page.getByTestId("hero")).toHaveAttribute("data-tone", "bad");
});

test("앞 사람이 없으면 '내 앞 0명'이라고 하지 않는다", async ({ page }) => {
  await open(page, "jr03-20");
  await page.getByTestId("n-input").fill("0");
  const result = page.getByTestId("result");
  await expect(result).toContainText("약 22명에 내 앞에 아무도 없으면");
  await expect(result).not.toContainText("0명이 타면");
  await expect(result).toContainText("그러면 거의 항상 타요");
});

test("몰림이 잦은 정류장은 최신 서버 기준(0.95)을 넘어야 초록이다", async ({ page }) => {
  await open(page, "jr03-23");  // 창신역4번출구: 앞 6명까지 초록, 10명(88%)은 주황
  await page.getByTestId("n-input").fill("6");
  await expect(page.getByTestId("hero")).toHaveAttribute("data-tone", "ok");
  await page.getByTestId("n-input").fill("7");
  await expect(page.getByTestId("hero")).toHaveAttribute("data-tone", "warn");
  await chip(page, 10).click();
  await expect(page.getByTestId("hero")).toHaveAttribute("data-tone", "warn");
  await expect(page.getByTestId("result")).toContainText("예상 약 88%");
});

test("ⓘ 안내는 사용자가 뜻을 몰랐던 표현을 쓰지 않고, 결과가 왜 다른지 말한다", async ({ page }) => {
  await open(page);
  await page.getByTestId("about").click();
  const sheet = page.getByTestId("about-sheet");
  await expect(sheet).toContainText("버스마다 탈 수 있는 인원");
  await expect(sheet).toContainText("평소 내리는 사람");
  await expect(sheet).not.toContainText(/거의 그대로|검증 전|공공데이터/);
});

test("보류 이유는 개발자 문장 대신 사용자 말로 보여 준다", async ({ page }) => {
  await page.goto("/?scenario=holiday");
  await page.getByTestId("stop-sb02-32").click();
  await expect(page.getByTestId("result")).toContainText("오늘은 탑승 예측을 쉬어요");
  await expect(page.getByTestId("result")).not.toContainText("검증 전");
  await expect(page.getByTestId("loads")).toContainText("약 39명");  // 예측을 쉬어도 지금 인원은 서울시 정보라 보인다
  await page.getByTestId("about").click();
  await expect(page.getByTestId("about-reason")).toContainText("예측이 맞는지 아직 확인하지 못했어요");
  await expect(page.getByTestId("about-reason")).not.toContainText("검증 전");
});

test("95% 이상과 5% 이하는 숫자를 좁혀 말하지 않는다", async ({ page }) => {
  await open(page);
  await page.getByTestId("n-input").fill("3");
  const result = page.getByTestId("result");
  await expect(result).toContainText("거의 항상 타요");
  await expect(result).toContainText("예상 95% 이상");
  await expect(result).not.toContainText("98%");
  await page.getByTestId("n-input").fill("25");
  await expect(result).toContainText("거의 못 타요");
  await expect(result).toContainText("예상 5% 이하");
});

test("인원이 아직 안 정해졌으면 언제 확인되는지 알리고, 정해졌으면 말하지 않는다", async ({ page }) => {
  await open(page, "jr03-23");
  await chip(page, 10).click();
  await expect(page.getByTestId("loads")).toContainText("에서 출발하면 실제 탑승 기록으로 다시 계산해요");
  await page.getByTestId("stop-switch").click();
  await page.getByTestId("stop-jr03-20").click();                  // 1정류장 전: 왜 바뀌는지 말한다
  await chip(page, 10).click();
  await expect(page.getByTestId("loads")).toContainText("에서 출발하면 실제 탑승 기록으로 다시 계산해요");
  await page.getByTestId("stop-switch").click();
  await page.getByTestId("stop-sb02-32").click();                  // 바로 앞이어도 범위가 넓으면 앞 정류장에 서 있는 버스다(39~50명)
  await chip(page, 10).click();
  await expect(page.getByTestId("loads")).toContainText("에서 출발하면 실제 탑승 기록으로 다시 계산해요");
  await page.getByTestId("stop-switch").click();
  await page.getByTestId("stop-jr03-19").click();                  // 달리는 바로 앞 버스(15~15명)
  await chip(page, 10).click();
  await expect(page.getByTestId("result")).toContainText(/내 앞 10명.*%/);
  await expect(page.getByTestId("loads")).not.toContainText("실제 탑승 기록으로");
});

test("인원을 빈자리로 읽지 않게 타고 있는 사람이라고 숫자 하나로 말한다", async ({ page }) => {
  await open(page);
  const loads = page.getByTestId("loads");
  await expect(loads).toContainText("지금 약 39명 타고 있어요");
  await expect(loads).toContainText("서울시 · 태그 기준");
  await expect(loads).toContainText("더 타서 도착 땐 약 43명일 것 같아요");
  await expect(loads).toContainText("한자리 예측");
  await expect(loads).not.toContainText("50명");                  // 범위를 함께 말하면 어느 숫자가 답인지 헷갈린다
  await expect(page.locator("body")).not.toContainText("공공데이터");
  await page.getByTestId("stop-switch").click();
  await page.getByTestId("stop-jr03-19").click();                  // 범위 폭이 없는 버스(15~15명)
  await expect(page.getByTestId("stop-name")).toContainText("동대문");
  await expect(loads).toContainText("도착 때도 약 15명일 거예요");   // 거의 정해졌으면 말끝이 달라진다
  await page.getByTestId("stop-switch").click();
  await page.getByTestId("stop-jr03-20").click();                  // 1정류장 전이면 아직 정해지지 않았다
  await expect(page.getByTestId("stop-name")).toHaveText("동묘앞역");
  await expect(loads).toContainText("더 타서 도착 땐 약 22명일 것 같아요");
});

test("시뮬레이션: 앞 정류장을 떠나면 말끝이 단정으로 바뀌고, 앞 정류장에서 몰리면 답이 달라진다", async ({ page }) => {
  const at = async (step: number) => {
    await page.goto(`/?scenario=approach-${step}`);
    await page.getByTestId("stop-jr03-20").click();
    await expect(page.getByTestId("hero")).toBeVisible();
  };
  const loads = page.getByTestId("loads");
  const result = page.getByTestId("result");
  await at(1);
  await expect(loads).toContainText("더 타서 도착 땐 약 20명일 것 같아요");
  await at(3);                                                     // 1정류장 전: 태울 정류장이 하나 남았다
  await expect(loads).toContainText("지금 약 15명 타고 있어요");
  await expect(loads).toContainText("더 타서 도착 땐 약 22명일 것 같아요");
  await chip(page, 10).click();
  await expect(loads).toContainText("에서 출발하면 실제 탑승 기록으로 다시 계산해요");
  await at(4);                                                     // 바로 앞이지만 앞 정류장에 서 있다. 인원은 출발할 때 갱신된다
  await expect(loads).toContainText("지금 약 15명 타고 있어요");
  await expect(loads).toContainText("더 타서 도착 땐 약 20명일 것 같아요");
  await chip(page, 10).click();
  await expect(loads).toContainText("에서 출발하면 실제 탑승 기록으로 다시 계산해요");
  await at(5);                                                     // 앞 정류장을 떠나 달리는 중
  await expect(loads).toContainText("지금 약 23명 타고 있어요");
  await expect(loads).toContainText("도착 때도 약 23명일 거예요");
  await chip(page, 10).click();
  await expect(result).toContainText(/내 앞 10명.*%/);
  await expect(loads).not.toContainText("실제 탑승 기록으로");
  await at(7);                                                     // 앞 정류장에서 36명 몰림
  await expect(loads).toContainText("지금 약 51명 타고 있어요");
  await chip(page, 5).click();
  await expect(result).toContainText("거의 못 타요");
});

test("언제 확인되는지 실제 이전 정류장 이름으로 말한다", async ({ page }) => {
  await open(page, "jr03-20");                                     // 입력 전에도 보인다
  await expect(page.getByTestId("loads")).toContainText("버스가 동대문역(1정류장 전)에서 출발하면 실제 탑승 기록으로 다시 계산해요");
  await page.getByTestId("stop-switch").click();
  await page.getByTestId("stop-jr03-23").click();
  await expect(page.getByTestId("loads")).toContainText("버스가 숭인1동주민센터(1정류장 전)에서 출발하면");
});

test("입력 전에도 다음에 무엇을 하면 되는지 흐름이 이어진다", async ({ page }) => {
  await open(page);
  await expect(page.getByTestId("basis")).toHaveText("여기에 내 앞 사람이 타면…");
  await chip(page, 10).click();
  await expect(page.getByTestId("basis")).toHaveText("약 43명에 내 앞 10명이 타면 약 53명");
});

test("같은 칩을 다시 누르면 입력 전 상태로 돌아간다", async ({ page }) => {
  await open(page);
  await chip(page, 10).click();
  await expect(page.getByTestId("result")).toContainText(/내 앞 10명.*%/);
  await chip(page, 10).click();
  await expect(page.getByTestId("n-input")).toHaveValue("");
  await expect(page.getByTestId("hero")).toHaveAttribute("data-tone", "idle");
  await expect(page.getByTestId("result")).not.toContainText(/\d+%/);
});

test("정류장을 바꾸면 앞 정류장에서 고른 인원을 이어 쓰지 않는다", async ({ page }) => {
  await open(page);
  await chip(page, 10).click();
  await expect(page.getByTestId("result")).toContainText(/내 앞 10명.*%/);
  await page.getByTestId("other-sb02-30").click();
  await expect(page.getByTestId("stop-name")).toHaveText("한성대입구역5번출구");
  await expect(page.getByTestId("n-input")).toHaveValue("");
  await expect(page.getByTestId("result")).not.toContainText(/\d+%/);
});

test("앞·뒤 정류장 화면에서도 입력 전에는 내 정류장 확률을 보이지 않는다", async ({ page }) => {
  await open(page);
  await page.getByTestId("tab-1").click();
  await expect(page.getByTestId("card-sb02-32")).not.toContainText(/\d+%|확률/);
  await page.getByTestId("tab-0").click();
  await chip(page, 10).click();
  await expect(page.getByTestId("result")).toContainText(/내 앞 10명.*%/);
  await page.getByTestId("tab-1").click();
  await expect(page.getByTestId("card-sb02-32")).toContainText("예상 약 92%");
});

test("일요일·공휴일이면 입력을 요구하지 않고 쉰다고 말하며, 다음 버스는 그대로 보인다", async ({ page }) => {
  await page.goto("/?scenario=holiday");
  await page.getByTestId("stop-sb02-32").click();
  await expect(page.getByTestId("result")).toContainText("오늘은 탑승 예측을 쉬어요");
  await expect(page.getByTestId("hero")).toHaveAttribute("data-tone", "hold");
  await expect(page.getByTestId("next-bus")).toBeVisible();
});

for (const [width, height] of [[320, 568], [360, 640], [390, 780], [412, 915]] as [number, number][]) {
  test(`${width}x${height}: 칩을 눌러도 입력 위치가 움직이지 않고 넘치지 않는다`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await open(page);
    const y = async () => (await page.getByTestId("n-minus").boundingBox())!.y;
    const before = await y();
    await chip(page, 10).click();
    await expect(page.getByTestId("result")).toContainText(/내 앞 10명.*%/);
    expect(Math.abs(await y() - before)).toBeLessThanOrEqual(1);
    await page.getByTestId("stop-switch").click();
    await page.getByTestId("stop-jr03-23").click();
    await chip(page, 10).click();
    await expect(page.getByTestId("loads")).toContainText("실제 탑승 기록으로");
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  });
}
