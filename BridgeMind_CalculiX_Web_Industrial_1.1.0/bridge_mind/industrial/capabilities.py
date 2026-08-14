"""构造 BridgeMind CalculiX 网站的真实工业能力矩阵。"""  # 说明模块用途。
from __future__ import annotations  # 启用延迟类型注解。
import importlib.util  # 提供可选 Python 依赖检测。
import os  # 提供环境变量读取。
import shutil  # 提供外部程序查找。
from pathlib import Path  # 提供显式可执行路径检查。
from typing import Any  # 提供通用 JSON 类型注解。
from ..version import CALCULIX_TARGET_VERSION, LANGUAGE_VERSION, PACKAGE_VERSION  # 导入统一版本常量。


def _program_state(names: list[str], configured: str | None = None) -> dict[str, Any]:  # 查找配置路径或一组候选程序名称。
    candidates = ([configured] if configured else []) + names  # 把显式配置放在自动探测之前。
    for name in candidates:  # 遍历全部候选程序名称或路径。
        if not name:  # 跳过空配置。
            continue  # 继续下一个候选项。
        candidate = Path(name).expanduser()  # 把候选值解析为本地路径。
        path = str(candidate.resolve()) if candidate.is_file() else shutil.which(name)  # 优先使用真实文件，否则在 PATH 中查找。
        if path:  # 检查是否找到程序。
            return {"available": True, "executable": path, "matchedName": name, "verifiedVersion": None}  # 返回程序可用状态并保留待运行核验版本。
    return {"available": False, "executable": None, "matchedName": None, "verifiedVersion": None}  # 返回程序不可用状态。


def build_capability_matrix() -> dict[str, Any]:  # 返回可供前端、部署和 Adapter 使用的单一可信能力矩阵。
    ifcopenshell_available = importlib.util.find_spec("ifcopenshell") is not None  # 检测 IfcOpenShell Python 包。
    numpy_available = importlib.util.find_spec("numpy") is not None  # 检测 NumPy 依赖。
    calculix = _program_state(["ccx", "ccx_2.23", "ccx_2.22"], os.getenv("CCX_EXECUTABLE"))  # 检测 CalculiX 命令或显式路径。
    gmsh = _program_state(["gmsh"], os.getenv("GMSH_EXECUTABLE"))  # 检测可选 Gmsh 命令。
    authentication_enabled = bool(os.getenv("BRIDGEMIND_API_KEYS", "").strip())  # 检测生产 API 密钥配置。
    return {  # 返回分层能力矩阵。
        "product": {"name": "BridgeMind CalculiX Web", "version": PACKAGE_VERSION, "language": f"BSDL Industrial {LANGUAGE_VERSION}", "solverTarget": f"CalculiX {CALCULIX_TARGET_VERSION}"},  # 描述产品、语言和求解器目标版本。
        "web": {"responsive": True, "pwa": True, "touch": {"singleFingerRotate": True, "twoFingerPan": True, "pinchZoom": True, "tapSelect": True, "longPressRegion": True}, "offlineShell": True},  # 描述移动端和离线壳能力。
        "modeling": {"beam": True, "shell": True, "solid": True, "hybrid": True, "contactDefinition": True, "prestressDefinition": True, "constructionStages": True, "codeCheckFramework": True},  # 描述统一语言和工业数据模型能力。
        "calculixAdapter": {"elementTypes": ["B31", "B32", "T3D2", "S3", "S4", "S4R", "C3D4", "C3D6", "C3D8", "C3D8R", "C3D10", "C3D20", "C3D20R"], "contact": True, "prestressModes": ["equivalent_load", "truss_tendon", "initial_stress", "solver_native"], "constructionStages": True, "staticLint": True, "datResultImport": True, "frdArtifactRetention": True},  # 描述本项目已实现的 CalculiX 适配器契约。
        "builtin": {"frame3dLinearStaticPreview": numpy_available, "shellSolver": False, "solidSolver": False, "nonlinearContactSolver": False, "stageCompiler": True, "prestressLossEngine": True, "genericCodeCheckEngine": True},  # 描述 Python 内置计算与外部求解职责边界。
        "imports": {"pointCloud": True, "ifc43": {"available": ifcopenshell_available, "mode": "IfcOpenShell" if ifcopenshell_available else "dependency_missing", "projectMvdValidation": True, "certificationClaim": False}},  # 描述输入 Adapter 和 IFC 项目 MVD 能力。
        "exports": {"bsdl": True, "gmshGeometryScript": True, "calculixInput": True, "commercialSolverDecks": False, "ifc43Export": False},  # 描述当前真实输出能力并关闭未实现商业格式声明。
        "execution": {"calculix": calculix, "gmsh": gmsh, "nativeCalculiXBundled": False, "externalBinaryRequired": True},  # 描述服务器端可执行程序状态。
        "security": {"apiKeyAuthentication": authentication_enabled, "optimisticConcurrency": True, "auditLog": True, "artifactHashing": True, "pathIsolation": True, "securityHeaders": True},  # 描述生产安全能力。
        "deployment": {"docker": True, "reverseProxy": "Nginx", "httpsReady": True, "healthCheck": True, "persistentVolumes": True, "singleNodeExecution": True, "pwaInstallable": True},  # 描述随交付包提供的部署能力。
        "limitations": ["本交付环境没有捆绑或执行 CalculiX 原生二进制；服务器需要合法安装 CalculiX 并通过 CCX_EXECUTABLE 或 PATH 提供 ccx。", "内置 Python 数值求解仅用于线弹性空间梁快速预览；壳、实体、接触、预应力和施工阶段由 CalculiX 执行。", "IFC 4.3 导入依赖 IfcOpenShell，项目 MVD 用于交付约束检查，不构成 buildingSMART 官方 MVD 认证。", "通用规范验算引擎只执行项目合法配置并经责任工程师复核的规则包，不自带受版权保护的正式规范条文或认证结论。"],  # 明确工程和合规边界。
    }  # 完成能力矩阵。
