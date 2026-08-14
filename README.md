# BridgeMind BSDL Experience Readback 1.1.0

本仓库保存 BridgeMind CalculiX Web Industrial 的可复现发布包。1.1.0 已接通 BSDL 经验读回链：从 Revision、Feedback 与 FEA 证据提取结构化 Experience，在新项目中执行兼容性过滤和相似度检索，生成保持 `needs_review` 状态的候选 BSDL Patch，并记录来源经验、适用边界和审批状态。

## 下载

- `BridgeMind_CalculiX_Web_Industrial_1.1.0.zip`：经验读回链完整包。
- `BridgeMind_CalculiX_Web_Industrial_1.0.0.zip`：原始工业版基线。
- `SHA256SUMS.txt`：1.1.0 发布包完整性哈希。

## 已验证

GitHub Actions 从 1.0.0 基线重建源码，执行 30 项自动化测试、8 项产品自检、Python 编译检查、JavaScript 语法检查和 ZIP 完整性检查。跨项目测试使用不同项目 ID 与平移坐标，确认被批准的支座经验会改变新项目策略，同时不兼容分析类型会被读回门阻断。

## 能力边界

本版本没有在 CI 中执行原生 CalculiX、解析真实 IFC 或构建 Docker 镜像；相关接口和工业工件仍保留在包内，不能把静态与夹具验收扩写成这些外部环境已经完成实测。
