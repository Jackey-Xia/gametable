/* 夏天Jackey 价目表 · Service Worker (改74)
 * 作用: 图片的网络层加速 —— 运行期拦截图片请求, 先回缓存秒出, 后台静默刷新。
 * 改74: 全量预缓存已下线(改由页面 IndexedDB 图库承担本地化), 避免同批图片存两份占手机空间。
 *       仅在页面报告"本机本地图库不可用"时, 才由页面发消息启用预缓存兜底。
 * 页面/数据/manifest 不拦截, 保证价格库存永远最新。
 */
const CACHE = 'gt-covers-v3';

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
    // 后台刷新: 有新图就换上, 下次打开即为新图
    const refresh = fetch(e.request).then(res => {
      if (res && res.ok) cache.put(e.request, res.clone());
      return res;
    }).catch(() => null);
    return cached || refresh.then(res => res || new Response('', { status: 504 }));
  })());
});
