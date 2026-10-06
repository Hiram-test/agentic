# 03 Gmsh调用、编号映射与加密网格

## 为什么不能直接重新划一个“看起来一样”的模型

本模型已包含逐单元初应力、逐节点荷载、支承以及后处理分组。网格一改，这些编号就可能失效。只导出一个Gmsh Abaqus网格没有材料、初应力、载荷历史等完整计算语义，不能直接替换本INP。

默认流程使用Gmsh**重新生成与原始线网完全相同的一阶一维网格**，以验证几何/拓扑和实现可视化交换；验证后计算仍使用完整原INP。因此这是完整的“几何建网—一致性验证—保留物理卡片求解”路径，不是丢弃物理信息的网格替换。

## 实际API顺序

```python
import gmsh
gmsh.initialize()
gmsh.model.add('catwalk_static')
# nodes: {原节点ID: [X,Y,Z]}；单位为mm
for nid, xyz in nodes.items():
    gmsh.model.geo.addPoint(*xyz, 0, nid)
# elements: {原单元ID: {'nodes':[起点ID,终点ID], ...}}
for eid, el in elements.items():
    gmsh.model.geo.addLine(*el['nodes'], eid)
gmsh.model.geo.synchronize()
for eid in elements:
    gmsh.model.mesh.setTransfiniteCurve(eid, 2)
# 为E_SEC1/2/3建立一维PhysicalGroup，组内是原线实体ID
# gmsh.model.addPhysicalGroup(1, element_ids, physical_id)
# gmsh.model.setPhysicalName(1, physical_id, 'E_SEC1')
gmsh.option.setNumber('Mesh.ElementOrder', 1)
gmsh.option.setNumber('Mesh.MshFileVersion', 4.1)
gmsh.model.mesh.generate(1)
gmsh.write('catwalk.msh')
gmsh.finalize()
```

完整、已连接到输入解析的实现是 `scripts/mesh_gmsh.py`，不要让AI从示例自行拼出另一个未验证版本。二维结构的杆件用 `generate(1)`，不是 `generate(2)`；平面结构不等于平面实体网格。

## 映射与验证

几何Point Tag、Gmsh Mesh Node Tag、INP Node ID是不同命名空间；Line Tag、Mesh Element Tag、INP Element ID同理。即使本流程令Point/Line Tag等于原ID，也不能假定生成的Mesh Tag相同。

本脚本逐个读取 `getNodes(0, nid)`，得到几何点对应的唯一网格节点，再建立 `gmsh_node_to_inp_node`。逐线读取 `getElements(1, eid)`，建立 `inp_element_to_gmsh_elements`。

默认每线两个节点（一段）：

- 必须1125个网格节点、1194个一阶线单元，Gmsh类型1。
- 每原始节点位置误差≤1e-7 mm。
- 每单元两个端点经过映射后必须与原INP**同一顺序**一致。
- 不做`removeAllDuplicates()`、`removeDuplicateNodes()`或OCC布尔合并；相近/相同坐标不自动意味着物理连接。
- 物理组表示截面归属，不能把它当成材料、边界或荷载的完整定义。

输出 `mesh/catwalk.msh`、`catwalk.geo_unrolled`、`mesh_map.json`。后者记录Gmsh版本、映射、误差和是否可用于本原件复算路径。

独立调用：

```bash
python scripts/mesh_gmsh.py --inp assets/inputs/migrate_P1.inp --out /new/mesh
```

## 可选加密：只生成候选网格，不自动求解

```bash
python scripts/mesh_gmsh.py --inp assets/inputs/migrate_P1.inp --out /new/refined-mesh --subdivisions 2
```

每条原线分成2段，原节点仍保留，但中间节点和新单元没有原始物理卡片；输出明确标记 `refined_mesh_is_unsolved_candidate=true`。不得拿该结果宣称完成网格收敛分析。

若任务明确要求加密计算，应另写派生INP转换器，并完成以下工作后才能求解：

1. 保留所有锚点、转折点、荷载点、门架节点及重合但不同拓扑的点，生成新旧节点/单元对应表。
2. 每个子单元继承父单元材料、截面及B31方向向量；不能把B31改成无弯曲杆。
3. 初始应力按父单元物理状态映射到子单元积分点；弦线方向改变时重新处理全局张量，不能仅拷贝Sxx。
4. 原节点集中力保留在原物理位置。由分布荷载离散来的节点力如需重离散，要用原线荷载重新积分，不能将原节点力简单复制到新节点造成总力翻倍。
5. 检查各步总力与关于同一原点的总力矩守恒；继承二期恒载的总量语义。
6. 处理重力、温度集合和B31内部扩展节点温度；新节点边界只按物理约束赋值。
7. 扩展N_MCT输出集合、8个跨度分组及单元应力输出，不许遗漏新增单元。
8. 生成独立manifest、audit，执行恒载平衡、反力核对与六工况回归，再比较网格1/2/4分段时位移、索力变化。

此加密转换器不属于本次交付的已验证自动运行路径。用户要求原INP复核时直接使用默认一段路径，不制造不必要的新模型。
