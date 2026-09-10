/* 夏天Jackey 价目表 · Service Worker (改70)
 * 作用: 封面图本地锁存 —— 顾客看过一次的封面永久存在其设备上,
 *       之后再打开页面直接读本地、零网络请求、图片秒出;
 *       图片在后台静默更新(先给旧的、拿到新的换上), 更换封面也能正常传播。
 * 策略: 站点全部 .jpg(封面/头像avatar/背景bg) = stale-while-revalidate; 其余请求不拦截(页面/数据保持在线取最新)
 */
const CACHE = 'gt-covers-v1';

self.addEventListener('install', e => self.skipWaiting());

self.addEventListener('activate', e => {
  e.waitUntil((async () => {
    // 清理旧版本缓存
    const keys = await caches.keys();
    await Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)));
    await self.clients.claim();
  })());
});

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
