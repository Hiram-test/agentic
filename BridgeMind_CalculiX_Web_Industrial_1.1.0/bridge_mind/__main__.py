"""允许通过 python -m bridge_mind 调用命令行工具。"""  # 说明模块用途。
from .cli import main  # 导入命令行主函数。


if __name__ == "__main__":  # 检查模块是否作为程序执行。
    raise SystemExit(main())  # 执行命令行并传播状态码。
