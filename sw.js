/* 改159: Service Worker —— 老客秒出核心
 * stale-while-revalidate: 命中缓存立即返回(秒出), 同时后台静默刷新缓存。
 * 每部署一次 CACHE 版本号(1794081423)随之变化 -> 新 SW 激活即清掉旧缓存, 不会把旧页喂给老客。
 * 例外: ver.json 永远走网络(保证版本探测/自动刷新生效); 跨域封面(weserv)不拦截(由 IndexedDB 接管); 可变图片(商品封面等)强制绕过 HTTP 缓存直连线上最新(避免老客长期看到旧封面); 固定图片(站点图标 icon.png / 背景 bg.jpg)走 SW 缓存秒出(改动极少, 老客免重复下载); 带 _bg=1 / no-store 的后台探测直连网络。
 */
const CACHE = 'gt-sw-v1794382871';
const VER_URL = 'ver.json';

self.addEventListener('install', function(e){ self.skipWaiting(); });

self.addEventListener('activate', function(e){
  e.waitUntil((async function(){
    var keys = await caches.keys();
    await Promise.all(keys.filter(function(k){ return k !== CACHE; }).map(function(k){ return caches.delete(k); }));
    await self.clients.claim();
  })());
});

function neverCache(u){ return u.pathname.indexOf(VER_URL) >= 0; }

function cacheKey(u){
  var p = u.pathname;
  if(p.slice(-8) === 'data.js') return '/data.js';           // 每次带 ?t= 去重 -> 归一成同一份
  if(p === '/' || p === '/gametable/' || p.slice(-10) === 'index.html') return '/index.html';
  return p;
}

/* 改169: icon.png 自改168 起同时作 favicon 与 logo，是站点固定图标。
   原白名单仍是改168 前的 avatar_fill.png，导致图标被误判为可变商品封面、
   走 fetch(req,{cache:'reload'}) 强制绕过缓存；手机/微信 WebView 可能重复下 28KB。
   归入固定图后走 swr() 缓存优先，老客 0 网络。勿改回 avatar_fill.png。 */
// 固定图片(站点图标/背景)改动极少, 适合 SW 缓存秒出; 其余图片(商品封面等)为可变资源
function isFixedImage(u){
  return /(?:^|\/)(icon\.png|bg\.jpg)$/.test(u.pathname);
}

async function swr(req, u){
  var cache = await caches.open(CACHE);
  var key = cacheKey(u);
  try{
    var cached = await cache.match(key);
    if(cached) return cached;                 /* 命中缓存 -> 秒出 */
  }catch(e){}
  /* 改159fix: 旧写法 `return cached || network` 中 cached 是 Promise(恒为真),
     首访会误把空缓存 Promise 当作命中返回 -> 页面拿到 undefined -> game_details.json 等请求失败。
     这里明确: 有缓存用缓存, 否则走网络并回填。 */
  var res = await fetch(req);
  if(res && res.ok){ try{ cache.put(key, res.clone()); }catch(e){} }
  return res;
}

self.addEventListener('fetch', function(e){
  var req = e.request;
  if(req.method !== 'GET') return;
  var u;
  try{ u = new URL(req.url); }catch(err){ return; }
  if(u.origin !== self.location.origin) return;            // 跨域(封面走 weserv)不拦截, 交给 IndexedDB
  if(neverCache(u)) return;                                // ver.json 永远网络
  // 图片分流: 固定图(站点图标/背景)走 SWR 秒出; 其余可变图片(商品封面等)强制直连最新
  if(/\.(jpe?g|png|gif|webp|svg|avif)(\?|$)/i.test(u.pathname)){
    if(isFixedImage(u)){ e.respondWith(swr(req, u)); return; }   // 固定图: 老客秒出, 后台静默刷新
    e.respondWith(fetch(req, {cache:'reload'})); return;          // 可变图: 绕过 HTTP 缓存直连线上
  }
  var cc = req.headers.get('cache-control') || '';
  if(cc.indexOf('no-store') >= 0 || u.searchParams.has('_bg')){
    e.respondWith(fetch(req));                             // 后台探测直连网络, 不读写缓存
    return;
  }
  /* 改164: data.js 是价格库存主数据。旧逻辑把 data.js?v=xxx 归一成 /data.js 做 cache-first,
     且注释里承诺的 stale-while-revalidate 并未实现(命中即 return, 从不后台刷新) ->
     WPS 推送新库存后老客永远拿到第一份缓存。改为网络优先 + 最近一次缓存兜底(离线可用),
     前端另有 IndexedDB 秒出层, 不会牺牲首屏速度。 */
  if(/(?:^|\/)data\.js$/.test(u.pathname)){
    e.respondWith((async function(){
      try{
        var res = await fetch(req);
        if(res && res.ok){ try{ var c=await caches.open(CACHE); c.put('/data.js',res.clone()); }catch(e2){} }
        return res;
      }catch(err){
        try{ var c2=await caches.open(CACHE); var old=await c2.match('/data.js'); if(old)return old; }catch(e2){}
        return Response.error();
      }
    })());
    return;
  }
  e.respondWith(swr(req, u));
});

self.addEventListener('message', function(e){
  if(e.data && e.data.type === 'clear'){
    caches.keys().then(function(ks){ ks.forEach(function(k){ caches.delete(k); }); });
  }
});
