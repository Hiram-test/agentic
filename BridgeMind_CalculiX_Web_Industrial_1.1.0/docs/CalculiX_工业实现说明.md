# CalculiX 2.23 工业实现说明

## 1. 执行链

工业链路为 `BSDL Industrial 1.0 → 完整验证 → FE 模型选择/兼容网格生成 → 连续编号与 ID Map → CalculiX deck → 静态检查 → ccx -i → OUT/LOG/DAT/FRD → SHA-256 产物清单 → DAT 回读 → ResultSet → 新 BSDL 修订`。严格模式下，安全关键语义缺失、引用错误、未知单元、无法映射的接触/预应力或非法阶段会阻断导出或执行。

## 2. 单元和截面

Adapter 按单元类型分组输出 `*ELEMENT`，按材料和截面组合生成专用 ELSET。梁单元映射 `*BEAM SECTION`，桁架/预应力筋映射 `*SOLID SECTION` 或对应面积契约，壳单元映射 `*SHELL SECTION`，实体单元映射 `*SOLID SECTION`。BSDL 字符串 ID 只存在于语义层，导出整数编号保存在 `.idmap.json`，保证重网格和结果回读时仍可追溯。

## 3. 材料与非线性

当前导出支持线弹性材料的 `*ELASTIC` 和密度；BSDL 可保存塑性、徐变和松弛对象，Adapter 只对已经定义且能够确定映射的数据输出相应关键字，无法确定的本构在严格模式下阻断。`solverPlans.settings.nlgeom` 控制 `*STEP, NLGEOM=YES/NO`；非线性收敛仍由 CalculiX 实际运行、增量历史和日志判定。

### 3.1 荷载映射

节点荷载保留结构层 `targetNodeRef`，并允许在 `attributes.finiteElementNodeRef` 中显式指定当前 FE 模型节点；Adapter 优先采用显式 FE 引用，再按 `FE node.sourceRef` 回查结构节点。自重通过目标单元集输出 `*DLOAD, GRAV`，表面压力通过 `attributes.surfaceRef` 和 `attributes.pressure` 输出 `*DSLOAD`。任何未映射的非零荷载都会进入 ConversionReport；严格项目应消除这些损失后再执行。

## 4. 接触

接触对象生成 FE 表面、`*SURFACE INTERACTION`、法向接触行为、摩擦参数和 `*CONTACT PAIR`。阶段变化通过 `*MODEL CHANGE, TYPE=CONTACT PAIR, ADD/REMOVE` 表达，数据行保持从属面在前、主表面在后。接触初始穿透、主从面网格密度、法向方向和摩擦收敛必须在项目基准中验证；静态 linter 只能检查关键字、引用和结构，不能证明非线性收敛。

## 5. 预应力

- `equivalent_load`：预应力损失模块计算有效力并转换为端部等效节点荷载，适合快速或高层模型。
- `truss_tendon`：使用 T3D2 筋单元、材料和面积表达筋束。
- `initial_stress`：在首个 `*STEP` 前输出 `*INITIAL CONDITIONS, TYPE=STRESS`，按元素与积分点写入全局应力分量。
- `solver_native`：输出 `*PRE-TENSION SECTION`，生成独立参考节点，并在阶段中对参考节点自由度 1 施加预紧力或位移。

`initial_stress` 和 `solver_native` 分别配有可验证 deck 夹具；它们是 Adapter 契约示例，实际桥梁张拉、摩阻、锚具回缩、弹性压缩、徐变、收缩和松弛参数必须由项目数据和合法规则提供。

## 6. 施工阶段

Adapter 先构造初始化步，将初始不参与结构的扩展单元和接触移除；随后按 `constructionStages.order` 生成多步静力分析，使用 `*MODEL CHANGE, TYPE=ELEMENT, ADD=STRAIN FREE/REMOVE` 和接触对状态变化，并在对应阶段启用荷载与预应力。每一步保留名称、NLGEOM、时间增量和输出请求。复杂时间依赖材料、临时结构、分步边界释放和重启动策略需要在实际项目配置中进一步明确。

## 7. 作业控制

`run_ccx` 使用受控子进程执行 `[ccx, -i, job_stem]`，设置 `OMP_NUM_THREADS` 和 `CCX_NPROC_RESULTS`，限制 1—86400 秒超时，保存标准输出与错误，扫描 `*ERROR`，并对 INP、DAT、FRD、STA、CVG、12D、EIG、OUT、LOG 计算真实 SHA-256。`/api/calculix/status` 只报告实际可执行文件状态；缺少 `ccx` 返回 `unavailable`，不会伪造成功。

## 8. 结果回读

DAT 解析器识别位移、反力、应力和应变表，生成数量、最大幅值和分量摘要；成功作业的输入、输出、日志和结果场作为 `artifacts` 写入新修订，`resultSets` 通过 `runRef` 与运行记录关联。FRD 当前作为完整场产物保留，网页可继续扩展 FRD 云图解析器；在该扩展完成前，DAT 摘要和原始 FRD 均应保留。

## 9. 静态检查

Deck linter 检查节点/单元计数、重复编号、未知节点引用、关键字白名单、STEP/END STEP 配对、材料/截面/集合/表面和阶段关键字。linter 通过只表示输入结构满足已编码契约；它不能替代 CalculiX 解析、求解收敛、单元质量、接触稳定性、能量平衡、网格收敛和工程审查。

## 10. 当前验证声明

本交付环境没有原生 CalculiX 二进制，故没有声称完成 CalculiX 2.23 原生数值认证。自动测试使用行为可控的 `ccx` 测试替身验证进程参数、工作目录、DAT/FRD 产物、日志、哈希、解析和 BSDL 结果提交；三个工业 deck 通过语言 L4 验证和静态检查。部署到目标服务器后，应增加官方/项目基准算例、单元补丁测试、接触与阶段最小模型、预应力解析解、反力平衡、网格收敛和双版本回归测试。
