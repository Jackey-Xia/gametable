/* 夏天Jackey 价目表 · Service Worker (改75)
 * 作用: 图片的网络层加速 —— 运行期拦截图片请求, 先回缓存秒出, 后台按 ETag 静默校验。
 * 改74: 全量预缓存已下线(改由页面 IndexedDB 图库承担本地化), 避免同批图片存两份占手机空间。
 *       仅在页面报告"本机本地图库不可用"时, 才由页面发消息启用预缓存兜底。
 *       页面/数据/manifest 不拦截, 保证价格库存永远最新。
 * 改75: 后台刷新改为「按 ETag 条件校验」(If-None-Match)。
 *       · 未更换的封面 -> 服务器回 304(零字节), 保留原缓存, 不重新下载;
 *       · 只换了的那张 -> ETag 变化, 回 200, 仅重新下载这一张。
 *       因此【改 1 张图 = 只有那 1 张重下, 其余全部零流量】, 不会全量重载。
 *       注意: 缓存版本号请勿随意 bump —— 一改整池失效, 会导致所有封面重新下载。
 */
const CACHE = 'gt-covers-v4';

self.addEventListener('install', e => self.skipWaiting());

/* 兜底: 仅当页面判断本机 IndexedDB/CacheStorage 都不可用时, 才发消息让 SW 预缓存 */
self.addEventListener('message', e => {
  if (e.data && e.data.type === 'precache') { precache().catch(function(){}); }
});

self.addEventListener('activate', e => {
  e.waitUntil((async () => {
    // 清理旧版本缓存(含旧的 gt-covers-v2 全量预缓存, 回收空间)
    const keys = await caches.keys();
    await Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)));
    await self.clients.claim();
  })());
});

async function precache() {
  const cache = await caches.open(CACHE);
  let urls = ['avatar.jpg', 'bg.jpg'];
  try {
    const res = await fetch('covers/manifest.json', { cache: 'no-store' });
    if (res.ok) {
      const m = await res.json();
      Object.keys(m).forEach(k => { if (typeof m[k] === 'string') urls.push(m[k]); });
    }
  } catch (err) {}
  const base = self.registration.scope;
  urls = [...new Set(urls.map(u => new URL(u, base).href))];
  // 跳过已缓存的(增量)
  const have = new Set((await cache.keys()).map(r => r.url));
  urls = urls.filter(u => !have.has(u));
  // 6 并发分批下载, 避免挤占顾客网络
  let i = 0;
  async function worker() {
    while (i < urls.length) {
      const u = urls[i++];
      try {
        const r = await fetch(u);
        if (r && r.ok) await cache.put(u, r);
      } catch (err) {}
    }
  }
  await Promise.all(Array.from({ length: 6 }, worker));
}

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (url.origin !== location.origin) return;                 // 只管本站
  if (!/^\/gametable\/.+\.jpg$/i.test(url.pathname)) return; // 封面/头像/背景 全部锁存
  if (e.request.method !== 'GET') return;

  e.respondWith((async () => {
    const cache = await caches.open(CACHE);
    const cached = await cache.match(e.request);

    if (cached) {
      // ① 立即秒出缓存(快/离线可用) ② 后台按 ETag 校验: 换过的才重下, 没换的回304零字节
      e.waitUntil((async () => {
        try {
          const etag = cached.headers.get('etag');
          const headers = new Headers(e.request.headers);
          if (etag) headers.set('If-None-Match', etag);
          const res = await fetch(new Request(e.request, { headers }));
          // 200 = 内容已变更 -> 更新缓存; 304 = 未变更 -> 保留原缓存(不重新下载)
          if (res && res.ok) await cache.put(e.request, res.clone());
        } catch (err) {}
      })());
      return cached;
    }

    // 首次访问(无缓存): 正常拉取并入库
    try {
      const res = await fetch(e.request);
      if (res && res.ok) await cache.put(e.request, res.clone());
      return res;
    } catch (err) {
      return new Response('', { status: 504 });
    }
  })());
});
