# BridgeMind CalculiX Web 1.1.0 + BSDL Industrial 1.0

BridgeMind CalculiX Web 是围绕“统一结构描述语言—三维结构认知—局部网格策略—人工交互—CalculiX 计算反馈—版本与经验沉淀”构建的可部署研究与工程原型。底层语言采用 BSDL Industrial 1.0，把桥梁物理构件、节点、杆件、面、实体、连接、材料、截面、约束、荷载、认知区域、网格策略、显式有限元模型、接触、预应力、施工阶段、求解计划、结果、验算证据、转换报告和修订记录组织在同一条可追溯数据链中。

1.1.0 补齐了经验读回链：专家修订可以从两个 BSDL Revision 中提取为结构化 Experience，经过状态、质量、任务兼容性和跨项目结构相似度筛选后，读回为新项目的待审核 Region/MeshPolicy 补丁。基础模型权重保持不变，产品通过版本化外部程序记忆改变后续策略；所有读回动作均标记为 `needs_review`，保留来源经验和匹配证据，并可通过人工拒绝、接受或归档控制未来使用。

## 当前交付能力

| 能力 | 实现状态 | 主要入口 |
|---|---|---|
| 桥梁统一结构描述 | 已实现 | `schema/bsdl-industrial.schema.json`、`docs/BSDL_Industrial_1.0_语言规范.md` |
| 三维结构与移动触控 | 已实现 | `web/`，支持单指旋转、双指平移/缩放、点击和长按选择 |
| PWA 网站 | 已实现 | `web/manifest.webmanifest`、`web/service-worker.js` |
| 多专家区域网格策略 | 已实现 | `bridge_mind/cognition/` |
| 人工区域修改、版本、审计和经验 | 已实现 | `bridge_mind/repository.py`、`bridge_mind/experience.py` |
| 跨项目经验读回与策略补丁 | 已实现 | `bridge_mind/memory.py`、`/memory/preview`、`/experiences/{id}/review` |
| 内置空间梁快速预览 | 已实现 | `bridge_mind/fea/frame3d.py`，只用于线弹性梁系预览 |
| 壳、实体和混合 FE 模型 | 已实现语言、验证、CalculiX 导出 | S3/S4/S4R、C3D4/C3D6/C3D8/C3D8R/C3D10/C3D20/C3D20R |
| 非线性与摩擦接触 | 已实现语言、验证、CalculiX 关键字映射 | `contacts`、`*SURFACE INTERACTION`、`*CONTACT PAIR` |
| 预应力 | 已实现四种契约 | 等效荷载、T3D2 筋、初始应力、`*PRE-TENSION SECTION` |
| 施工阶段 | 已实现语言、阶段编译和 CalculiX 映射 | `constructionStages`、`*MODEL CHANGE`、多 `*STEP` |
| CalculiX 作业执行 | 已实现 | `ccx -i`、超时、线程、日志、SHA-256、DAT/FRD 产物链 |
| CalculiX 结果回写 | 已实现 | DAT 位移、反力、应力、应变摘要写回 `resultSets` |
| 规范验算框架 | 已实现 | 版本化规则包、安全表达式、逐条结果和审计修订 |
| IFC 4.3/MVD 导入 | 已实现可选 Adapter | 依赖 IfcOpenShell，带项目 MVD 检查与转换报告 |
| 公网单节点部署 | 已实现 | Docker、Compose、Nginx、API 密钥、健康检查、持久化卷 |

## 五分钟启动

安装 Python 3.11 或更高版本，在项目根目录执行：

```bash
python -m pip install -r requirements.txt
python scripts/run_lan.py
```

电脑打开 `http://127.0.0.1:8000`；手机与电脑连接同一 Wi-Fi 后，打开终端打印的局域网地址。Windows 首次启动可能需要允许 Python 通过专用网络防火墙。

本机已安装 CalculiX 时，将 `CCX_EXECUTABLE` 指向 `ccx` 后重新启动网站；未安装时，网站仍可完成语言编辑、策略生成、验证、deck 生成和静态检查，并在能力面板中明确显示原生求解不可用。

## Docker 部署

```bash
cp .env.example .env
# 把合法获得、适配服务器平台并具有执行权限的 CalculiX 2.23 文件放到 solver/ccx
docker compose up -d --build
```

默认通过服务器 80 端口访问。公网 PWA 需要 HTTPS；可在本栈前部署云负载均衡、Caddy、Traefik 或配置证书的上级 Nginx。生产环境必须设置高强度 `BRIDGEMIND_API_KEYS`。网站左侧“服务器访问”区域可在当前浏览器会话保存密钥，后续受保护请求会自动携带 `X-API-Key`；密钥不会写入项目、日志或持久化 `localStorage`。

## CalculiX 工业示例

工业示例位于 `examples/calculix_industrial_bridge_segment.bsdl.json`，包含 33 个 FE 节点、16 个单元、S4R 壳、C3D8R 实体、T3D2 预应力筋、一个摩擦接触和四个施工阶段。对应输入文件位于 `runs/industrial_demo/bridge_segment.inp`；另外两个预应力契约夹具分别位于 `runs/industrial_demo/prestress_initial_stress.inp` 和 `runs/industrial_demo/prestress_solver_native.inp`。

执行验证和导出：

```bash
python -m bridge_mind.cli validate examples/calculix_industrial_bridge_segment.bsdl.json
python -m bridge_mind.cli export-calculix examples/calculix_industrial_bridge_segment.bsdl.json --output runs/manual_bridge_segment.inp
```

通过 API 执行原生作业：

```bash
curl -X POST http://127.0.0.1:8000/api/projects/project.calculix_industrial_bridge_segment/calculix/run \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $BRIDGEMIND_CLIENT_KEY" \
  -d '{"solverPlanId":"solver.calculix.industrial","strict":true,"threads":4,"commitResult":true}'
```

## IFC 4.3 导入

```bash
python -m pip install -r requirements-ifc.txt
```

安装后可在网页上传 `.ifc`，系统会执行 Schema 前缀、桥梁根对象、GlobalId、放置、表示、空间分解及物理—分析关联等项目交付约束检查，保留 IFC GlobalId，并输出逐对象映射与损失报告。该 MVD 是项目级交付 Profile，不构成 buildingSMART 官方 MVD 认证。

## 工程边界

交付环境中没有安装或运行原生 `ccx`，因此自动化测试验证的是 BSDL→CalculiX 输入生成、静态检查、受控子进程、日志与产物哈希、DAT 回读和结果写回契约；原生数值正确性仍需要在目标服务器的 CalculiX 2.23 上运行项目基准算例、网格收敛、平衡检查和工程复核。通用规则包是可审计计算示例，不包含受版权保护的正式规范条文，也不能单独形成工程符合性结论。IFC 项目 MVD、接触、预应力与施工阶段映射均需针对实际项目约定和求解器版本执行 conformance tests。

## 主要文档

- `QUICK_START.md`：本机、手机、CalculiX 和 Docker 快速启动。
- `docs/BSDL_Industrial_1.0_语言规范.md`：工业语言对象、引用和验证规则。
- `docs/CalculiX_工业实现说明.md`：元素、接触、预应力、阶段、运行与结果回读。
- `docs/移动端与公网部署.md`：触控、PWA、API 密钥和生产部署。
- `docs/IFC43_MVD映射与边界.md`：IFC 4.3 导入、项目 MVD 和损失报告。
- `docs/能力边界与验证声明.md`：已验证能力、未验证项和工程采用条件。
- `docs/BSDL_经验读回链_实操与验证.md`：经验写入、读回、安全门槛、API 和新用户 A/B 验证。
- `docs/会议设想_工业实现追踪矩阵.md`：老师设想与代码、界面、测试的逐项对应。
- `SELF_CHECK_REPORT.md`：最终测试、示例验证和环境状态。

## 目录

```text
bridge_mind/   Python API、版本库、认知专家、经验读回、FEA、IFC、CalculiX 和规则引擎
web/           响应式触控 PWA
schema/        BSDL Core 0.1 与 Industrial 1.0 JSON Schema
rules/         语言规则和版本化验算规则包
mvd/           IFC 4.3 项目交付 Profile
examples/      核心示例、工业示例和预应力夹具
runs/          可审计输入、日志、结果和转换报告
Dockerfile     非特权单节点应用镜像
docker-compose.yml  应用、Nginx 和持久化卷编排
```

本项目采用 MIT 许可；外部 CalculiX、IfcOpenShell、IFC 标准内容和工程规范分别受其自身许可、标准治理和使用条件约束。
