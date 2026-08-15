# 材料库 / Material library

按名字取材料，数字有出处。spec 里手敲 `material.E: 210000.0  # MPa` 仍然可用，
也可以写材料名：

```yaml
material:
  library: Steel-Generic     # 展开成 E / nu / density / conductivity / ...
  # yield: 300               # 同块里写的键覆盖卡片值，覆盖会记进 provenance
```

`agent/orchestrator.py` 在**校验之前**就把 `library:` 展开成数字
（`resolve_spec_materials`）。这个顺序不是偏好：`schema/spec_schema.json` 的 material 块
是 `additionalProperties: false`、每个键都是数字，带着 `library:` 去校验会直接报
4 条错（实测：`'name'/'E'/'nu' is a required property` 加
`Additional properties are not allowed ('library' was unexpected)`）。
**任何先校验、后展开的路径都会把这个键判成非法**，而不是解析它。

直接在 Python 里取一个块也可以：

```python
from core import material_library

block, prov = material_library.load_material("CalculiX-Steel")
# block -> {"name": "CalculiX-Steel", "E": 210000.0, "nu": 0.3,
#           "density": 7.9e-09, "conductivity": 43.0,
#           "specific_heat": 590000000.0, "expansion_coeff": 1.2e-05}
# prov["properties"]["density"] -> {"raw": "7900 kg/m^3", "si": 7900.0,
#                                   "value": 7.9e-09, "unit": "t/mm^3", ...}
```

`list_materials()` 列出全部 17 种（名字 + 一行摘要）。名字打错会被拒绝，
并列出最接近的候选，不会给你一个"差不多"的材料。

数据在 `freecad/*.json`，**一个材料一个文件**。这么分是因为许可证是按卡片走的
（本库里同时有 CC-BY-3.0 和 CC-BY-4.0），把署名和它所覆盖的数字放在同一个文件里，
别人单独拷走一张卡时署名会跟着走；将来某张卡的许可被发现有问题，删一个文件就行。
没有 index 文件——索引是真相的第二份拷贝，过期后的表现是"列得出来但取不到"，
17 个小 JSON 不值得为此引入一份可能过期的状态。

---

## 出处与署名 / Attribution

全部数据来自 **FreeCAD** 的标准材料卡：

- 项目：FreeCAD — <https://github.com/FreeCAD/FreeCAD>
- 路径：`src/Mod/Material/Resources/Materials/Standard/`
- 取用 commit：`c54df69e0b699e37fb67d116ef2d6ded8ebdc64e`（2026-08-05）
- 取用日期：2026-08-06

每张卡的 `source.url` 是指向该 commit 的永久链接，`source.author` 是上游作者。
下表是 CC-BY 要求的署名，`E` / `ν` / `ρ` 已换算到 mm_MPa_t：

| 材料名 | 上游作者 | 许可 | E (MPa) | ν | ρ (t/mm³) | 上游文件 |
| --- | --- | --- | --- | --- | --- | --- |
| `ABS-Generic` | Juergen Riegel | CC-BY-3.0 | 2300 | 0.37 | 1.06e-09 | `Thermoplast/ABS-Generic.FCMat` |
| `Acrylic-Glass-Generic` | Przemo Firszt | CC-BY-3.0 | 2550 | 0.38 | 1.16e-09 | `Thermoplast/Acrylic-Glass-Generic.FCMat` |
| `Aluminum-6061-T6` | FreeCAD | CC-BY-4.0 | 68900 | 0.33 | 2.7e-09 | `Metal/Aluminum/Aluminum-6061-T6.FCMat` |
| `Aluminum-7075-T6` | FreeCAD | CC-BY-4.0 | 71700 | 0.33 | 2.81e-09 | `Metal/Aluminum/Aluminum-7075-T6.FCMat` |
| `CalculiX-Steel` | Juergen Riegel | CC-BY-3.0 | 210000 | 0.3 | 7.9e-09 | `Metal/Steel/CalculiX-Steel.FCMat` |
| `Concrete-EN-C35_45` | Bernd Hahnebach | CC-BY-3.0 | 32000 | 0.17 | 2.5e-09 | `Aggregate/Concrete-EN-C35_45.FCMat` |
| `Concrete-Generic` | Yorik van Havre | CC-BY-3.0 | 32000 | 0.17 | 2.4e-09 | `Aggregate/Concrete-Generic.FCMat` |
| `Glass-Generic` | Przemo Firszt | CC-BY-3.0 | 72000 | 0.22 | 2.52e-09 | `Glass/Glass-Generic.FCMat` |
| `PA6-Generic` | Uwe Stöhr | CC-BY-3.0 | 2930 | 0.39 | 1.15e-09 | `Thermoplast/PA6-Generic.FCMat` |
| `PET-Generic` | Uwe Stöhr | CC-BY-3.0 | 3150 | 0.36 | 1.38e-09 | `Thermoplast/PET-Generic.FCMat` |
| `PLA-Generic` | Uwe Stöhr | CC-BY-3.0 | 3640 | 0.36 | 1.24e-09 | `Thermoplast/PLA-Generic.FCMat` |
| `PP-Generic` | Uwe Stöhr | CC-BY-3.0 | 1470 | 0.44 | 9.16e-10 | `Thermoplast/PP-Generic.FCMat` |
| `PTFE-Generic` | Uwe Stöhr | CC-BY-3.0 | 564 | 0.46 | 2.07e-09 | `Thermoplast/PTFE-Generic.FCMat` |
| `PVC-Generic` | Uwe Stöhr | CC-BY-3.0 | 2800 | 0.38 | 1.38e-09 | `Thermoplast/PVC-Generic.FCMat` |
| `Reinforcement-FIB-B500` | Bernd Hahnebach | CC-BY-3.0 | 210000 | 0.3 | 7.85e-09 | `Aggregate/Reinforcement-FIB-B500.FCMat` |
| `Steel-Generic` | Juergen Riegel | CC-BY-3.0 | 200000 | 0.3 | 7.9e-09 | `Metal/Steel/Steel-Generic.FCMat` |
| `Wood-Generic` | Bernd Hahnebach | CC-BY-3.0 | 12000 | 0.05 | 7e-10 | `Wood/Wood-Generic.FCMat` |

许可证全文：
[CC-BY-3.0](https://creativecommons.org/licenses/by/3.0/legalcode) ·
[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/legalcode)。

> **待办（都在本目录之外，本次没有动）**：
> - 仓库根目录的 `THIRD_PARTY_NOTICES.md` 需要加一条指向本文件的条目。
> - `scripts/publish/manifest.py` 的 `PUBLIC_DIRS` 里没有 `data`，而 `core` 在里面。
>   现在直接发公开树会**只带代码不带数据**，`list_materials()` 一调就报
>   "材料库目录不存在"。`build_public_tree.py` 的 path-reference 检查只覆盖
>   `course/` 和 `docs/` 两个前缀，抓不到这个。
> - `pyproject.toml` 的 wheel packages 和 `packaging/abaqus_agent.spec` 的 `datas`
>   同理，需要各加一条 `data/materials`。

---

## 许可筛选：为什么 140 张卡只留下 17 张

FreeCAD 官方文档说 `StandardMaterial` 只收 CC-BY-3.0 的卡片。**实测不是这样**——
逐张读 `General.License` 字段，140 张卡的分布是：

| 上游许可 | 张数 | 收 | 理由 |
| --- | --- | --- | --- |
| `LGPL-2.0-or-later` | 110 | ❌ | copyleft |
| `CC-BY-3.0` | 18 | ✅ | 署名即可 |
| `LGPL-2.1-or-later` | 5 | ❌ | copyleft |
| `CC-BY-SA-4.0` | 4 | ❌ | copyleft（share-alike） |
| `CC-BY-4.0` | 3 | ✅ | 署名即可 |

本仓库是 **AGPL-3.0-or-later + 商业双授权**（见 `LICENSING.md`）。商业授权卖的正是
"解除 copyleft 义务"这件事，而这件事只能对自己拥有的内容做。把 115 张 LGPL 卡片和
4 张 CC-BY-SA 卡片装进交付物，等于替别人的数据承诺了一个无权承诺的授权——
AGPL 那一半没问题，商业那一半直接失效。所以只收署名类许可。

筛选口径是 `build_library.py --licenses` 的参数，不是写死的常量：如果你 fork 出去
**只**按 AGPL 分发，那 115 张 LGPL 卡片对你是合规的，自己重跑一次加进来即可。

许可通过后又被拒的 4 张，理由记在 `provenance.json` 里，也复述在下面。

---

## 换算：这里是唯一真正危险的地方

FreeCAD 卡片写的是**带单位的字符串**：`"7900 kg/m^3"`、`"210000 MPa"`、
`"26.0 GPa"`、`"68 µm/m/K"`。单位是解析出来的，不是假设出来的。
spec dialect 默认单位制是 `mm_MPa_t`（mm、N、MPa、tonne、s，能量 mJ，功率 mW）：

| 物理量 | spec 键 | 卡片单位（SI） | mm_MPa_t 单位 | 换算系数 | 例 |
| --- | --- | --- | --- | --- | --- |
| 密度 | `density` | kg/m³ | t/mm³ | **1e-12** | 7850 → 7.85e-09 |
| 弹性模量 / 强度 | `E`、`yield` | Pa | MPa | **1e-6** | 210000 MPa = 2.1e11 Pa → 210000 |
| 导热系数 | `conductivity` | W/(m·K) | mW/(mm·K) | **1** | 43 → 43 |
| 比热 | `specific_heat` | J/(kg·K) | mJ/(t·K) | **1e6** | 590 → 5.9e08 |
| 热膨胀系数 | `expansion_coeff` | 1/K | 1/K | **1** | 1.2e-05 → 1.2e-05 |
| 泊松比 | `nu` | — | — | **1** | 0.3 → 0.3 |

两个"看起来不用换"的要单独说：导热系数在两套单位制里数值**真的相同**
（1 W/(m·K) = 1 mW/(mm·K)），比热**真的不同**（差 1e6）。凭"都是 SI 派生量"
一起当成 1 就会错一个。

卡片里出现过的单位拼写（`MPa` / `GPa` / `kg/m^3` / `W/m/K` / `J/kg/K` / `m/m/K` /
`µm/m/K`）都在 `core/material_library.py` 的 `UNIT_TO_SI` 表里。
**表里没有的单位一律拒绝，不猜**——猜一个换算系数正是"算完了、图也出了、
数量级差一千倍"的来源。要加新单位，在那张表里补一行，附上它对 SI 的系数。

每个数字在 JSON 里存三份：`raw`（上游原字符串）、`parsed_unit`（解析出来的单位）、
`si` + `mm_MPa_t`（换算结果）。不用回头查上游就能核对这次换算对不对。
`load_material(units=...)` 支持 `mm_MPa_t`（默认）和 `SI_m_kg_s`，
其余单位制名字会被拒绝并列出支持的两个。

---

## 拒收清单（许可通过、内容不合格的 4 张）

| 卡片 | 拒收理由 |
| --- | --- |
| `PC-Molded` | 数值用逗号当小数点：`"2200,00 MPa"`。读成小数点是 2200 MPa，读成千分位是 220000 MPa，两个数对某种材料都成立，本模块没有依据分辨，所以整张拒收而不是猜一个。 |
| `Glass-E-GlassFibre` | 只有密度、抗压、抗拉强度，没有 E 和 ν。schema 里 `material` 块必须有这两个，做不成材料。 |
| `Glass-S2-GlassFibre` | 同上。 |
| `Default` | 只有 `Density: "1 kg/m^3"`，是 FreeCAD 的模板占位卡，不是材料。 |

完整的 140 张逐卡判定（收 / 拒 + 理由）在 `provenance.json`。

---

## 收了但没写进 material 块的东西

一样不许悄悄丢。这些在 `load_material()` 返回的 `provenance["not_included"]` 里
逐条列出，带原始值和理由：

- **屈服强度（`YieldStrength`）**——17 张里有 10 张带。默认**不**写进 material 块：
  `runner/build_v2.py` 看到 `yield` 就会生成 `*Plastic`，把线弹性分析变成弹塑性
  分析。要用请传 `load_material(..., include_plasticity=True)`。
  （注意 spec 的键是 `yield` 不是 `yield_stress`，后者会被 build_v2 指名拒绝。）
- **抗拉 / 抗压强度**——是失效判据不是本构，`material` 块没有对应键。
- **剪切模量**——各向同性材料的 G 由 E 和 ν 决定，spec 只在 `materials[]`
  复合材料条目里有独立的 `G12`。
- **内摩擦角**——Mohr-Coulomb 类本构，本 dialect 不生成。

另外，上游卡片自相矛盾的地方记在每张卡的 `notes` 里，原样保留数字、不替上游改数：

- `ABS-Generic` / `Acrylic-Glass-Generic` / `PET-Generic` / `PLA-Generic`：
  屈服强度高于抗拉强度。
- `Acrylic-Glass-Generic`：给的 G = 1.08 GPa，E/(2(1+ν)) = 0.9239 GPa，差 16.9%。
- `PET-Generic`：给的 G 是 0.0385 GPa，而 E/(2(1+ν)) = 1.158 GPa——推出来的值是
  卡片值的 30 倍，这张卡的 `ShearModulus` 基本可以判定是上游写错了。本 dialect 不用
  G，所以不影响算出来的结果，但用这张卡之前值得知道。

  `notes` 里的百分比一律以 **E、ν 推出来的值为基准**（也就是本库真正会用的那两个数），
  并在文字里写明基准。同一个分歧按卡片自身的 G 作基准会读出完全不同的数
  （PET 是 2908% 而不是 96.7%），没写基准的百分比读者没法复核。

---

## 重新生成

```powershell
# 1. 把 FreeCAD 的 .FCMat 卡片下载到某个目录（脚本自己不联网）
# 2. 重建
.venv\Scripts\python.exe data\materials\build_library.py `
    --cards <卡片目录> --commit <FreeCAD commit sha>
# 3. 验证
.venv\Scripts\python.exe -m pytest tests\test_material_library.py -q
```

`build_library.py` 只负责走文件、按许可过滤、写盘；解析、换算、拒收规则全在
`core/material_library.py` 里，也就是测试真正跑到的那份代码。
