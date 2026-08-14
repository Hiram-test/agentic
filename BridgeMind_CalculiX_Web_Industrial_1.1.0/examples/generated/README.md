# 预生成的完整闭环样例

本目录保存双主梁桥从 V1 初始 BSDL 到 V2 多专家区域策略、快速空间梁 FEA 结果以及 V3 FEA 热点反馈的预生成产物，用于在不启动数据库和 Web 服务时检查语言对象、认知地图、网格策略、数值结果及反馈区域之间的对应关系。示例中的结构、荷载和计算结果均为软件功能验证数据，不能用于真实桥梁设计、安全评估或规范验算。

- `two_girder_bridge_V2_strategy.bsdl.json`：全局分配器与局部 experts 生成的区域策略和认知地图。
- `two_girder_bridge_V2_fea_result.json`：内置 3D Euler–Bernoulli 梁单元快速试算结果。
- `two_girder_bridge_V3_feedback.bsdl.json`：根据构件响应形成 FEA 热点区域后的文档。
- `two_girder_bridge_strategy_reports.json`：两轮策略报告与 BSDL 验证结果。
