# BSDL 经验读回链：实操、接口与验证

## 1. 这次版本真正补上的能力

BridgeMind Studio 1.1.0 把原来彼此分离的“修订记录—经验提取—模板管理—策略生成”接成了可执行读回链。基础大模型或规则专家的权重保持不变，产品通过外部程序记忆改变后续项目的策略条件：专家在训练项目中修改 `Region` 和 `MeshPolicy`，系统把修改前后状态、结构语义、任务条件和可选 FEA 指标编译为结构化经验；新项目生成规则策略后，系统检索跨项目经验，经过兼容性门槛、相似度和质量筛选，把合格经验聚合成待审核 BSDL 补丁。

完整数据流为：

`Revision Vn → Human/FEA Feedback → Experience Extractor → Experience Store → Memory Policy → Descriptor Matching → Proposed BSDL Patch → Human Review → FEA Verification → Revision Vn+1`

经验读回不会直接批准工程决策。所有被历史经验改变的区域统一进入 `needs_review`，并保存经验 ID、相似度、质量分、应用字段和策略模板版本。

## 2. 可迁移经验的数据结构

每条区域经验至少包含以下部分：

- `descriptor`：与项目本地 ID 和绝对坐标解耦的结构—任务描述符。
- `action`：专家最终采用的相对网格动作，例如 `targetSizeRatio`、`meshLevel`、`amrEngine` 和 `maxIterations`。
- `applicability`：适用分析类型、区域语义、单元族和任务边界。
- `evidence`：人工批准、FEA 指标、来源修订和可选运行 ID。
- `qualityScore`：用于读回门槛与动作聚合的经验质量分。
- `status`：`candidate`、`accepted`、`rejected` 或 `archived`。
- `review`：审核人、时间和说明。

当前描述符包含区域语义类型、几何类型、单元族、分析类型、QoI、荷载类型、节点连接度、支承状态、约束自由度模式、邻接构件类别、构件拓扑、材料数、截面面积比、局部尺度比和区域尺度比。具体 `targetRefs` 仍用于项目内追踪，但不进入跨项目相似度核心。

## 3. 安全门槛

经验匹配首先执行硬门槛：

1. `semanticType` 必须一致。
2. `elementFamily` 必须兼容；除非其中一方为 `auto`。
3. 默认要求历史与当前分析类型至少存在交集。
4. 经验状态必须属于策略允许集合。
5. 经验质量和结构相似度必须达到策略阈值。
6. 默认仅从其他项目读回经验，避免把同一项目自身记录误当成跨项目泛化。

通过硬门槛后，系统对任务、支承、节点度数、约束模式、构件类别、截面突变、局部尺度等字段进行加权评分。多个经验同时命中时，数值动作按“相似度 × 质量分”聚合，离散动作按带权众数选择。单次读回还受到最大网格等级变化、最大目标尺寸倍率和允许字段白名单限制。

默认策略由 `template.memory_policy` 管理，可版本化、设为默认并通过 API 指定。默认值包括：最低相似度 `0.62`、最低质量 `0.45`、每个区域最多匹配 3 条经验、仅跨项目读取、读回后状态为 `needs_review`。

## 4. 浏览器线性操作

### 4.1 专家 A 写入经验

1. 打开训练项目，关闭“使用经验”后运行“Agent 策略”，得到纯规则基线。
2. 选择一个 Agent 区域，修改目标尺寸、网格等级或其他允许参数。
3. 将确认后的区域标记为人工来源并保存新修订。
4. 必要时运行快速 FEA，把位移、内力、平衡残差和网格指标写回反馈修订。
5. 在两个修订之间执行“提取经验”。
6. 进入经验库检查 `status` 和 `qualityScore`；需要进入未来策略的经验应由人审核为 `accepted`。

### 4.2 新用户 B 读取经验

1. 创建一个未参与训练的新项目。
2. 先关闭“使用经验”，运行一次策略并记录控制组结果。
3. 点击“读回预览”，检查命中的经验、相似度、拟议动作和拒绝原因。
4. 开启“使用经验”，再次运行策略。
5. 查看被读回改变的区域；这些区域应显示 `needs_review`，并在属性中保留 `memoryReadback`。
6. 人工确认后再运行 FEA；只有验证通过的结果才进入下一修订或经验版本。

经验库中的“接受、拒绝、归档”会立即影响后续读回。被拒绝和归档的经验不会继续改变新项目。

## 5. API 示例

无副作用预览经验匹配：

```bash
curl -X POST http://127.0.0.1:8000/api/projects/project.test/memory/preview \
  -H "Content-Type: application/json" \
  -d '{"minSimilarity":0.65,"minQuality":0.60,"crossProjectOnly":true}'
```

生成规则策略并启用读回：

```bash
curl -X POST http://127.0.0.1:8000/api/projects/project.test/strategy \
  -H "Content-Type: application/json" \
  -d '{"commit":true,"useMemory":true,"memoryPolicyId":"template.memory_policy"}'
```

审核一条经验：

```bash
curl -X POST http://127.0.0.1:8000/api/experiences/experience.example/review \
  -H "Content-Type: application/json" \
  -d '{"status":"accepted","reviewer":"human.expert","comment":"跨项目回归验证通过"}'
```

关闭读回形成严格控制组：

```bash
curl -X POST http://127.0.0.1:8000/api/projects/project.test/strategy \
  -H "Content-Type: application/json" \
  -d '{"commit":false,"useMemory":false}'
```

## 6. 证明产品发生变化的 A/B 实验

训练阶段由专家 A 在若干项目中完成修订、FEA 验证和经验批准；测试阶段冻结代码、规则、基础模型和经验库，让未参与训练的新用户 B 处理严格留出的项目。

控制组使用相同系统但设置 `useMemory=false`，实验组设置 `useMemory=true`。至少比较：首次策略与专家最终策略的差异、人工增删区域数、参数修改幅度、完整求解次数、同资源预算下 QoI 误差、总耗时和错误迁移率。只有新用户 B 在实验组稳定受益，才能说明知识进入了产品；只有专家 A 自己变快，主要说明人在学习。

测试集应分为三层：同类结构插值、已知部件的新组合、未见物理机制。当前版本主要验证前两层的局部组合迁移，不宣称对接触、强非线性、整体稳定、施工阶段等新机制具有可靠零样本泛化。

## 7. 当前边界

- 经验相似度是确定性启发式，不是经大样本校准的概率。
- 读回只修改策略白名单字段，不自动改变材料、荷载、边界和结构拓扑。
- 历史经验只生成待审核补丁，不能替代后验误差估计、网格收敛和工程复核。
- 当前内置快速 FEA 只覆盖线弹性空间梁；工业 CalculiX 路径仍需目标环境原生验证。
- 负面经验目前通过 `rejected` 和适用性门槛阻断，尚未实现复杂反事实规则学习。
- 经验库随项目扩大后，需要进一步研究相似度校准、冲突消解、概念漂移和策略包发布机制。
