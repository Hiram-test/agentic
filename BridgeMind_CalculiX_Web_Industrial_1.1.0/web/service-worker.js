"use strict"; // 启用严格 JavaScript 模式。
const CACHE_NAME = "bridgemind-calculix-web-v3"; // 定义可版本化静态缓存名称。
const APP_SHELL = ["/", "/index.html", "/styles.css", "/app.js", "/manifest.webmanifest", "/icons/icon-192.png", "/icons/icon-512.png"]; // 定义离线可打开的应用壳资源。
self.addEventListener("install", (event) => { // 监听 Service Worker 安装事件。
    event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)).then(() => self.skipWaiting())); // 缓存应用壳并立即进入等待完成状态。
}); // 结束安装事件处理。
self.addEventListener("activate", (event) => { // 监听新版本激活事件。
    event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))).then(() => self.clients.claim())); // 删除旧缓存并接管现有页面。
}); // 结束激活事件处理。
self.addEventListener("fetch", (event) => { // 监听同源资源请求。
    const request = event.request; // 读取当前请求。
    const url = new URL(request.url); // 解析请求地址。
    if (request.method !== "GET" || url.origin !== self.location.origin) { return; } // 只处理同源 GET 请求。
    if (url.pathname.startsWith("/api/")) { // 对 API 使用网络优先策略。
        event.respondWith(fetch(request).catch(() => new Response(JSON.stringify({ detail: "当前离线，API 不可用。" }), { status: 503, headers: { "Content-Type": "application/json" } }))); // 网络失败时返回显式离线错误。
        return; // 结束 API 请求处理。
    } // 结束 API 分支。
    event.respondWith(caches.match(request).then((cached) => cached || fetch(request).then((response) => { const copy = response.clone(); caches.open(CACHE_NAME).then((cache) => cache.put(request, copy)); return response; }).catch(() => caches.match("/index.html")))); // 对静态文件使用缓存优先并动态补充缓存。
}); // 结束请求事件处理。
