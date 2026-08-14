"""把 IFC 4.3 桥梁物理对象和结构分析对象映射到 BSDL Industrial。"""  # 说明模块用途。
from __future__ import annotations  # 启用延迟类型注解。
import hashlib  # 提供稳定短 ID 哈希。
import importlib.util  # 提供可选依赖检测。
from pathlib import Path  # 提供 IFC 文件路径处理。
from typing import Any  # 提供通用返回类型注解。
from ..industrial.document import new_document  # 复用工业文档工厂。
from ..industrial.mvd import load_profile, validate_ifc_model  # 复用 MVD 检查器。
from ..utils import content_hash, utc_now  # 复用内容哈希和时间戳。

ROOT = Path(__file__).resolve().parents[2]  # 获取项目根目录。
DEFAULT_MVD = ROOT / "mvd" / "bridge_analysis_delivery_view.json"  # 指定默认桥梁分析交付视图。

_TYPE_MAPPING: dict[str, tuple[str, str, str]] = {"IfcBeam": ("girder", "line", "frame3d"), "IfcMember": ("rod", "line", "frame3d"), "IfcColumn": ("column", "line", "frame3d"), "IfcPile": ("foundation", "line", "frame3d"), "IfcSlab": ("deck", "surface", "shell"), "IfcPlate": ("surface", "surface", "shell"), "IfcWall": ("surface", "surface", "shell"), "IfcFooting": ("foundation", "solid", "solid"), "IfcBearing": ("bearing", "point", "excluded"), "IfcTendon": ("rod", "line", "truss3d"), "IfcReinforcingBar": ("rod", "line", "truss3d"), "IfcBuildingElementProxy": ("other", "solid", "excluded"), "IfcBridgePart": ("span", "solid", "excluded"), "IfcBridge": ("bridge", "solid", "excluded")}  # 定义 IFC 类到 BSDL 基础语义的映射。


def capability() -> dict[str, Any]:  # 检测当前运行环境是否具备 IfcOpenShell。
    available = importlib.util.find_spec("ifcopenshell") is not None  # 检测 IfcOpenShell 包。
    if not available:  # 处理可选依赖缺失。
        return {"available": False, "adapter": "ifcopenshell", "version": None, "message": "未安装 ifcopenshell；可执行 pip install -e .[ifc] 后启用 IFC 4.3 导入和导出。", "mvdProfile": str(DEFAULT_MVD)}  # 返回明确能力状态。
    import ifcopenshell  # type: ignore  # 在确认存在后导入 IFC 解析库。
    return {"available": True, "adapter": "ifcopenshell", "version": str(getattr(ifcopenshell, "version", "unknown")), "message": "IFC 4.3 Adapter 可用。", "mvdProfile": str(DEFAULT_MVD)}  # 返回可用状态。


def _safe_token(value: str, prefix: str) -> str:  # 把 IFC GlobalId 或 STEP ID 转换为 BSDL 合法 ID。
    cleaned = "".join(character if character.isalnum() else "." for character in value).strip(".")  # 清理不兼容字符。
    if not cleaned:  # 检查清理后是否为空。
        cleaned = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]  # 使用哈希生成稳定后缀。
    return f"{prefix}.{cleaned[:96]}"  # 返回满足长度限制的稳定 ID。


def _entity_type(entity: Any) -> str:  # 读取 IFC 实体类型名称。
    return str(entity.is_a()) if hasattr(entity, "is_a") else type(entity).__name__  # 返回 IfcOpenShell 类型或 Python 类型。


def _entity_key(entity: Any) -> str:  # 读取实体稳定身份用于 BSDL ID。
    global_id = getattr(entity, "GlobalId", None)  # 优先读取 GlobalId。
    if global_id:  # 检查是否存在 GlobalId。
        return str(global_id)  # 返回 GlobalId。
    if hasattr(entity, "id"):  # 检查是否可读取 STEP 实例号。
        return f"step{entity.id()}"  # 返回 STEP 实例号标识。
    return content_hash(str(entity))[:16]  # 使用对象文本哈希作为最后备用身份。


def _geometry_vertices(entity: Any) -> tuple[list[list[float]], list[str]]:  # 使用 IfcOpenShell 几何内核读取世界坐标顶点。
    warnings: list[str] = []  # 初始化几何警告。
    try:  # 捕获无表示或几何内核错误。
        import ifcopenshell.geom  # type: ignore  # 导入可选 IFC 几何模块。
        settings = ifcopenshell.geom.settings()  # 创建几何设置。
        settings.set(settings.USE_WORLD_COORDS, True)  # 请求输出世界坐标。
        shape = ifcopenshell.geom.create_shape(settings, entity)  # 生成产品三角化几何。
        flat = list(shape.geometry.verts)  # 读取扁平顶点数组。
        vertices = [[float(flat[index]), float(flat[index + 1]), float(flat[index + 2])] for index in range(0, len(flat), 3)]  # 转换为三维点列表。
        if not vertices:  # 检查几何是否为空。
            warnings.append("几何内核返回空顶点集合。")  # 记录空几何警告。
        return vertices, warnings  # 返回顶点和警告。
    except Exception as error:  # 处理几何生成失败。
        warnings.append(f"几何生成失败：{error}")  # 记录失败原因。
        return [], warnings  # 返回空顶点集合。


def _placement_origin(entity: Any) -> list[float]:  # 从产品放置读取近似世界坐标原点。
    try:  # 捕获 IfcOpenShell 工具模块不可用或非法放置。
        import ifcopenshell.util.placement  # type: ignore  # 导入放置矩阵工具。
        matrix = ifcopenshell.util.placement.get_local_placement(getattr(entity, "ObjectPlacement", None))  # 计算世界放置矩阵。
        return [float(matrix[0][3]), float(matrix[1][3]), float(matrix[2][3])]  # 返回平移分量。
    except Exception:  # 处理放置解析失败。
        return [0.0, 0.0, 0.0]  # 返回安全原点。


def _bounds(vertices: list[list[float]], fallback: list[float]) -> tuple[list[float], list[float], list[float]]:  # 计算几何包围盒中心、尺寸和主轴端点。
    points = vertices or [fallback]  # 使用几何顶点或放置原点。
    minimum = [min(point[index] for point in points) for index in range(3)]  # 计算三向最小坐标。
    maximum = [max(point[index] for point in points) for index in range(3)]  # 计算三向最大坐标。
    center = [(minimum[index] + maximum[index]) * 0.5 for index in range(3)]  # 计算包围盒中心。
    size = [max(maximum[index] - minimum[index], 1e-6) for index in range(3)]  # 计算并限制包围盒尺寸。
    longest_axis = max(range(3), key=lambda index: size[index])  # 确定最长包围盒方向。
    start = list(center)  # 初始化主轴起点。
    end = list(center)  # 初始化主轴终点。
    start[longest_axis] = minimum[longest_axis]  # 设置主轴起点坐标。
    end[longest_axis] = maximum[longest_axis]  # 设置主轴终点坐标。
    if sum((end[index] - start[index]) ** 2 for index in range(3)) <= 1e-18:  # 检查主轴是否退化。
        end[longest_axis] += 1e-6  # 添加微小长度保持拓扑合法。
    return center, size, [start, end]  # 返回包围盒和主轴端点。


def _collect_entities(model: Any) -> list[Any]:  # 收集桥梁空间对象、物理构件和结构分析对象。
    entity_names = list(_TYPE_MAPPING) + ["IfcStructuralCurveMember", "IfcStructuralSurfaceMember", "IfcStructuralPointConnection", "IfcStructuralCurveConnection", "IfcStructuralSurfaceConnection"]  # 定义需要导入的 IFC 类型。
    entities: list[Any] = []  # 初始化实体列表。
    seen: set[int] = set()  # 初始化 STEP 实例去重集合。
    for entity_name in entity_names:  # 遍历 IFC 类型。
        try:  # 捕获 Schema 中不存在的类型。
            candidates = list(model.by_type(entity_name) or [])  # 查询当前类型实例。
        except Exception:  # 处理类型查询失败。
            candidates = []  # 使用空集合继续导入。
        for entity in candidates:  # 遍历查询结果。
            step_id = int(entity.id()) if hasattr(entity, "id") else id(entity)  # 读取实例标识。
            if step_id in seen:  # 检查继承查询导致的重复实例。
                continue  # 跳过重复实例。
            seen.add(step_id)  # 保存实例标识。
            entities.append(entity)  # 保存待导入实体。
    return entities  # 返回去重实体列表。


def import_ifc(path: str | Path, mvd_profile_path: str | Path | None = None, project_id: str | None = None) -> dict[str, Any]:  # 执行 IFC 4.3 到 BSDL Industrial 的实际映射。
    state = capability()  # 检测 IFC Adapter 能力。
    if not state["available"]:  # 检查可选依赖是否存在。
        raise RuntimeError(state["message"])  # 对不可用能力给出明确错误。
    file_path = Path(path).resolve()  # 规范化 IFC 文件路径。
    if not file_path.is_file():  # 检查 IFC 文件存在。
        raise FileNotFoundError(file_path)  # 对缺失文件抛出标准异常。
    import ifcopenshell  # type: ignore  # 导入 IfcOpenShell 主模块。
    model = ifcopenshell.open(str(file_path))  # 打开 IFC 文件。
    profile = load_profile(mvd_profile_path or DEFAULT_MVD)  # 读取项目 MVD 配置。
    mvd_report = validate_ifc_model(model, profile)  # 执行 IFC 4.3 项目级符合性检查。
    projects = list(model.by_type("IfcProject") or [])  # 读取 IFC 项目对象。
    bridges = list(model.by_type("IfcBridge") or [])  # 读取 IFC 桥梁对象。
    project_name = str(getattr(bridges[0], "Name", None) or getattr(projects[0], "Name", None) or file_path.stem) if bridges or projects else file_path.stem  # 选择项目名称。
    stable_project_id = project_id or _safe_token(str(getattr(bridges[0], "GlobalId", None) or file_path.stem) if bridges else file_path.stem, "project.ifc")  # 构造 BSDL 项目 ID。
    document = new_document(stable_project_id, project_name, "由 IFC 4.3 桥梁模型导入的物理结构描述。", "ifc43", str(file_path), "software.ifc43_importer")  # 创建工业 BSDL 基线文档。
    document["nodes"] = []  # 清除文档工厂占位节点。
    document["components"] = []  # 清除文档工厂占位构件。
    document["externalMappings"] = []  # 初始化外部映射集合。
    document.setdefault("extensions", {})["ifc43"] = {"schema": str(getattr(model, "schema_identifier", None) or getattr(model, "schema", "")), "mvdProfileId": profile.get("id"), "sourceFile": str(file_path)}  # 保存 IFC 来源元数据。
    node_by_coordinate: dict[tuple[float, float, float], str] = {}  # 初始化坐标到 BSDL 节点的去重映射。
    conversion_losses: list[dict[str, Any]] = []  # 初始化转换损失列表。
    parent_map: dict[int, str] = {}  # 初始化 IFC 实例到 BSDL 构件 ID 映射。
    entities = _collect_entities(model)  # 收集待导入实体。
    for entity in entities:  # 第一遍创建所有 BSDL 构件。
        ifc_type = _entity_type(entity)  # 读取 IFC 类型。
        source_key = _entity_key(entity)  # 读取 IFC 稳定身份。
        component_id = _safe_token(source_key, "component.ifc")  # 构造 BSDL 构件 ID。
        parent_map[int(entity.id()) if hasattr(entity, "id") else id(entity)] = component_id  # 保存实例映射。
        mapping = _TYPE_MAPPING.get(ifc_type, ("other", "solid", "excluded"))  # 查找物理类映射。
        if ifc_type == "IfcStructuralCurveMember":  # 处理 IFC 分析曲线构件。
            mapping = ("rod", "line", "frame3d")  # 映射为线分析构件。
        elif ifc_type == "IfcStructuralSurfaceMember":  # 处理 IFC 分析面构件。
            mapping = ("surface", "surface", "shell")  # 映射为壳分析构件。
        elif "Connection" in ifc_type:  # 处理 IFC 结构连接。
            mapping = ("joint", "point", "excluded")  # 映射为连接候选构件。
        category, topology, element_type = mapping  # 解包 BSDL 映射结果。
        vertices, geometry_warnings = _geometry_vertices(entity)  # 提取世界坐标几何顶点。
        fallback = _placement_origin(entity)  # 提取放置原点作为几何备用。
        center, size, axis_points = _bounds(vertices, fallback)  # 计算包围盒和主轴。
        node_refs: list[str] = []  # 初始化构件节点引用。
        points_for_nodes = axis_points if topology == "line" else [center]  # 选择线端点或中心点作为结构节点。
        for point in points_for_nodes:  # 遍历需要创建的结构节点位置。
            coordinate_key = tuple(round(float(value), 8) for value in point)  # 构造坐标去重键。
            node_id = node_by_coordinate.get(coordinate_key)  # 查找已有节点。
            if node_id is None:  # 检查是否需要创建新节点。
                node_id = f"node.ifc.{len(node_by_coordinate) + 1}"  # 构造顺序稳定的导入节点 ID。
                node_by_coordinate[coordinate_key] = node_id  # 保存坐标映射。
                document["nodes"].append({"id": node_id, "name": node_id, "position": [float(value) for value in point], "coordinateSystemRef": "cs.global", "roles": ["imported_geometry_anchor"], "constraints": {"ux": False, "uy": False, "uz": False, "rx": False, "ry": False, "rz": False}, "tags": ["ifc43"], "sourceIds": {"ifcSource": source_key}, "attributes": {"generatedFrom": "geometry_bounds"}})  # 创建 BSDL 节点。
            node_refs.append(node_id)  # 保存构件节点引用。
        geometry = {"kind": "line", "points": axis_points} if topology == "line" else {"kind": "box", "center": center, "size": size, "rotation": [0.0, 0.0, 0.0]}  # 创建轻量几何表示。
        document["components"].append({"id": component_id, "name": str(getattr(entity, "Name", None) or f"{ifc_type} #{getattr(entity, 'id', lambda: '?')()}"), "category": category, "topology": topology, "parentRef": None, "nodeRefs": node_refs, "materialRef": None, "sectionRef": None, "geometry": geometry, "analysis": {"elementType": element_type, "active": False, "localUp": [0.0, 0.0, 1.0] if topology == "line" else None, "finiteElementModelRef": None, "shellSectionRef": None, "solidSectionRef": None}, "attributes": {"ifcType": ifc_type, "ifcPredefinedType": str(getattr(entity, "PredefinedType", None) or "NOTDEFINED"), "geometryVertexCount": len(vertices), "needsIdealizationApproval": True}, "featureDescriptors": {"bboxX": size[0], "bboxY": size[1], "bboxZ": size[2]}, "tags": ["ifc43", "physical" if not ifc_type.startswith("IfcStructural") else "analytical"], "sourceIds": {"ifcGlobalId": str(getattr(entity, "GlobalId", None) or ""), "ifcStepId": str(entity.id()) if hasattr(entity, "id") else "", "ifcType": ifc_type}})  # 创建 BSDL 构件。
        document["externalMappings"].append({"id": _safe_token(f"{source_key}.{component_id}", "mapping.ifc"), "sourceSystem": "IFC", "sourceVersion": str(getattr(model, "schema_identifier", None) or getattr(model, "schema", "")), "sourceId": source_key, "targetRef": component_id, "kind": "identity", "method": "direct", "confidence": 1.0, "geometryHash": content_hash({"center": center, "size": size, "vertices": len(vertices)}), "status": "valid" if vertices else "needs_review", "attributes": {"ifcType": ifc_type}})  # 保存 IFC 到 BSDL 身份映射。
        for warning in geometry_warnings:  # 遍历当前实体几何警告。
            conversion_losses.append({"category": "degraded", "sourceRef": component_id, "targetRef": component_id, "path": f"/{ifc_type}/{source_key}/Representation", "message": warning, "severity": "warning", "action": "保留 IFC 源文件并在几何可用环境中重新导入或人工核验。"})  # 保存几何降级记录。
    if not document["nodes"]:  # 检查 IFC 是否没有可导入实体。
        document["nodes"].append({"id": "node.ifc.origin", "name": "IFC 原点", "position": [0.0, 0.0, 0.0], "coordinateSystemRef": "cs.global", "roles": ["reference"], "constraints": {"ux": False, "uy": False, "uz": False, "rx": False, "ry": False, "rz": False}, "tags": ["placeholder"], "sourceIds": {}, "attributes": {"placeholder": True}})  # 创建安全占位节点。
    if not document["components"]:  # 检查 IFC 是否没有可导入对象。
        document["components"].append({"id": "component.ifc.root", "name": project_name, "category": "bridge", "topology": "solid", "parentRef": None, "nodeRefs": [document["nodes"][0]["id"]], "materialRef": None, "sectionRef": None, "geometry": {"kind": "box", "center": [0.0, 0.0, 0.0], "size": [1e-6, 1e-6, 1e-6], "rotation": [0.0, 0.0, 0.0]}, "analysis": {"elementType": "excluded", "active": False, "localUp": None, "finiteElementModelRef": None, "shellSectionRef": None, "solidSectionRef": None}, "attributes": {"placeholder": True}, "featureDescriptors": {}, "tags": ["placeholder"], "sourceIds": {}})  # 创建安全占位构件。
    report_id = f"conversion.ifc43.{hashlib.sha256(str(file_path).encode('utf-8')).hexdigest()[:12]}"  # 构造转换报告 ID。
    conversion_report = {"id": report_id, "adapter": "ifcopenshell_ifc43_import", "adapterVersion": "1.0.0", "sourceVersion": str(getattr(model, "schema_identifier", None) or getattr(model, "schema", "")), "targetVersion": "BSDL Industrial 1.0.0", "createdAt": utc_now(), "mapped": {"entities": len(entities), "nodes": len(document["nodes"]), "components": len(document["components"]), "externalMappings": len(document["externalMappings"])}, "losses": conversion_losses, "blocked": not mvd_report.get("valid", False), "artifactRefs": [], "roundTrip": {"performed": False, "reason": "导入阶段未执行 IFC 往返。"}}  # 组装转换报告。
    document["conversionReports"].append(conversion_report)  # 把转换报告写入 BSDL 文档。
    return {"document": document, "mvd": mvd_report, "conversionReport": conversion_report, "capability": state}  # 返回完整导入结果。
