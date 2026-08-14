# BridgeMind CalculiX Web 1.1.0 快速启动

## 1. 电脑和同一 Wi-Fi 手机直接使用

在 Windows PowerShell、macOS Terminal 或 Linux Shell 中进入项目目录并执行：

```bash
python -m pip install -r requirements.txt
python scripts/run_lan.py
```

终端会打印两个地址：电脑使用 `http://127.0.0.1:8000`，手机使用 `http://电脑局域网IP:8000`。手机和电脑必须位于同一局域网，Windows 首次弹出防火墙提示时允许“专用网络”。手机页面支持单指旋转、双指缩放和平移、点击构件、长按区域、底部快捷操作和抽屉式属性面板。

## 2. 连接 CalculiX

先安装与电脑平台匹配的 CalculiX 2.23，然后设置可执行路径。

Windows PowerShell：

```powershell
$env:CCX_EXECUTABLE="C:\CalculiX\ccx_2.23.exe"
python scripts/run_lan.py
```

macOS 或 Linux：

```bash
export CCX_EXECUTABLE=/opt/calculix/ccx
python scripts/run_lan.py
```

打开网页后点击“检测 CalculiX”，状态为可用时即可运行工业示例。缺少 `ccx` 时，系统仍可生成和下载 `.inp`、执行静态检查、编辑 BSDL 和运行内置空间梁预览；壳、实体、接触、预应力和施工阶段不会由内置预览器伪算。

## 3. 安装 IFC 4.3 导入能力

```bash
python -m pip install -r requirements-ifc.txt
```

安装完成后重新启动服务，在网页中选择 IFC 文件上传。系统只在 IfcOpenShell 可用时启用实际 IFC 解析，并返回项目 MVD 和 ConversionReport。

## 4. 公网或实验室服务器部署

复制环境配置并设置密钥：

```bash
cp .env.example .env
```

把合法获得且具有执行权限的 `ccx` 放入 `solver/ccx`；Linux 执行：

```bash
chmod +x solver/ccx
docker compose up -d --build
```

访问 `http://服务器IP`。首次打开后，在左侧“服务器访问”输入 `.env` 中配置的一把 `BRIDGEMIND_API_KEYS` 密钥并点击连接；网页只在当前标签会话的 `sessionStorage` 保存密钥，关闭会话后需要重新输入。使用域名和 PWA 安装时，应在前置代理或云负载均衡启用 HTTPS。查看服务状态：

```bash
docker compose ps
curl http://服务器IP/api/health
curl http://服务器IP/api/calculix/status
```

## 5. 首次演示流程

进入工业示例项目，依次执行“验证模型→查看三维结构→查看/调整区域策略→检测 CalculiX→生成或运行 CalculiX→查看结果集→执行规则验算→查看 V1/V2 修订和审计日志”。若服务器没有 `ccx`，使用“导出 CalculiX”下载 `bridge_segment.inp`，在已安装 CalculiX 的工作站执行 `ccx -i bridge_segment`，再保留 DAT、FRD、OUT 和 LOG 作为项目证据。

## 6. 十分钟验证经验读回

先在一个训练项目中关闭“使用经验”并运行 Agent 策略，人工修改一个支座或突变区域，保存新修订，再从修改前后两个修订提取经验并把经验审核为 `accepted`。随后创建一个结构相似但项目 ID 和空间位置不同的新项目，先关闭“使用经验”运行控制组，再点击“读回预览”查看匹配，最后开启“使用经验”重新运行策略。若产品读回成功，新项目中的相应区域会改变网格动作、状态变为 `needs_review`，并在 `experienceRefs` 和 `memoryReadback` 中保留经验来源；若只保存了日志而没有进入读回链，控制组和实验组不会产生系统性差异。完整步骤见 `docs/BSDL_经验读回链_实操与验证.md`。

## 7. 常见故障

浏览器无法打开时，确认终端仍在运行并检查端口是否被占用；手机无法访问时，确认同一 Wi-Fi、局域网 IP 正确且防火墙允许 8000 端口；CalculiX 显示不可用时，检查 `CCX_EXECUTABLE` 是否指向真实文件且具有执行权限；IFC 上传提示依赖缺失时，安装 `requirements-ifc.txt`；公网 PWA 无法安装时，确认域名使用 HTTPS 且 Service Worker 没有被上级代理长期缓存。
