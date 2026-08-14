# BSDL 桥梁统一结构描述语言规范 v0.1.0

> 本文是 BSDL Core 0.1 历史基线；当前工业主规范见 `BSDL_Industrial_1.0_语言规范.md`。


## 1. 定位

BSDL 是 BridgeMind Studio 的底层结构语义语言，用统一、可计算、可修改的 JSON 表达桥梁及其局部结构。它以节点、构件、连接、原点/坐标系和区域为基本词汇，并显式携带几何、材料、截面、约束、荷载、任务和网格策略。它解决的是“机器如何看到并理解一个三维结构，然后把局部认知转成有限元建模决策”的问题。

BSDL 不把某个求解器输入文件当作结构真相源，也不要求把所有节点单元和结果数组写入同一 JSON。几何、网格和结果大文件可以作为 artifact 外置，BSDL 保存稳定 ID、选择范围、坐标和语义关系。

## 2. 设计原则

1. 结构对象以稳定 ID 标识，节点、构件、连接和区域不得依赖数组序号建立永久关系。
2. 桥梁可以逐级分解为桥、跨、构件、局部节点、杆件、面和实体区域，但任何对象只在一个主层级中拥有。
3. 几何接触、物理连接和力学连接分开表达，几何相交不能自动视为传力关系。
4. 三维区域是网格决策和人机交互的一等对象，每个区域记录来源、类型、目标对象、参数、理由、置信度、状态和版本。
5. Agent 建议、人工修改和 FEA 反馈必须分源保存，允许比较、回滚和经验提取。
6. 多专家系统只提交结构化建议，网格生成、求解和数值检查由确定性程序执行。
7. 局部认知地图保存关键特征与决策关系，不要求在每次推理时调用完整全局状态。
8. 当前规范以 SI 为计算基准，显示层可以换算单位，但求解前必须规范化。

## 3. 根文档

根对象字段包括 `language`、`languageVersion`、`documentId`、`revision`、`project`、`units`、`coordinateSystems`、`agents`、`materials`、`sections`、`nodes`、`components`、`connections`、`loadCases`、`loads`、`analysisTasks`、`cognitiveMap`、`regions`、`meshPolicies`、`solverPlans`、`feedback`、`artifacts`、`experienceRefs` 和 `extensions`。

`language` 固定为 `Bridge-Structural-Description-Language`，`languageVersion` 固定为 `0.1.0`。规范化文件扩展名建议为 `.bsdl.json`。

## 4. 基础结构对象

### 4.1 Node

`Node` 表示结构拓扑中的点，可以是几何端点、连接节点、支承点、加载点、传感点或局部认知地标。必须给出三维坐标和坐标系引用，可选保存六自由度约束、标签和来源。

### 4.2 Component

`Component` 表示桥梁构件或基本结构块。`category` 的最小词汇包括 bridge、span、deck、girder、crossbeam、diaphragm、stiffener、rib、pier、column、bearing、foundation、joint、rod、surface、solid_region 和 other。`topology` 为 point、line、surface 或 solid。线构件通过 `nodeRefs` 指定端点；面和实体可使用内联代理几何或外部 artifact。

承载构件应引用材料，线构件还应引用截面。`analysis.elementType` 可以声明 frame3d、truss3d、shell、solid 或 excluded。当前内置求解器实现 frame3d。

### 4.3 Connection

`Connection` 将多个构件、节点或接口区域对象化连接。连接类型包括 shared_node、rigid、pinned、spring、bearing、contact、tie、offset 和 other。连接可带参与对象、局部坐标、六自由度关系、刚度和间隙参数。

### 4.4 Material 与 Section

`Material` 至少定义密度、弹性模量和泊松比，可选定义剪切模量、热膨胀系数和强度。`Section` 至少定义面积、两个主惯性矩和扭转常数；这些参数直接进入内置梁系求解器。

## 5. 三维区域与网格策略

`Region` 用三维包围盒、球、圆柱或对象选择器表达局部区域。最小类型包括 support、joint、discontinuity、smooth、hotspot、boundary、user_defined。`source` 区分 agent、human、fea、imported。区域具有 active、meshLevel、targetSize、elementFamily、amrEngine、maxIterations、reason、confidence 和 status。

`MeshPolicy` 保存全局基准尺寸、元素族、计算预算和区域覆盖表。区域优先级由 support/joint/discontinuity/hotspot/smooth 顺序、人工覆盖和计算证据综合决定。多个 expert 对同一区域提出意见时，融合器保留原始提案并输出一个合并区域，不覆盖来源证据。

## 6. 有限元认知地图

`CognitiveMap.landmarks` 保存局部关键点或结构块及其特征向量，例如节点度数、支承状态、构件夹角、截面比、材料差异、曲率代理、长度尺度和 FEA 响应指标。`decisionEdges` 保存从某类特征到某类建模动作的条件关系，例如“支承节点且连接度大于二时，建立高优先级局部加密区”。

认知地图的最小单位是局部地标与决策边，不要求复制完整网格或全桥状态。项目经验可通过 feature signature 检索相似地标，并作为后续策略生成的先验。

## 7. 多专家策略

系统默认包含六类 expert：

- GlobalAllocator：估计结构尺度、预算和全局基准尺寸。
- SupportJointExpert：识别支承、连接度异常和构件交汇节点。
- DiscontinuityExpert：识别截面、材料、方向和拓扑突变。
- SmoothRegionExpert：识别长而连续的平滑区并提出可放松区域。
- FEAHotspotExpert：根据位移、端力和响应梯度生成反馈区域。
- HumanOverrideExpert：把人工新增、删除和参数修改作为最高优先级约束。

专家输出统一的 `RegionProposal`，包括三维范围、目标、参数、理由、置信度和证据引用。FusionEngine 负责去重、合并、优先级裁决和预算归一化。

## 8. 快速 FEA 与反馈

内置求解器使用空间 Euler–Bernoulli 梁单元，每节点六自由度，支持线弹性材料、通用截面、节点力/矩和节点约束。求解输出节点位移、支反力、单元局部端力、最大位移和最大内力指标。求解器会检查零长度构件、材料与截面缺失、刚度矩阵奇异和未约束刚体模态。

FEA 反馈以 `Feedback` 对象保存，并可生成 source=fea 的 hotspot 区域。计算反馈只说明当前模型和当前任务下的响应，不自动证明真实结构结论。

## 9. 修订、Patch 与经验

每次保存形成不可变修订，包含 parentRevision、author、source、summary、时间和完整文档快照。人工拖动区域、删除区域、修改网格参数或批准建议均应形成反馈记录。系统可比较两个修订，把对象级新增、删除和字段变化转换为经验条目，保存局部特征、原策略、新策略、修改理由和计算结果。

经验模板具有版本和默认状态。系统可以把多个项目的经验按结构类型、地标类型、构件类别和 feature signature 检索，生成下一版策略提示模板；本版本使用确定性摘要器，同时保留外接大模型的接口。

## 10. 上游与下游 Adapter

上游 Adapter 包括 BSDL JSON、XYZ/CSV 点云和可插拔 IFC/BIM。点云流程完成读取、体素降采样、DBSCAN 分割、主方向分析、包围盒和 line/surface/solid 代理分类。下游 Adapter 包括内置 frame3d、CalculiX B31 输入导出和 Gmsh 线网格脚本导出。

每个 Adapter 应返回 capability、warnings、losses 和 artifact 路径。未知安全关键属性不得静默忽略。

## 11. 合法性层级

- L0：JSON Schema 结构有效。
- L1：ID、引用和坐标有效。
- L2：拓扑、材料、截面和连接有效。
- L3：任务、荷载、约束和求解条件有效。
- L4：区域和网格策略覆盖有效。
- L5：求解完成并产生反馈证据。
- L6：人工批准、版本可重放和经验可检索。

实现不得把“Schema 通过”“求解成功”和“工程结论可信”视为同一状态。
