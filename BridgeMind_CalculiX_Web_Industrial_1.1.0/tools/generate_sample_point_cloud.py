"""生成可用于点云 Importer 演示的双主梁桥 XYZ 点集。"""  # 说明脚本用途。
from __future__ import annotations  # 启用延迟类型注解。
from pathlib import Path  # 提供输出路径处理。
import numpy as np  # 提供确定性随机点和几何采样。


def sample_box(center: list[float], size: list[float], count: int, rng: np.random.Generator) -> np.ndarray:  # 在长方体表面与内部采样点。
    center_vector = np.asarray(center, dtype=float)  # 转换长方体中心。
    size_vector = np.asarray(size, dtype=float)  # 转换长方体尺寸。
    points = (rng.random((count, 3)) - 0.5) * size_vector + center_vector  # 在长方体内部均匀采样。
    face_axis = rng.integers(0, 3, size=count)  # 为每个点随机选择贴近的表面轴。
    face_sign = rng.choice([-0.5, 0.5], size=count)  # 为每个点随机选择正负表面。
    points[np.arange(count), face_axis] = center_vector[face_axis] + face_sign * size_vector[face_axis]  # 把点投影到选定表面。
    return points  # 返回采样点集。


def main() -> None:  # 生成并保存示例点云。
    root = Path(__file__).resolve().parents[1]  # 获取项目根目录。
    output = root / "examples" / "two_girder_bridge.xyz"  # 指定示例点云输出路径。
    rng = np.random.default_rng(20260813)  # 使用固定随机种子保证可复现。
    clouds: list[np.ndarray] = []  # 初始化几何块点集列表。
    clouds.append(sample_box([20.0, -3.0, 0.0], [40.0, 0.8, 1.6], 1800, rng))  # 采样左侧主梁。
    clouds.append(sample_box([20.0, 3.0, 0.0], [40.0, 0.8, 1.6], 1800, rng))  # 采样右侧主梁。
    for x in [0.0, 10.0, 20.0, 30.0, 40.0]:  # 遍历横梁位置。
        clouds.append(sample_box([x, 0.0, 0.0], [0.7, 6.0, 1.0], 500, rng))  # 采样当前横梁。
    points = np.vstack(clouds)  # 合并所有几何块点集。
    noise = rng.normal(0.0, 0.015, size=points.shape)  # 生成小幅测量噪声。
    points = points + noise  # 把噪声叠加到点坐标。
    output.parent.mkdir(parents=True, exist_ok=True)  # 确保输出目录存在。
    np.savetxt(output, points, fmt="%.6f")  # 保存为空格分隔 XYZ 文件。
    print(output)  # 输出生成文件路径。


if __name__ == "__main__":  # 检查脚本是否直接执行。
    main()  # 运行点云生成流程。
