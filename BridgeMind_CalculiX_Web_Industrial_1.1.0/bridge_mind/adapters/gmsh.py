"""把 BSDL 自适应线网格导出为可复现的 Gmsh GEO 脚本。"""  # 说明模块用途。
from __future__ import annotations  # 启用延迟类型注解。
from pathlib import Path  # 提供输出文件路径处理。
from typing import Any  # 提供通用 JSON 类型注解。
from ..fea.mesher import mesh_document  # 复用确定性空间梁网格器。
from ..utils import slug, utc_now  # 复用安全名称和统一时间戳。


def export_gmsh(document: dict[str, Any], output_path: str | Path, mesh_policy_id: str | None = None) -> dict[str, Any]:  # 导出 Gmsh 线网格 GEO 脚本。
    path = Path(output_path)  # 规范化输出路径。
    path.parent.mkdir(parents=True, exist_ok=True)  # 确保输出目录存在。
    mesh = mesh_document(document, mesh_policy_id)  # 生成当前策略对应的空间梁网格。
    nodes = mesh.get("nodes", [])  # 读取网格节点。
    elements = mesh.get("elements", [])  # 读取网格单元。
    node_numbers = {node["id"]: index + 1 for index, node in enumerate(nodes)}  # 为 Gmsh 点分配连续编号。
    line_numbers = {element["id"]: index + 1 for index, element in enumerate(elements)}  # 为 Gmsh 线分配连续编号。
    base_size = float(mesh.get("stats", {}).get("baseSize", 1.0) or 1.0)  # 读取全局基准尺寸用于点特征长度。
    lines: list[str] = []  # 初始化 GEO 文本行。
    lines.append(f"// BridgeMind Studio Gmsh export {utc_now()}")  # 写入生成时间注释。
    lines.append('SetFactory("OpenCASCADE");')  # 使用 OpenCASCADE 几何内核。
    for node in nodes:  # 遍历网格节点写入点。
        x, y, z = (float(value) for value in node["position"])  # 解包节点坐标。
        lines.append(f"Point({node_numbers[node['id']]}) = {{{x:.12g}, {y:.12g}, {z:.12g}, {base_size:.12g}}};")  # 写入 Gmsh 点定义。
    for element in elements:  # 遍历网格单元写入线。
        first_ref, second_ref = element["nodeRefs"]  # 解包单元端点。
        lines.append(f"Line({line_numbers[element['id']]}) = {{{node_numbers[first_ref]}, {node_numbers[second_ref]}}};")  # 写入线段定义。
    by_component: dict[str, list[int]] = {}  # 初始化构件到线编号映射。
    for element in elements:  # 遍历单元建立 Physical Curve 分组。
        by_component.setdefault(str(element.get("componentRef")), []).append(line_numbers[element["id"]])  # 保存构件线编号。
    for component_ref, line_ids in by_component.items():  # 遍历构件分组。
        safe_name = slug(component_ref)  # 构造 Gmsh 安全物理组名称。
        lines.append(f'Physical Curve("{safe_name}") = {{{", ".join(str(value) for value in line_ids)}}};')  # 写入物理线组。
    lines.append("Mesh 1;")  # 生成一维线网格。
    lines.append(f'Save "{path.stem}.msh";')  # 指定网格输出文件名。
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")  # 写入 GEO 脚本。
    return {"adapter": "gmsh_geo", "version": "0.1.0", "output": str(path), "meshStats": mesh.get("stats", {}), "mapped": {"points": len(nodes), "curves": len(elements), "physicalGroups": len(by_component)}, "losses": [], "warnings": list(mesh.get("warnings", [])), "blocked": False}  # 返回可审计转换报告。
