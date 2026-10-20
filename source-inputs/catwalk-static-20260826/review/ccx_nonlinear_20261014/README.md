# CCX 六工况非线性复核证据

本目录对应原六工况入口 `inputs/migrate_P1.inp` 至 `inputs/migrate_P6.inp`。P1 输入和六工况入口已在上级目录归档；本目录补充 P2–P6 的实际 CalculiX 非线性输入、`.dat`、`.sta`、对照记录和模型审查记录。

所有输入均保留 `*STEP, NLGEOM` 几何非线性设置。`COMPARE.json` 用于核对工况与历史结果，`independent_reread.json` 和 `model-review.md` 记录独立回读与模型边界。
