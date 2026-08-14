# CalculiX 2.23 可执行文件放置目录

把服务器对应平台的 `ccx` 可执行文件放在本目录并命名为 `ccx`，Linux 下执行 `chmod +x solver/ccx`，随后运行 `docker compose up -d --build`。交付包没有捆绑 CalculiX 二进制，原因是不同服务器需要选择与 CPU、稀疏求解器和操作系统匹配的合法构建；网站会在 `/api/calculix/status` 明确报告求解器是否可用。
