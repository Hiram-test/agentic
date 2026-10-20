# catwalk_base_C01 — PPT 交付算例

- 来源 run id: `17a00fbe85854e73896342299cbf53b4`（`99_audit/root_verified_cases/base/`，与 `04_calculix/base/` 副本 sha256 一致）
- 网格档 base（索细分2段），工况 C01 恒载
- ccx exit code: `0`；1 step / 1 inc / 3 iterations，Total CalculiX Time 3.30 s
- `.dat`、`_stderr.txt` 为 0 字节（原样）

| 文件 | 字节 | sha256 |
|---|---|---|
| `catwalk_base_C01.cvg` | 520 | `c38f4a49f5dcb6b125856f1d2d46613a9db157ea7d10b9924e2aad3be43f3325` |
| `catwalk_base_C01.dat` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `catwalk_base_C01.inp` | 1772218 | `810083849dee8468776b42d4775e608c09f98f2b81a90293ae3e492ecb3d5ae1` |
| `catwalk_base_C01.sta` | 170 | `567b13fb49c7f969107cabbd7421a71863eb59f7acc52b7ad05ed0d0dbf9e051` |
| `catwalk_base_C01_ccx_exit.txt` | 2 | `9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa` |
| `catwalk_base_C01_stderr.txt` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `catwalk_base_C01_stdout.txt` | 4987 | `ca321242a3416242109ef41d225b8e0cd7d1d31645642645dc2314aa0432d27b` |
| `catwalk_base_C01_disp.png` | 114724 | `db859caaa3a0de6427e67d59ec27a620e60b32d664f171413ba11ce9388d3902` |
| `catwalk_base_C01_force.png` | 88007 | `ac3ef116f21a215e2a8acf98576ff3a7bf74edb9bb9b6b66b6930f3bc74a7e4a` |
| `catwalk_base_C01_stress.png` | 117042 | `ee527fa1aca9624d9c5c02a16fde80ccf5cfb243fc9b1eb49c2609bd00e820ea` |

云图 PNG（stress/disp/force）为二进制，本次提交工具只能写文本文件，未入库；哈希见上表。

注：另一 run `08d82d5260c1413f9e5d5935ea6432fa/04_calculix_static/{base,rerun_base}/catwalk_base_C01.inp`（sha256 `9e99682a…`，1818598 B）与本版本不同（节点/单元内容差异大），非本交付版本。
