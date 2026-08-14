# IFC 4.3、项目 MVD 与 BSDL 映射

## 1. 实现入口

IFC 导入位于 `bridge_mind/importers/ifc.py`，解析依赖可选 IfcOpenShell；项目交付 Profile 位于 `mvd/bridge_analysis_delivery_view.json`。网页和 API 接受 `.ifc`、`.ifczip` 和 `.ifcxml` 文件，但实际可解析格式取决于部署环境中的 IfcOpenShell 构建。

## 2. 项目 MVD

Profile 要求 IFC4X3 Schema 前缀、`IfcProject` 和 `IfcBridge`，推荐 `IfcSite`、`IfcBridgePart` 和 `IfcAlignment`；检查 GlobalId、放置、表示、空间分解、单位、地理引用及物理—分析关联。它用于本项目导入前的可执行约束和报告，不是 buildingSMART 发布或认证的正式 MVD，因此 `certificationClaim` 固定为 false。

## 3. 物理对象映射

`IfcBridge` 和 `IfcBridgePart` 建立项目/桥梁空间身份；`IfcBeam`、`IfcMember`、`IfcSlab`、`IfcPlate`、`IfcColumn`、`IfcPile`、`IfcBearing`、`IfcFooting`、`IfcWall`、`IfcTendon`、`IfcReinforcingBar` 和受控 `IfcBuildingElementProxy` 映射为 BSDL 物理构件。IFC `GlobalId` 写入 `externalMappings`，名称、对象类型、放置和可用表示作为结构属性或 artifact 引用保留。

## 4. 分析对象映射

`IfcStructuralCurveMember`、`IfcStructuralSurfaceMember` 和结构连接可映射为分析构件、连接和约束候选；`IfcRelAssignsToProduct` 用于建立物理—分析来源关系。IFC Structural Analysis Domain 不包含完整 FE 节点/单元网格和详细场结果，因此导入器不会把 IFC 结构分析项伪装为已完成的 CalculiX 模型；显式 `finiteElementModels` 必须由确定性网格器、外部 Adapter 或人工确认生成。

## 5. 几何与坐标

导入器保留对象放置和源表示标识，复杂 B-Rep、扫掠、Alignment 和地理参考按 artifact/外部映射管理。几何抽取失败、坐标转换不完整、单位不确定或源对象没有表示时写入 ConversionReport；安全关键尺寸在确认前不得用于自动生成求解模型。

## 6. 转换报告

每次导入返回 Profile 版本、Schema 状态、对象数量、已映射类别、GlobalId→BSDL ID、警告、损失和阻断项。常见损失包括自定义 PropertySet、参数公式、复杂连接语义、阶段、预应力细节、局部坐标、材料本构和软件专属扩展。未知安全关键语义阻断后续工业执行，非关键属性可作为命名空间扩展透传。

## 7. 项目采用条件

工业项目应绑定明确 IFC 4.3 补丁版本、交付 MVD、坐标/单位约定、属性字典、对象分类、几何精度、源软件版本和 round-trip fixture；使用实际桥梁 IFC 文件建立 conformance suite，并统计对象保持率、GlobalId 保持率、坐标偏差、未映射属性和不可逆损失。只有通过项目级互操作测试后，才可将 IFC 导入作为生产模型来源。
