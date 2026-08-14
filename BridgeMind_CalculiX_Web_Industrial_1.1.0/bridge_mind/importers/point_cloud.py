"""XYZ/CSV 点云的体素降采样、DBSCAN 分割和 BSDL 初始结构生成。"""  # 说明模块用途。
from __future__ import annotations  # 启用延迟类型注解。
import csv  # 提供逗号分隔文本解析。
from pathlib import Path  # 提供输入文件路径处理。
from typing import Any  # 提供通用 JSON 类型注解。
import numpy as np  # 提供点云、主方向和包围盒计算。
from sklearn.cluster import DBSCAN  # 提供无需预设簇数的空间聚类。
from ..utils import content_hash, utc_now  # 复用内容哈希和统一时间戳。
from ..industrial.migration import upgrade_document  # 把点云初始文档统一升级到 BSDL Industrial 1.0。


def load_points(path: str | Path) -> np.ndarray:  # 从 XYZ 或 CSV 文本读取三维点。
    file_path = Path(path)  # 规范化输入路径。
    points: list[list[float]] = []  # 初始化点列表。
    with file_path.open("r", encoding="utf-8-sig", errors="replace") as stream:  # 打开文本并兼容 BOM。
        for raw_line in stream:  # 逐行读取点云。
            line = raw_line.strip()  # 去除行首尾空白。
            if not line or line.startswith("#"):  # 跳过空行和注释行。
                continue  # 继续读取下一行。
            normalized = line.replace(";", ",").replace("\t", ",")  # 统一常见分隔符。
            fields = next(csv.reader([normalized], skipinitialspace=True))  # 解析逗号分隔字段。
            if len(fields) == 1:  # 处理纯空格分隔的 XYZ。
                fields = line.split()  # 使用空白重新分割。
            if len(fields) < 3:  # 跳过字段不足的行。
                continue  # 继续读取下一行。
            try:  # 捕获标题或非法数值。
                point = [float(fields[0]), float(fields[1]), float(fields[2])]  # 解析前三个坐标字段。
            except ValueError:  # 处理非数值行。
                continue  # 跳过标题或损坏行。
            if all(np.isfinite(point)):  # 检查坐标有限性。
                points.append(point)  # 保存有效点。
    if not points:  # 检查是否成功读取点云。
        raise ValueError(f"点云文件不包含有效三维点：{file_path}")  # 对空点云给出明确错误。
    return np.asarray(points, dtype=float)  # 返回 N×3 数值数组。


def voxel_downsample(points: np.ndarray, voxel_size: float) -> np.ndarray:  # 使用体素质心执行确定性降采样。
    if voxel_size <= 0.0:  # 检查体素尺寸。
        return np.asarray(points, dtype=float)  # 非正尺寸表示不降采样。
    minimum = np.min(points, axis=0)  # 计算点云最小坐标。
    voxel_indices = np.floor((points - minimum) / voxel_size).astype(np.int64)  # 计算每个点的体素整数索引。
    unique, inverse = np.unique(voxel_indices, axis=0, return_inverse=True)  # 获取唯一体素和点到体素映射。
    sums = np.zeros((len(unique), 3), dtype=float)  # 初始化各体素坐标和。
    counts = np.zeros(len(unique), dtype=np.int64)  # 初始化各体素点数。
    np.add.at(sums, inverse, points)  # 累加每个体素内所有点坐标。
    np.add.at(counts, inverse, 1)  # 累加每个体素内点数量。
    return sums / counts[:, None]  # 返回每个体素的坐标质心。


def _cluster_descriptor(points: np.ndarray) -> dict[str, Any]:  # 计算单个点簇的几何描述和代理类型。
    center = np.mean(points, axis=0)  # 计算点簇质心。
    centered = points - center  # 构造去中心化点集。
    covariance = centered.T @ centered / max(len(points) - 1, 1)  # 计算三维协方差矩阵。
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)  # 计算对称协方差特征分解。
    order = np.argsort(eigenvalues)[::-1]  # 按方差从大到小排序主方向。
    eigenvalues = np.maximum(eigenvalues[order], 0.0)  # 排序并截断微小负数。
    eigenvectors = eigenvectors[:, order]  # 排序主方向矩阵。
    primary = eigenvectors[:, 0]  # 读取第一主方向。
    projections = centered @ eigenvectors  # 把点转换到主方向坐标。
    local_min = np.min(projections, axis=0)  # 计算主方向坐标最小值。
    local_max = np.max(projections, axis=0)  # 计算主方向坐标最大值。
    extents = np.maximum(local_max - local_min, 1e-9)  # 计算三个主方向尺度。
    ratio_21 = float(eigenvalues[1] / max(eigenvalues[0], 1e-18))  # 计算第二与第一主方差比。
    ratio_32 = float(eigenvalues[2] / max(eigenvalues[1], 1e-18))  # 计算第三与第二主方差比。
    if ratio_21 < 0.08:  # 判断线状点簇。
        topology = "line"  # 设置线拓扑。
        category = "rod"  # 设置线状构件类别。
        proxy_type = "line_like"  # 设置几何代理分类。
    elif ratio_32 < 0.08:  # 判断面状点簇。
        topology = "surface"  # 设置面拓扑。
        category = "surface"  # 设置面状构件类别。
        proxy_type = "surface_like"  # 设置几何代理分类。
    else:  # 处理体状点簇。
        topology = "solid"  # 设置实体拓扑。
        category = "solid_region"  # 设置实体区域类别。
        proxy_type = "solid_like"  # 设置几何代理分类。
    world_min = np.min(points, axis=0)  # 计算全局轴对齐包围盒下界。
    world_max = np.max(points, axis=0)  # 计算全局轴对齐包围盒上界。
    if topology == "line":  # 计算线状点簇两个端点。
        scalar = centered @ primary  # 计算点在第一主方向上的投影。
        start = center + float(np.min(scalar)) * primary  # 计算线段起点。
        end = center + float(np.max(scalar)) * primary  # 计算线段终点。
    else:  # 处理面状和体状点簇。
        start = center  # 使用质心作为占位起点。
        end = center  # 使用质心作为占位终点。
    return {"center": [float(value) for value in center], "worldMin": [float(value) for value in world_min], "worldMax": [float(value) for value in world_max], "worldSize": [float(value) for value in np.maximum(world_max - world_min, 1e-6)], "eigenvalues": [float(value) for value in eigenvalues], "principalAxes": [[float(value) for value in eigenvectors[:, index]] for index in range(3)], "principalExtents": [float(value) for value in extents], "ratio21": ratio_21, "ratio32": ratio_32, "topology": topology, "category": category, "proxyType": proxy_type, "start": [float(value) for value in start], "end": [float(value) for value in end], "pointCount": int(len(points))}  # 返回完整点簇描述。


def segment_points(points: np.ndarray, eps: float, min_samples: int = 20, voxel_size: float = 0.0) -> tuple[np.ndarray, list[dict[str, Any]], dict[str, Any]]:  # 对点云执行降采样和 DBSCAN 分割。
    sampled = voxel_downsample(points, voxel_size)  # 执行体素降采样。
    if len(sampled) < min_samples:  # 检查降采样后点数是否足够聚类。
        labels = np.zeros(len(sampled), dtype=int)  # 点数不足时把全部点视为一个簇。
    else:  # 处理正常聚类情况。
        labels = DBSCAN(eps=float(eps), min_samples=int(min_samples), n_jobs=-1).fit_predict(sampled)  # 执行 DBSCAN 空间聚类。
    cluster_ids = sorted(int(value) for value in set(labels.tolist()) if int(value) >= 0)  # 收集非噪声簇 ID。
    descriptors: list[dict[str, Any]] = []  # 初始化簇描述列表。
    for cluster_id in cluster_ids:  # 遍历每个空间簇。
        cluster_points = sampled[labels == cluster_id]  # 提取当前簇点集。
        descriptor = _cluster_descriptor(cluster_points)  # 计算簇几何描述。
        descriptor["clusterId"] = cluster_id  # 保存原聚类 ID。
        descriptors.append(descriptor)  # 加入描述列表。
    noise_count = int(np.sum(labels < 0))  # 统计噪声点数量。
    report = {"inputPointCount": int(len(points)), "sampledPointCount": int(len(sampled)), "clusterCount": len(descriptors), "noisePointCount": noise_count, "eps": float(eps), "minSamples": int(min_samples), "voxelSize": float(voxel_size)}  # 汇总分割统计。
    return sampled, descriptors, report  # 返回降采样点、簇描述和报告。


def build_bsdl_from_point_cloud(path: str | Path, eps: float = 0.6, min_samples: int = 6, voxel_size: float = 0.2, project_id: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:  # 从点云文件生成可编辑 BSDL 初始文档。
    file_path = Path(path)  # 规范化点云路径。
    points = load_points(file_path)  # 读取原始点云。
    sampled, descriptors, report = segment_points(points, eps, min_samples, voxel_size)  # 执行降采样和分割。
    if not descriptors:  # 处理全部点被判为噪声的情况。
        descriptor = _cluster_descriptor(sampled)  # 把全部降采样点作为单一对象。
        descriptor["clusterId"] = 0  # 设置默认簇 ID。
        descriptors = [descriptor]  # 构造单簇描述列表。
        report["clusterCount"] = 1  # 更新簇数量。
        report["fallbackSingleCluster"] = True  # 标记使用单簇回退。
    global_min = np.min(sampled, axis=0)  # 计算全点云包围盒下界。
    global_max = np.max(sampled, axis=0)  # 计算全点云包围盒上界。
    global_center = (global_min + global_max) * 0.5  # 计算全点云中心。
    global_size = np.maximum(global_max - global_min, 1e-6)  # 计算全点云尺寸。
    stable_project_id = project_id or f"project.pointcloud.{content_hash({'path': file_path.name, 'count': len(points), 'bounds': [global_min.tolist(), global_max.tolist()]})[:12]}"  # 生成稳定项目 ID。
    nodes: list[dict[str, Any]] = []  # 初始化 BSDL 节点列表。
    components: list[dict[str, Any]] = []  # 初始化 BSDL 构件列表。
    regions: list[dict[str, Any]] = []  # 初始化导入区域列表。
    landmarks: list[dict[str, Any]] = []  # 初始化认知地标列表。
    root_component_id = "component.bridge.imported"  # 定义点云根结构对象 ID。
    components.append({"id": root_component_id, "name": "点云整体结构", "category": "bridge", "topology": "solid", "parentRef": None, "nodeRefs": [], "materialRef": None, "sectionRef": None, "geometry": {"kind": "box", "center": [float(value) for value in global_center], "size": [float(value) for value in global_size], "rotation": [0.0, 0.0, 0.0]}, "analysis": {"elementType": "excluded", "active": False, "localUp": None}, "attributes": {"source": "point_cloud", "requiresClassification": True}, "featureDescriptors": {"pointCount": int(len(sampled))}, "tags": ["imported", "root"], "sourceIds": {"file": file_path.name}})  # 保存点云根结构对象。
    characteristic_sizes: list[float] = []  # 初始化对象特征尺寸集合。
    for sequence, descriptor in enumerate(descriptors, start=1):  # 遍历点云分割对象。
        component_id = f"component.cluster.{sequence}"  # 生成分割构件 ID。
        region_id = f"region.imported.cluster.{sequence}"  # 生成导入区域 ID。
        landmark_id = f"landmark.imported.cluster.{sequence}"  # 生成认知地标 ID。
        characteristic = max(float(np.min(descriptor["principalExtents"])), 0.05)  # 估计局部最小特征尺寸。
        characteristic_sizes.append(characteristic)  # 保存局部尺度。
        if descriptor["topology"] == "line":  # 处理线状点簇。
            first_node_id = f"node.cluster.{sequence}.start"  # 生成线起点 ID。
            second_node_id = f"node.cluster.{sequence}.end"  # 生成线终点 ID。
            nodes.append({"id": first_node_id, "name": f"点簇{sequence}起点", "position": descriptor["start"], "coordinateSystemRef": "cs.global", "roles": ["geometry", "landmark"], "constraints": {"ux": False, "uy": False, "uz": False, "rx": False, "ry": False, "rz": False}, "tags": ["imported"], "sourceIds": {"cluster": str(descriptor["clusterId"])}, "attributes": {"confidence": 0.6}})  # 保存线起点。
            nodes.append({"id": second_node_id, "name": f"点簇{sequence}终点", "position": descriptor["end"], "coordinateSystemRef": "cs.global", "roles": ["geometry", "landmark"], "constraints": {"ux": False, "uy": False, "uz": False, "rx": False, "ry": False, "rz": False}, "tags": ["imported"], "sourceIds": {"cluster": str(descriptor["clusterId"])}, "attributes": {"confidence": 0.6}})  # 保存线终点。
            node_refs = [first_node_id, second_node_id]  # 设置线构件端点引用。
            geometry = {"kind": "line", "points": [descriptor["start"], descriptor["end"]]}  # 构造线几何代理。
        else:  # 处理面状和体状点簇。
            center_node_id = f"node.cluster.{sequence}.center"  # 生成点簇中心节点 ID。
            nodes.append({"id": center_node_id, "name": f"点簇{sequence}中心", "position": descriptor["center"], "coordinateSystemRef": "cs.global", "roles": ["geometry", "landmark"], "constraints": {"ux": False, "uy": False, "uz": False, "rx": False, "ry": False, "rz": False}, "tags": ["imported"], "sourceIds": {"cluster": str(descriptor["clusterId"])}, "attributes": {"confidence": 0.6}})  # 保存中心节点。
            node_refs = [center_node_id]  # 设置非线构件代理节点引用。
            geometry = {"kind": "box", "center": descriptor["center"], "size": descriptor["worldSize"], "rotation": [0.0, 0.0, 0.0]}  # 构造轴对齐包围盒代理。
        components.append({"id": component_id, "name": f"分割对象{sequence}", "category": descriptor["category"], "topology": descriptor["topology"], "parentRef": root_component_id, "nodeRefs": node_refs, "materialRef": None, "sectionRef": None, "geometry": geometry, "analysis": {"elementType": "excluded", "active": False, "localUp": descriptor["principalAxes"][2]}, "attributes": {"requiresHumanClassification": True, "pointCount": descriptor["pointCount"], "proxyType": descriptor["proxyType"]}, "featureDescriptors": {"ratio21": descriptor["ratio21"], "ratio32": descriptor["ratio32"], "principalExtent1": descriptor["principalExtents"][0], "principalExtent2": descriptor["principalExtents"][1], "principalExtent3": descriptor["principalExtents"][2]}, "tags": ["imported", descriptor["proxyType"]], "sourceIds": {"cluster": str(descriptor["clusterId"])}})  # 保存点云分割构件。
        regions.append({"id": region_id, "name": f"点云分割区域{sequence}", "semanticType": "user_defined", "source": "imported", "geometry": {"kind": "box", "center": descriptor["center"], "size": [max(float(value), characteristic * 1.2) for value in descriptor["worldSize"]], "rotation": [0.0, 0.0, 0.0]}, "targetRefs": [component_id] + node_refs, "active": True, "meshLevel": 2, "targetSize": max(characteristic / 2.0, 0.05), "elementFamily": "auto", "amrEngine": "none", "maxIterations": 0, "reason": ["来自点云空间聚类的初始区域", f"几何代理类型为 {descriptor['proxyType']}", "需人工补充结构类别、材料、截面和连接"], "confidence": 0.6, "status": "needs_review", "evidenceRefs": [], "attributes": {"clusterId": descriptor["clusterId"], "pointCount": descriptor["pointCount"]}})  # 保存点云区域。
        landmarks.append({"id": landmark_id, "kind": "other", "targetRefs": [component_id], "position": descriptor["center"], "featureVector": {"proxyType": descriptor["proxyType"], "ratio21": descriptor["ratio21"], "ratio32": descriptor["ratio32"], "pointCount": descriptor["pointCount"]}, "reason": ["点云分割对象中心与主方向特征"], "confidence": 0.6})  # 保存点云认知地标。
    if not nodes:  # 防御性检查节点列表。
        nodes.append({"id": "node.pointcloud.center", "name": "点云中心", "position": [float(value) for value in global_center], "coordinateSystemRef": "cs.global", "roles": ["geometry", "landmark"], "constraints": {"ux": False, "uy": False, "uz": False, "rx": False, "ry": False, "rz": False}, "tags": ["imported"], "sourceIds": {}, "attributes": {}})  # 提供满足 Schema 的中心节点。
    base_size = float(np.median(characteristic_sizes)) if characteristic_sizes else max(float(np.max(global_size)) / 20.0, 0.1)  # 估计初始全局尺寸。
    document = {"$schema": "../schema/bsdl.schema.json", "language": "Bridge-Structural-Description-Language", "languageVersion": "0.1.0", "documentId": f"doc.{stable_project_id}", "revision": {"number": 1, "parent": None, "createdAt": utc_now(), "createdBy": "software.pointcloud_importer", "status": "working", "summary": "从 XYZ/CSV 点云生成的 BSDL 初始结构"}, "project": {"id": stable_project_id, "name": file_path.stem, "description": "点云分割后生成的结构代理模型，需人工完成结构语义和力学属性。", "sourceType": "point_cloud", "sourceUri": str(file_path), "tags": ["point_cloud", "needs_review"]}, "units": {"length": "m", "force": "N", "mass": "kg", "stress": "Pa", "angle": "rad"}, "coordinateSystems": [{"id": "cs.global", "name": "点云全局坐标系", "parentRef": None, "origin": [0.0, 0.0, 0.0], "xAxis": [1.0, 0.0, 0.0], "yAxis": [0.0, 1.0, 0.0], "zAxis": [0.0, 0.0, 1.0]}], "agents": [{"id": "software.pointcloud_importer", "name": "BridgeMind PointCloud Importer", "kind": "software", "version": "1.0.0"}], "materials": [], "sections": [], "nodes": nodes, "components": components, "connections": [], "loadCases": [], "loads": [], "analysisTasks": [{"id": "task.structure_recognition", "name": "结构识别与区域规划", "type": "other", "loadCaseRefs": [], "qoi": ["component_classification", "connection_recognition", "region_strategy"], "accuracyTarget": 0.1, "budget": {"maxElements": 100000, "maxRuns": 1, "maxWallSeconds": 300.0}, "status": "draft"}], "cognitiveMap": {"landmarks": landmarks, "decisionEdges": [], "version": 1}, "regions": regions, "meshPolicies": [{"id": "mesh.pointcloud.initial", "name": "点云初始区域策略", "taskRef": "task.structure_recognition", "baseSize": max(base_size, 0.05), "elementFamily": "auto", "regionRules": [{"regionRef": region["id"], "targetSize": region["targetSize"], "priority": 50} for region in regions], "budget": {"maxElements": 100000, "maxIterations": 0}, "status": "draft"}], "solverPlans": [], "feedback": [{"id": "feedback.pointcloud.import", "source": "importer", "kind": "validation", "createdAt": utc_now(), "createdBy": "software.pointcloud_importer", "targetRefs": [component["id"] for component in components], "before": None, "after": {"clusterCount": len(descriptors)}, "metrics": report, "comment": "点云完成降采样、DBSCAN 分割和主方向几何代理生成。", "status": "recorded"}], "artifacts": [{"id": "artifact.pointcloud.source", "kind": "point_cloud", "uri": str(file_path), "format": file_path.suffix.lower().lstrip(".") or "xyz", "hash": None, "createdAt": utc_now()}], "experienceRefs": [], "extensions": {"bridgemind:pointCloudImport": report}}  # 构造完整 BSDL 文档。
    return upgrade_document(document), report  # 返回统一升级到工业主版本的导入文档和分割报告。
