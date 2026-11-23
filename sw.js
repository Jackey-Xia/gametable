/* 改159: Service Worker —— 老客秒出核心
 * stale-while-revalidate: 命中缓存立即返回(秒出), 同时后台静默刷新缓存。
 * 每部署一次 CACHE 版本号(1794081423)随之变化 -> 新 SW 激活即清掉旧缓存, 不会把旧页喂给老客。
 * 例外: ver.json 永远走网络(保证版本探测/自动刷新生效); 跨域封面(weserv)不拦截(由 IndexedDB 接管); 可变图片(商品封面等)强制绕过 HTTP 缓存直连线上最新(避免老客长期看到旧封面); 固定图片(站点图标 icon.png / 背景 bg.jpg)走 SW 缓存秒出(改动极少, 老客免重复下载); 带 _bg=1 / no-store 的后台探测直连网络。
 */
/* 改2026-11-22复核5: CACHE 名由构建期 sync_all.py 从 ver.json 的 v 派生(md5[:8]),
   占位符 AUTO 会被替换。真发版(bump v)才换名 -> 新 SW 清旧缓存 -> 首开即新页;
   cron 每小时重建但 v 不变 -> 名字不变 -> 不重装 SW -> 老客 0 成本。勿手写固定值。 */
const CACHE = 'gt-sw-vAUTO';
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
  /* 改2026-11-22: 详情(整包/分片)与封面清单是可变数据, 版本参数必须进缓存键,
     否则 ?v= 无效 -> 详情改动老客要开两次才看到 */
  if(/game_details\.json$/.test(p) || /\/details\/(?:p\d{2}|_keys)\.json$/.test(p) || /\/covers\/manifest.*\.json$/.test(p))
    return p + u.search;
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

/* 改2026-11-23复核10: 网络优先 + 最近缓存兜底, data.js / 详情(整包+分片+键索引)共用。
   ★修 B1 分片自带漏洞: 详情此前落默认 swr()=缓存优先, 命中即 return(注释44-46自承 SWR 未实现),
     前端详情 URL 的 ?v= 取自 data_v(不是 v), 改详情但 data_v 没变时老客永远看旧内容;
     _keys.json 陈旧还会让新上架商品按钮灰着/点开落空。
   ★复核11: 纯网络优先弱网点开要干等 -> 升级为真 SWR(300ms 竞速):
     - 网络 300ms 内回来: 用最新响应(200 回填缓存), 秒级拿到新内容;
     - 300ms 未回 + 有旧缓存: 先吐旧缓存(秒出), fetch 仍在后台跑, 完成自动回填 -> 下次即新内容;
       ★与旧 swr() 的本质区别: 后台 fetch 真实执行且回填, 不是"命中即 return 从不刷新";
     - 300ms 未回 + 无缓存: 继续等网络(不提前 error);
     - 网络失败(快速/最终): 有缓存用缓存, 无缓存 Response.error。
     key=cacheKey(u): 详情带 ?v=, data.js 归一 /data.js —— 各键独立, 详情绝不覆盖 data.js。
     详情点开才取不伤首屏, 离线/弱网均有兜底。 */
async function netFirst(req, u){
  var key = cacheKey(u);
  var cache = null;
  try{ cache = await caches.open(CACHE); }catch(e){}
  var netP = fetch(req).then(function(res){
    if(res && res.ok && cache){ try{ cache.put(key, res.clone()); }catch(e2){} }
    return res;                                   // 200 响应; 后台回填不依赖调用方是否还在等
  }).catch(function(){ return null; });           // 网络失败 -> null(不抛, 竞速里可判)
  var TIMEOUT = '__NET_TIMEOUT__';
  var timer = new Promise(function(res){ setTimeout(function(){ res(TIMEOUT); }, 300); });
  var first = await Promise.race([netP, timer]);
  if(first && first !== TIMEOUT) return first;     // 网络 300ms 内成功 -> 最新
  // 走到这里: 要么超时(TIMEOUT), 要么网络快速失败(null) -> 先找缓存兜底
  try{ var old = cache && await cache.match(key); if(old) return old; }catch(e3){}
  if(first === null) return Response.error();      // 网络明确失败且无缓存
  var res2 = await netP;                           // 超时且无缓存 -> 继续等后台网络
  return res2 || Response.error();
}

self.addEventListener('fetch', function(e){
  var req = e.request;
  if(req.method !== 'GET') return;
  var u;
  try{ u = new URL(req.url); }catch(err){ return; }
  if(u.origin !== self.location.origin) return;            // 跨域(封面走 weserv)不拦截, 交给 IndexedDB
  if(neverCache(u)) return;                                // ver.json 永远网络
  /* 改2026-11-22复核: 版本跳转 ?_v= 必须直连网络。否则 cacheKey 把
     /gametable/?_v=xxx 归一成 /index.html -> 拿到 SW 缓存旧页 -> MY 依旧 stale
     -> 45s 后再刷(最多3次)。让 ?_v= 绕过 SW 才能保证部署后老客一次收敛。 */
  if(u.searchParams.has('_v')) return;
  // 图片分流: 固定图(站点图标/背景)走 SWR 秒出; 其余可变图片(商品封面等)强制直连最新
  if(/\.(jpe?g|png|gif|webp|svg|avif)(\?|$)/i.test(u.pathname)){
    if(isFixedImage(u)){ e.respondWith(swr(req, u)); return; }   // 固定图: 老客秒出, 后台静默刷新
    e.respondWith(fetch(req, {cache:'reload'})); return;          // 可变图: 绕过 HTTP 缓存直连线上
  }
  // 封面 manifest 为可变数据(持续增删封面), 强制直连最新,
  // 避免老客命中 SW 陈旧缓存 -> 新增封面永不显示(修复: GTA6终极版手机端缺封面)
  if(/\/covers\/manifest.*\.json$/.test(u.pathname)){
    e.respondWith(fetch(req, {cache:'reload'})); return;
  }
  /* 改167fix: taobao.json 是可变链接表(持续增删购买/闲鱼链接)。旧逻辑落入默认 swr() ->
     SW 把首次缓存的陈旧 taobao.json 立即返回, 后台才刷新; 而前端仅当 tb_v 变化时才会重拉,
     重拉拿到的仍是 SW 陈旧副本 -> 新增链接"永久不更新"直至强刷(GTA6封面的同类坑)。
     与封面 manifest 同理强制直连最新。普通加载前端走 IDB 秒出根本不发此请求, 不影响老客速度。 */
  if(/(?:^|\/)taobao\.json$/.test(u.pathname)){
    e.respondWith(fetch(req, {cache:'reload'})); return;
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
    e.respondWith(netFirst(req, u));   /* 复核10: 抽通用函数, cacheKey(data.js)='/data.js', 行为不变 */
    return;
  }
  /* 改2026-11-23复核10: 详情三类资源网络优先(修 B1 分片漏洞)。
     game_details.json(整包兜底) / details/pXX.json(分片) / details/_keys.json(新上架按钮索引)
     此前落默认 swr() 缓存优先 -> 改详情老客看旧内容、新上架按钮灰着/落空。
     cacheKey 已让详情 key 带 ?v=u.search; netFirst 网络优先+缓存兜底, 离线仍可用。 */
  if(/game_details\.json$/.test(u.pathname) || /\/details\/(?:p\d{2}|_keys)\.json$/.test(u.pathname)){
    e.respondWith(netFirst(req, u));
    return;
  }
  e.respondWith(swr(req, u));
});

self.addEventListener('message', function(e){
  if(e.data && e.data.type === 'clear'){
    caches.keys().then(function(ks){ ks.forEach(function(k){ caches.delete(k); }); });
  }
});
