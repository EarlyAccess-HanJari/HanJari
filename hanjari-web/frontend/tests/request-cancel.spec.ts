import {test,expect} from '@playwright/test';
import fixture from '../src/mock/predict_n3.json' with {type:'json'};

test.use({serviceWorkers:'block'});
test.skip(process.env.VITE_MOCK!=='0','HTTP request cancellation');

test('changed input aborts the old request without displaying an error',async({page})=>{
  const seen:number[]=[];
  await page.addInitScript(()=>{
    localStorage.clear();
    (window as any).__aborted=[];
    const original=window.fetch.bind(window);
    window.fetch=(input,init)=>{
      const n=Number(new URL(String(input),location.href).searchParams.get('n'));
      init?.signal?.addEventListener('abort',()=> (window as any).__aborted.push(n));
      return original(input,init);
    };
  });
  await page.route('**/api/predict?*',async route=>{
    const n=Number(new URL(route.request().url()).searchParams.get('n'));seen.push(n);
    if(n===4)await new Promise(resolve=>setTimeout(resolve,2000));
    await route.fulfill({json:{...fixture,n_ahead:n,service:{status:'ok',mode:'latest',release:'test',
      data_status:'ok',routes:{},model:{status:'ok',loaded:'v1',disk:'v1'},ready:true}}});
  });
  await page.goto('/');await page.getByTestId('stop-sb02-32').click();
  await expect(page.getByTestId('hero')).toBeVisible();
  await page.getByTestId('n-input').fill('4');
  await expect.poll(()=>seen.includes(4)).toBe(true);
  await page.getByTestId('n-input').fill('5');
  await expect.poll(()=>page.evaluate(()=>(window as any).__aborted.includes(4))).toBe(true);
  await expect.poll(()=>seen.includes(5)).toBe(true);
  await expect(page.getByTestId('verdict')).toContainText('%');
  await expect(page.locator('body')).not.toContainText('연결이 불안정해요');
  await expect(page.locator('body')).not.toContainText('서버에 연결할 수 없어요');
});
