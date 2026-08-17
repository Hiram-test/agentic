# CalculiX .inp 兼容 / Compatibility

## 中文

这是 **VM 发现工作**，不是正式证据，也不是工程发布。

已落地能力：

- 导入 CalculiX/Abaqus 风格 `.inp`
- 生成 **仅供显示** 的 BSDL（`extensions.nativeCalculiX.useNativeDeck = true`）
- 导出时 **原生 deck 直通**，不从 BSDL 重建输入
- 静态检查允许 `MASS` / `EXPANSION`；MASS 单元可只有 1 个节点
- Web 增加「CalculiX .inp 兼容」区块（`#inpFile` / `#inpImportButton`）
- 启动可用 `?project=` 指定项目

**工程发布仍然 BLOCKED。**

本包 **不包含**：

- `ccx` / 求解器二进制
- `data/*.sqlite3`
- `runs/`
- 闸庆或其他实验室 deck
- 任何声称已完成物理结果或工程放行的材料

## English

This is **VM discovery work**. It is **not formal evidence** and **not an engineering release**.

Landed capabilities:

- Import CalculiX/Abaqus-style `.inp`
- Build **display-only** BSDL with `extensions.nativeCalculiX.useNativeDeck = true`
- Native-deck passthrough on export (do not rebuild the deck from BSDL)
- Linter allows `MASS` and `EXPANSION`; MASS elements may have 1 node
- UI block 「CalculiX .inp 兼容」 (`#inpFile`, `#inpImportButton`)
- Bootstrap deep-link via `?project=`

**Engineering release remains BLOCKED.**

This package does **not** include a ccx binary, sqlite databases, `runs/`, zhaqing decks, or any claim of physics results.
