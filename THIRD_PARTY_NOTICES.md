# Third-Party Notices

本文件说明 Abaqus Agent 发布物（`dist\abaqus-agent-server`、`dist\AbaqusAgent-portable`
及任何课程资料 zip）中第三方组件的许可归属。两件事必须分开说清：
**imageio-ffmpeg（Python 包装库）** 与 **ffmpeg（可执行二进制）** 是两个不同的作品、
两种不同的许可证。

---

## 1. imageio-ffmpeg（随发布物分发，BSD-2-Clause）

- 组件：`imageio-ffmpeg` 0.6.0 —— 纯 Python 包装库（`imageio_ffmpeg` 模块本身）。
- 分发状态：**其 Python 代码包含在本产品的打包发布物中**（PyInstaller PYZ 内）。
- 许可证：BSD 2-Clause License。该许可允许二进制再分发，条件是保留版权与许可声明，
  即本节的存在理由。

```
BSD 2-Clause License

Copyright (c) 2019-2025, imageio
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice, this
  list of conditions and the following disclaimer.

* Redistributions in binary form must reproduce the above copyright notice,
  this list of conditions and the following disclaimer in the documentation
  and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

## 2. ffmpeg 可执行二进制（**不随发布物分发**，GPLv3）

- imageio-ffmpeg 的 PyPI wheel 内附带一个静态链接的 ffmpeg 可执行文件
  （`ffmpeg-win-x86_64-v7.1.exe`，约 84MB）。经实测其构建参数含
  `--enable-gpl --enable-version3` 并静态链接 x264 / x265 / xvid / rubberband，
  即该二进制整体按 **GPLv3** 分发，另涉及 AVC/HEVC 编码器的专利授权问题。
- 处置：**本产品的所有发布物均已剔除该二进制**（`packaging\abaqus_agent.spec`
  在 Analysis 后过滤 `ffmpeg*`），因此本产品不承担 GPLv3 的随附源码/构建参数义务，
  也不分发任何 AVC/HEVC 编码实现。
- 运行时行为：动画拼片（帧序列 PNG → anim.mp4）需要用户**自备 ffmpeg**，
  解析顺序为环境变量 `IMAGEIO_FFMPEG_EXE` > 系统 PATH 中的 `ffmpeg`。
  未找到时功能降级为仅保留帧序列，并提示两种自行安装途径
  （见 `post\export_odb_animation_runner.py` 的 `FFMPEG_INSTALL_HINT`）。
  用户自行安装 ffmpeg 属用户自己的使用行为，不构成本产品的分发行为。
- 明确不做（G3 决议）：不改发 LGPL 构建的 ffmpeg 二进制（仍属分发）；
  不做安装器自动下载 ffmpeg（引入新的分发义务）。

## 3. FreeCAD 材料卡（随发布物分发，CC-BY-3.0 / CC-BY-4.0）

- 组件：`data/materials/freecad/*.json` —— 17 张材料卡，由 FreeCAD 标准材料库
  (`src/Mod/Material/Resources/Materials/Standard/`) 的 `.FCMat` 转换而来，
  取用 commit `c54df69e0b699e37fb67d116ef2d6ded8ebdc64e`（2026-08-05）。
- 分发状态：**包含在 wheel、PyInstaller 冻结包与公开源码树中**。
  `core/material_library.py` 运行时读取它们；只发代码不发数据会让
  `list_materials()` 在第一次调用时报错，所以两者必须一起走。
- 许可证：逐卡不同，本库中同时存在 **CC-BY-3.0** 与 **CC-BY-4.0**。
  署名要求的作者、原始文件路径、许可名与永久链接写在**每张卡自己的
  `source` 字段里**，汇总表在 `data/materials/README.md`。
  这么放是为了让署名跟着数据走：单独拷走一张卡时署名不会掉。
- 明确没取的：上游 140 张卡里有 119 张是 LGPL-2.0/2.1-or-later 或 CC-BY-SA-4.0。
  本产品是 AGPL-3.0-or-later **加商业双授权**——AGPL 那一半带得动 copyleft，
  商业那一半卖的是"免除 copyleft 义务"，而这个义务不是我们能替别人免除的。
  筛选条件写在 `data/materials/build_library.py --licenses`，是个显式参数，
  纯 AGPL 的分叉可以自行放开。

---

## 4. 交付物核查基线

任何对外交付的 zip / 安装包在出库前必须满足：

```
Get-ChildItem -Recurse <deliverable_dir> -Filter "ffmpeg*"   # 期望 0 命中
```

已知例外登记：`packaging\tauri\target\release\backend` 是一份**过期的**后端拷贝，
截至 2026-07-26 仍含旧的捆绑 ffmpeg，禁止直接对外交付；重建 Tauri 安装包前
必须先用过滤后的 spec 重新打包后端（跟进项，见 G3 结果记录）。
