/* 改159: Service Worker —— 老客秒出核心
 * stale-while-revalidate: 命中缓存立即返回(秒出), 同时后台静默刷新缓存。
 * 每部署一次 CACHE 版本号(1793678497)随之变化 -> 新 SW 激活即清掉旧缓存, 不会把旧页喂给老客。
 * 例外: ver.json 永远走网络(保证版本探测/自动刷新生效); 跨域封面(weserv)不拦截(由 IndexedDB 接管); 头图/头像等可变图片不进 SW 缓存且强制绕过 HTTP 缓存直连线上(避免老客长期看到旧缓存图); 带 _bg=1 / no-store 的后台探测直连网络。
 */
const CACHE = 'gt-sw-v1793678497';
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
  // 可变图片(头图/头像/横幅)不进 SW 缓存, 且强制绕过 HTTP 缓存直连线上最新, 避免老客长期看到旧缓存图
  if(/\.(jpe?g|png|gif|webp|svg|avif)(\?|$)/i.test(u.pathname)){
    e.respondWith(fetch(req, {cache:'reload'})); return;
  }
  var cc = req.headers.get('cache-control') || '';
  if(cc.indexOf('no-store') >= 0 || u.searchParams.has('_bg')){
    e.respondWith(fetch(req));                             // 后台探测直连网络, 不读写缓存
    return;
  }
  e.respondWith(swr(req, u));
});

self.addEventListener('message', function(e){
  if(e.data && e.data.type === 'clear'){
    caches.keys().then(function(ks){ ks.forEach(function(k){ caches.delete(k); }); });
  }
});
