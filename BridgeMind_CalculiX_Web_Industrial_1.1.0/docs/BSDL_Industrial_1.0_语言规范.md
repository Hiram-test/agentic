# BSDL Industrial 1.0 桥梁统一结构描述语言规范

## 1. 定位

BSDL Industrial 1.0 是 BridgeMind 的规范化中间语言，用于在点云/BIM、三维结构认知、人工交互、有限元理想化、显式网格、CalculiX 求解、结果验证和经验复用之间维持稳定对象身份和可审计语义。语言文件采用 JSON 序列化，规范 Schema 为 `schema/bsdl-industrial.schema.json`，核心旧文档可通过确定性迁移器升级为 Industrial 1.0。

## 2. 顶层对象

| 对象 | 职责 |
|---|---|
| `project`、`revision`、`agents` | 项目身份、不可变修订、责任主体和状态 |
| `coordinateSystems`、`nodes` | 全局/局部坐标系和结构节点 |
| `materials`、`sections`、`shellSections`、`solidSections` | 材料、梁截面、壳厚度/铺层和实体材料区域 |
| `components` | 梁、杆、板、壳、实体、支座、节点构造和物理构件 |
| `connections` | 端点、局部坐标、DOF、刚接、铰接、弹簧、刚臂和物理/力学连接 |
| `loadCases`、`loads` | 荷载工况、组合引用和节点/线/面/体荷载 |
| `analysisTasks` | QoI、精度、计算预算和任务状态 |
| `cognitiveMap`、`regions`、`meshPolicies` | 局部结构特征、关键区域、网格等级、尺寸和 expert 决策 |
| `finiteElementModels` | 显式 FE 节点、单元、集合、表面、源对象映射和激活状态 |
| `contacts` | 主从表面、接触算法、法向行为、摩擦、滑移和阶段激活 |
| `prestressingSystems` | 预应力筋、张拉力/应力、损失、锚固、阶段和求解器表示 |
| `constructionStages` | 激活/移除构件、单元、接触、荷载、预应力和边界的顺序 |
| `solverProfiles`、`solverPlans` | 求解器版本能力、FE 模型、阶段、分析类型、增量和输出请求 |
| `artifacts`、`resultSets` | 输入、日志、DAT/FRD、结果字段、位置、单位和运行关联 |
| `codeCheckPlans`、`codeCheckResults` | 规则包、规范引用、需求、容量、利用率和逐条判定 |
| `feedback`、`experienceRefs` | 人工修改、计算反馈、前后状态、结论和经验引用 |
| `externalMappings`、`conversionReports` | IFC/外部系统 ID、对象分裂合并、单位转换、损失和阻断 |

## 3. 显式有限元模型

`finiteElementModels` 将语义模型与求解器离散分开。每个模型包含稳定 ID、坐标系、节点、单元、集合、表面和源对象引用；节点与单元使用字符串 ID，CalculiX Adapter 在导出时生成连续整数编号并写入 `.idmap.json`，结果回读通过该映射恢复 BSDL 身份。

当前 CalculiX 契约覆盖 `B31`、`B32`、`T3D2`、`S3`、`S4`、`S4R`、`C3D4`、`C3D6`、`C3D8`、`C3D8R`、`C3D10`、`C3D20`、`C3D20R`、`MASS` 和 `SPRINGA`。单元必须引用存在的节点，集合必须引用存在的 FE 对象，壳单元必须能解析壳截面，实体单元必须能解析材料，T3D2 必须有面积截面或等价参数。

## 4. 接触

`contacts` 至少记录 `masterSurfaceRef`、`slaveSurfaceRef`、法向行为、切向行为、摩擦系数、滑移选项、初始状态和阶段。几何相邻不自动升级为力学接触；主从表面必须来自显式 FE 表面。目标求解器不支持的安全关键接触语义在严格模式下阻断导出，非关键降级写入 ConversionReport。

## 5. 预应力

工业 FE 节点荷载同时保留结构语义目标和离散目标：`targetNodeRef` 指向结构节点，`attributes.finiteElementNodeRef` 可在特定网格中显式指向 FE 节点；后者属于任务/网格条件化映射，重网格后必须由 Adapter 或映射服务重新绑定并生成转换报告。

`prestressingSystems` 支持四种表示：`equivalent_load` 把有效预应力转换为确定性等效荷载；`truss_tendon` 使用 T3D2 筋单元；`initial_stress` 按单元和积分点写入初始应力；`solver_native` 使用求解器原生预紧截面和参考节点。每个系统记录初始力/应力、有效值、损失模型、张拉阶段、锚固区域、材料/截面和目标对象。任何缺少面积、材料、积分点或目标表面的原生表示都必须阻断或要求人工补全。

## 6. 施工阶段

`constructionStages` 以稳定顺序定义阶段 ID、时间、激活对象、移除对象、接触状态、荷载状态、预应力状态和阶段边界条件。阶段编译器把物理构件/集合解析到 FE 单元集合，并生成 CalculiX 多步 `*STEP` 与 `*MODEL CHANGE`。初始化步负责建立初始激活状态，后续阶段只输出状态变化，避免隐式默认造成不可重放模型。

## 7. 结果与证据

`resultSets` 通过 `runRef`、`artifactRefs`、`fields` 和 `summaries` 关联求解任务、DAT/FRD 文件和 BSDL 对象。结果字段至少记录物理量、位置、分量、单位、坐标系、工况/阶段和产物引用。当前 DAT 回读覆盖位移、反力、应力和应变摘要；FRD 保留为场结果产物。工程结论必须另有关联的平衡、收敛、网格、基准、监测或人工审批证据。

## 8. 规则验算

`codeCheckPlans` 绑定标准名称/版本、规则包版本、目标对象、输入参数和验收值；`codeCheckResults` 保存规则 ID、需求、容量、利用率、单位、判定、证据和计算引擎版本。规则表达式只允许白名单算术、比较、布尔、字典字段和纯函数，不允许任意脚本。内置 `generic.bridge` 只展示可审计机制，正式项目必须配置合法规则包并由责任工程师复核。

## 9. IFC 4.3 映射

`externalMappings` 保留 IFC `GlobalId`、实体类别、源文件和 BSDL 目标 ID；`conversionReports` 记录对象计数、MVD 问题、未映射属性、几何缺失、默认值、降级、不可逆损失和阻断状态。IFC 物理构件、结构分析项和 FE 模型保持分层，不能把同一个实体同时当作物理对象和 FE 单元复制使用。

## 10. 验证等级

- L1：JSON Schema、必填字段、类型和枚举通过。
- L2：稳定 ID、引用、单位和主层级通过。
- L3：连接、DOF、荷载、任务和网格策略工程规则通过。
- L4：工业 FE、集合/表面、接触、预应力、施工阶段、求解计划、结果和验算引用通过。

只有达到 L4 且 CalculiX deck 静态检查通过的文档才能进入严格工业执行；求解成功、数值收敛和工程验收属于后续证据，不由 Schema 自动保证。

## 11. 修订与人机闭环

每次 Agent 建议、人工区域增删、参数修改、FEA 反馈、规范验算和结果导入都保存为新修订；提交必须携带 `baseRevision`，过期提交返回冲突。修订内容使用 SHA-256 哈希，运行产物使用真实文件哈希，审计事件记录 actor、source、action、status、project、revision 和 details。经验提取器比较两个修订，将局部特征、人工动作、计算反馈、结果和适用边界写入经验库。
