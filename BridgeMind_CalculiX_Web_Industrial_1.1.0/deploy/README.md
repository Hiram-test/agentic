# 部署入口

本目录与项目根目录的 `Dockerfile`、`docker-compose.yml`、`.env.example` 共同构成单节点生产部署基线。复制 `.env.example` 为 `.env`，设置强 API 密钥，把合法获得且可执行的 CalculiX 2.23 `ccx` 放入 `solver/ccx`，运行 `docker compose up -d --build`，随后通过服务器域名或 IP 访问网站。公网 HTTPS 建议由云负载均衡、Caddy、Traefik 或带证书的上级 Nginx 终止 TLS，再把请求转发到本栈的 HTTP 端口；PWA 安装和离线缓存除 `localhost` 外要求安全上下文，因此公网部署必须启用 HTTPS。
