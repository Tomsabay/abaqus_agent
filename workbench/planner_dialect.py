"""
workbench/planner_dialect.py
----------------------------
The v2 spec dialect document that build_prompt pastes into every claude_cli
planning call. Text, not code: each rule records a measured trap (the numbers
and failure modes were observed on the real solver), so this file changes when
the engine grammar does and for no other reason. Held apart from planner.py so
the module that RUNS the calls stays small enough to hold in one read.
"""

from __future__ import annotations

# Held apart from _PROMPT_TEMPLATE and passed in as a *value*, not inlined:
# _PROMPT_TEMPLATE goes through str.format, and this text is almost entirely YAML
# flow mappings — `{op: sketch, ...}` — every one of which format() would read as
# a replacement field and die on. Doubling several hundred braces to keep them in
# one string is a diff nobody can check.
V2_DIALECT = """### 选择器：怎么点名一块面，以及为什么必须数个数
写法 `[<实例名>:]<kind>@<axis>=<place>`：
  kind  = face|faces|edge|edges|cell|cells|vertex|vertices|node|nodes|element|elements
  axis  = x|y|z，或 r（按半径选，只有 face/edge 有半径）
  place = min|max|具体数值；另有 `<kind>@all`
例：`Lower:face@y=max`、`Bar:vertices@z=max`、`Plate:face@r=6`、`Plate:cells@all`。
- 实例的包围盒是**装配坐标系**的：Upper 平移 +5 之后，`Upper:face@y=5` 指的是平移**之后**
  的 y=5，跟写 spec 的人想的一致。
- 单数默认要求正好命中 1 个（=1），复数和 @all 默认 >=1；要别的写 `expect: "=4"` /
  `expect: ">=2"`。
- **数量断言是这一层的地基**：Abaqus 选面选空了不报错，Set() 照收空序列，
  作业照样 COMPLETED——只是边界条件加在了空气上。所以凡是你能数出来的个数就写出来
  （一个平面上有几个面、一个端面有几个角点），命中数不符必须当场中止。
- 孔壁没法用平面命名（它的包围盒在 x/y 上就是整块板），用 `face@r=<半径>`；
  局部加密的圈边用 `edges@r=<半径>`。**local_seeds 的 region 只能选 edge**——
  Abaqus 只给边种种子，face/cell 会被指名拒绝（实测有草稿在这里写 face@ 被拒）。
- 装配域（interactions / conditions / assembly.operations）的选择器**必须带实例名**；
  零件域（parts 里的 features、mesh.local_seeds）**不能带实例名**——种子和特征作用在
  零件上，那时还没有实例。
- `node@` / `element@` 点的是网格，只有已划网的零件和 orphan mesh 有。orphan mesh
  零件**没有 cell/face/edge/vertex**（实测：189 节点 80 单元、四种几何实体全是 0），
  所以那种零件上只有这两个 kind 能用。
- **`element@` 只收 `@all`**：单元是个体，不是面，平面切不出一层单元来——
  实测 `getByBoundingBox` 对单元是"整个包住才算"，一层零厚度的平面命中 0 个（共 80 个），
  把带子加厚到一个单元的厚度才命中那层的 4 个。要按平面点名就选 `nodes@`。
- **`cell@` 只收 `@all`**：同样的道理，cell 也是个体。实测（分成两个 cell 的板）
  `cell@x=min` 命中 **0 个**（带子加宽一百倍还是 0），而同一条带子下 `face@x=min`
  命中 1 个、能整个包住那个 cell 的盒子命中 1 个——所以不是带子太薄，是平面永远
  切不中体。要按平面点名就用 `face@`，几何面本来就长在平面上。

### parts（零件，至少一个）
每个零件：name / features / section 必写，mesh / expect 可选。
```yaml
parts:
  - name: Plate
    features:
      - {op: sketch, id: outline, plane: XY,
         profile: {rect: {corner1: [0.0, 0.0], corner2: [60.0, 240.0]}}}
      - {op: extrude, sketch: outline, depth: 5.0}
      - {op: sketch, id: hole, plane: XY,
         profile: {circle: {center: [30.0, 120.0], r: 6.0}}}
      - {op: cut_extrude, sketch: hole, depth: 5.0}
    section: {type: solid, material: Steel}    # solid | shell
    mesh:
      seed: 5.0
      element: C3D8I          # 常用这四个：C3D8I | C3D20R | C3D8 | C3D8R
                              # 其他六面体码由生成器的配对表决定，不认识的会被指名拒绝
      technique: free         # 可选：free | sweep | structured；不写让 Abaqus 自己挑
      local_seeds:
        - {region: "edges@r=6", size: 1.2, expect: "=2"}
```

**板壳零件**（钢板、楼板、薄壁件）：`section.type: shell` + 必写 `thickness`。
零件仍是 `dimensionality: THREE_D`——空间里的一张面就是三维零件，Abaqus 没有
第四种 dimensionality——但它的**本体是 face 不是 cell**，用 `{call: BaseShell}` 造，
`expect` 写 `area` 不写 `volume`，单元用壳单元（S4R / S4 / S3 / S8R）：
```yaml
    section: {type: shell, material: Steel_Q345, thickness: 25.0}
    mesh: {seed: 100.0, element: S4R, hourglass_control: ENHANCED}
    expect: {area: 4000000.0, faces: 1}
```
- `thickness` 是壳唯一一处写厚度的地方（几何里没有），不写直接拒绝。
- 厚度方向积分点默认 5（Simpson）。板外纤维屈服要靠这 5 个点解出塑性铰，
  改成 3 会少报塑性，要改写 `section.integration_points`。
- ⚠️ `hourglass_control` 不是装饰：实测 explicit_impact 同一套网格，
  带 ENHANCED 报 31817 N 支反力，不带报 33501 N，差 5.3%，**两个作业都正常完成**。
  缩减积分单元（末尾 R）配 explicit 步就要写它。
名义 op 的硬规矩：
- 草图 plane 只有 XY，base 拉伸沿 +z——所以零件的"长度"方向是 z。
- 只能拉伸一次（第二次 extrude 会替换本体）；cut_extrude 必须在 extrude 之后。
- **cut_extrude 只支持圆**。矩形挖槽会被拒：挖完不留曲面，事后没东西可核对，
  而挖偏是完全静默的——体积不变、单元数不变、不报错。
- 草图 id 只能用字母数字下划线（它会变成生成脚本里的变量名，连字符会炸）。
- 接触算例的单元别用 C3D20R（实测二次单元接触不收敛），用 C3D8I。
- ⚠️ **不写 `element:` 拿到的是 C3D8R**，它是一阶缩减积分单元：厚度方向只有一层
  时几乎没有弯曲刚度。实测同一根 10×10×100 悬臂加侧向压力，一层单元时
  C3D8I −0.7126152 / C3D8R −65.66674（差 92 倍），两层时差 1.34 倍，
  **两次作业都报 COMPLETED**；而 C3D8I 从一层到两层只变 0.3%，也就是说错的
  那一边不是网格不够密。弯曲为主就写 C3D8I 或 C3D20R；真要用 C3D8R，
  厚度方向至少给两层单元。引擎会就此发一条警告并写进报告，但它不会拒绝求解。

这四步画不出来的零件，直接说 Abaqus 的方法名，其余键就是它的关键字参数：
```yaml
    features:
      - op: sketch
        id: profile
        entities:
          - {call: ConstructionLine, point1: [0.0, 0.0], point2: [0.0, 10.0]}
          - {call: Line, point1: [4.0, 0.0], point2: [30.0, 0.0]}
      - {call: BaseSolidRevolve, sketch: {sketch: profile}, angle: 360.0,
         flipRevolveDirection: "OFF"}
    expect:
      volume: 31730.07
      cells: 1
      cylindrical_faces: 3
      cylinders: [{r: 3.0, at: [0.0, 5.0, 20.0]}]
```
- **零件里只要出现 call:，就必须写 expect:**（volume / cells / faces / edges /
  vertices / cylindrical_faces / cylinders 至少一项）。名义 op 自带检查，通用调用没有。
- 计数和体积**看不见"挖错地方"**：实测同一个孔草图定向轴写反，孔跑到 90° 外，
  体积差 1.5e-7、面数边数顶点数圆柱面数一模一样、不报错。所以位置要用
  `cylinders: [{r: ..., at: [x, y, z]}]` 明说。
- 零件如果**自己用通用调用划网格**，还必须写 `expect: {mesh: {elements: "=10030"}}`：
  实测 elemShape=HEX + technique=SYSTEM_ASSIGN 在划不出六面体的零件上被接受、
  产出 0 个单元、不报错。
- 名义 op 不能消费 entities 画的草图，反过来也不行。

### 零件从文件读进来（STEP/IGES/SAT 几何，或 .inp/.nas 的 orphan mesh）
用户给了模型文件就走这条，别照着描述把形状重画一遍。`features` 换成 `import`：
```yaml
parts:
  - name: Bracket                       # 几何：先开文件，再从它建零件
    import:
      open: {call: openStep, fileName: {file: bracket.stp},
             scaleFromFile: "OFF"}
      part: {call: PartFromGeometryFile,
             dimensionality: THREE_D, type: DEFORMABLE_BODY}
    expect: {volume: 10000.0, cells: 1}
    section: {type: solid, material: Steel}
    mesh: {seed: 5.0, element: C3D8I}
  - name: Bar                           # orphan mesh：没有 open:，deck 自带网格
    import:
      part: {call: PartFromInputFile, inputFileName: {file: bar.inp}}
    expect: {mesh: {nodes: 189, elements: 80}}
    section: {type: solid, material: Steel}
```
- **导入的零件必须写 expect**：几何写 `volume` / `cells`，orphan mesh 写
  `expect.mesh.nodes` / `elements`。实测同一根杆导出再读回来，STEP 和 SAT 给 1 个
  cell、体积 10000.0，**IGES 给 0 个 cell、体积 0.0 而且不报错**——曲面进来了、实体没有。
  不核对就等于把一个空壳零件当零件用。
- `expect.mesh` 里只写 quality / max_warned 不算数：那是给网格划分定的界，
  没说文件里到底来了什么。
- orphan mesh 零件**不许再写 `mesh:` 块**（网格已经在文件里了），也不能写体积/面数——
  实测它 `getVolume()` 返回 0.0 且不报错。截面按 `ALL` 集合整体指派。

### 用户已经有一份完整 .inp
整份 deck 直接跑，别照着它把模型重描一遍。用顶层 `deck:`，此时
parts / assembly / steps / conditions / interactions **一个都不许写**：
```yaml
deck:
  file: SteelFrameBlast.inp     # 相对**这份 spec 文件**，不是相对 run 目录
```
- deck 自带零件、分析步、边界条件、载荷。spec 再写一份等于给读的人一个和实际
  跑的东西不一致的说法，所以是拒绝而不是忽略。
- 只有 `meta` / `material` / `outputs` 跟着走；KPI 照常从 ODB 里取。
- .inp 的**内容**会进构建指纹。原地改 .inp 而路径不变，缓存曾经把上一版 deck
  原样递回来：实测源文件 100N 改成 900N、重跑、cached=True、作业 COMPLETED、
  跑的是 100N 那份。
- `PartFromInputFile` 不收 `name:`，零件名由 deck 决定（实测 deck 里叫 Bar 的进来是
  `BAR`），这边会自动改回 spec 里的名字；文件里如果有多个零件会被指名拒绝，不猜。
- 路径写 `{file: <相对路径>}`，相对的是 **spec 文件所在目录**。文件不存在当场拒，
  不会启动 CAE 去占一个 license。

### seam（裂缝面：一层面裂成两片，不是切开）
`assignSeam` 挂在零件的 engineeringFeatures 上，区域必须是**零件集合**，
而且要在划网之前（零件特征本来就跑在 generateMesh 前面）：
```yaml
    features:
      # …前面先把零件分成两个 cell，seam 加在它们共享的那个面上
      - call: assignSeam
        target: {attr: engineeringFeatures}
        regions: {set: "face@z=5", name: SEAMFACE, expect: "=1"}
    expect:
      seams: [{set: SEAMFACE, duplicated: 9}]
```
- **必须写 `expect.seams`**：实测把 seam 加在一个不被两个 cell 共享的面上
  （比如零件外表面），`assignSeam` 正常返回、不报错、什么也没发生——
  10×10×10 分两半 seed 5 的块，内部面加 seam 是 36 个节点，外表面加是 27 个，
  跟没加一模一样。`set` 是上面 `{set: ..., name: X}` 给的那个集合名，
  `duplicated` 是这个面上**裂成两个节点的位置数**：3×3 的面就是 9
  （生效后集合里 18 个节点占 9 个位置，不生效是 9 个节点占 9 个位置）。
- 加在装配上会被拒，理由是**时机**不是作用域：实测 seam 加在 `generateMesh`
  **之后**节点数一个都不变、也不报错（27→27，先加才是 36），而零件特征跑在
  `generateMesh` 之前、装配操作跑在之后。拒绝信息里会给出改法。
- XFEM 裂纹（`XFEMCrack`）**还没测过**，别写。围线积分（`ContourIntegral`）已经测通，
  见下面「二维零件与裂纹」。

### 二维零件与裂纹（围线积分 J）

零件带 `dimensionality: THREE_D | TWO_D_PLANAR | AXISYMMETRIC`（默认 THREE_D）。
这**不是标签**：它决定截面指派、单元类型、网格控制是作用在零件的 **cell** 上还是
**face** 上。平面零件用 `{call: BaseShell, sketch: {sketch: <id>}}` 造，
真值层写 `expect.area`（**不能写 volume**——实测平面零件 `getVolume()` 返回 0.0
且不报错），单元用 CPE/CPS/CAX 系列，截面可以给 `thickness:`。
平面零件配六面体单元会被当场拒——Abaqus 不拒，它会一个单元都不划还什么都不说。

**`kind@box=xMin,yMin,zMin,xMax,yMax,zMax`**：六个数，Abaqus 自己
`getByBoundingBox` 的顺序，语义是**整个包在里面**。这是唯一能「在两个里点一个」的
形式——分区之后 y=0 那条线变成两条边，平面形式两条都命中、`@all` 也是两条都命中，
中间原来什么都没有。数量断言照旧生效。

裂纹三步：分区把裂纹面和裂尖分出来 → 在**零件**上给裂纹那一段边加 seam →
在**装配**上声明 ContourIntegral（裂纹前沿是装配集合，不是零件集合）：
```yaml
parts:
  - name: Plate
    dimensionality: TWO_D_PLANAR
    features:
      - {op: sketch, id: o, plane: XY,
         profile: {rect: {corner1: [0.0, -50.0], corner2: [50.0, 50.0]}}}
      - {call: BaseShell, sketch: {sketch: o}}
      - {call: DatumPlaneByPrincipalPlane, principalPlane: XZPLANE, offset: 0.0, as: mid}
      - {call: PartitionFaceByDatumPlane, datumPlane: {datum: mid},
         faces: {select: "face@all"}}
      - {call: DatumPlaneByPrincipalPlane, principalPlane: YZPLANE, offset: 10.0, as: tip}
      - {call: PartitionFaceByDatumPlane, datumPlane: {datum: tip},
         faces: {select: "face@all"}}
      - call: assignSeam
        target: {attr: engineeringFeatures}
        regions: {set: "edge@box=0,0,0,10,0,0", name: CRACKLINE, expect: "=1"}
    expect: {area: 5000.0, faces: 4, seams: [{set: CRACKLINE, duplicated: 20}]}
    section: {type: solid, material: Steel, thickness: 1.0}
    mesh: {seed: 1.0, element: CPE8}
assembly:
  instances: [{name: P, part: Plate, translate: [0.0, 0.0, 0.0]}]
  operations:
    - call: ContourIntegral
      target: {attr: engineeringFeatures}
      name: {literal: Crack}
      symmetric: "OFF"
      crackFront: {set: "P:vertex@box=10,0,0,10,0,0", name: TIP, expect: "=1"}
      crackTip: {named_set: TIP}
      extensionDirectionMethod: Q_VECTORS
      qVectors: [[[10.0, 0.0, 0.0], [11.0, 0.0, 0.0]]]
      midNodePosition: 0.25
      collapsedElementAtTip: SINGLE_NODE
conditions:
  - call: HistoryOutputRequest
    name: {literal: JOUT}
    createStepName: {literal: Pull}
    contourIntegral: {literal: Crack}
    numberOfContours: 6
    contourType: J_INTEGRAL
    rebar: EXCLUDE
```
- `expect.seams.duplicated` 比线上的节点位置数**少一个**：裂尖是 seam 终止的地方，
  那个节点不裂开。实测这块板 41 个节点占 21 个位置，所以写 20。
- KPI 写 `{type: contour_integral_j, location: Crack}`，`location` 就是
  ContourIntegral 的名字。
- 实测（Abaqus 2021）：这份 spec 出来的 J = 2.503265619277954，
  和手写 CAE 脚本建的同一个模型 2.503265619277954 **每一位都一样**；
  离手册解 2.5576 低 2.12%。

### assembly（装配）
```yaml
assembly:
  instances:
    - {name: Lower, part: Half, translate: [0.0, 0.0, 0.0]}
    - {name: Upper, part: Half, translate: [0.0, 5.0, 0.0]}
    - {name: Bolt,  part: Stud, translate: [0.0, -55.0, -5.0],
       rotate: {axis: [1.0, 0.0, 0.0], origin: [0.0, 0.0, 0.0], angle: -90.0}}
  operations:                 # 可选：对 rootAssembly 的通用调用
    - {call: RadialInstancePattern, instanceList: ["Bolt"], point: [0.0, 0.0, 0.0],
       axis: [0.0, 1.0, 0.0], number: 8, totalAngle: 360.0,
       creates: ["Bolt-rad-2", "Bolt-rad-3", "Bolt-rad-4", "Bolt-rad-5",
                 "Bolt-rad-6", "Bolt-rad-7", "Bolt-rad-8"]}
  expect:
    instances: 10
    at: [{instance: "Bolt-rad-3", centroid: [55.0, 7.5, 0.0], tol: 0.01}]
```
- 一个 part 可以实例化多次，实例名必须唯一；BC / 载荷 / 接触都按**实例名**点面。
- **translate 先于 rotate，两者不可交换**：先平移到 (0,-55,-5) 再绕 x 转 -90° 落在
  (0, 7.5, 55)，反过来落在 (0, 67.5, 5)。两个都是合法模型，都不报错。
- `number` 把原件算在内（8 = 原件 + 7 个副本，360° 里每 45° 一个），所以 instances 是
  3 个手摆的加 7 个阵列出来的 = 10。`at` 里的坐标必须自己推得出来：Bolt 落在
  (0, 7.5, 55)，绕 y 转 2×45° 就是 (55, 7.5, 0)。tol 是 0.01，抄一个别处的坐标只会
  让一个本来正确的装配中止。
- operations 会造出 spec 里没列过的实例，必须用 `creates:` 声明它们的名字，
  否则"合法的新实例"和"打错的实例名"就分不开了。
- assembly.expect 只认 instances / at / wires。实测装配摆错位时**实例数是对的、
  每个零件的体积面数全对、零报错**，只有 `at` 能看见——所以位置要明说。

### interactions（零件之间怎么连）
不写 = 零件之间力学上互不相干，这是合法模型，别自作主张补一个。

两名简写（tie / contact，最常用的两种）：
```yaml
interactions:
  - {name: MidPlane, type: tie, main: "Lower:face@y=max",
     secondary: "Upper:face@y=min", position_tolerance: 0.01}
  - {name: Interface, type: contact, main: "Base:face@y=max",
     secondary: "Slider:face@y=min", sliding: finite,
     property: {normal: hard, friction: 0.3, allow_separation: true}}
```
- tie 焊死（一起动、能传拉力）；contact 只能压、能滑、能分开。差别不是修辞：
  两层梁 tie 上按一个截面算，无摩擦接触各算各的，尖端挠度差 4 倍。
- **property 只有 contact 能带**；tie 带 property 会被拒——绑定是约束，
  没有摩擦也没有法向行为，收下只能是悄悄丢掉。
- friction 缺省 0（无摩擦），显式写出来：「故意无摩擦」和「压根没想过摩擦」是两个模型。
- tie 一定写 position_tolerance。超出容差的节点 Abaqus **不绑**，只在 .dat 里留一条
  WARNING，作业照样 COMPLETED，实测挠度错 7.95 倍——比根本不写 tie 还糟。

其他一切（Coupling / RigidBody / 通用接触 / 自接触 / MPC / 壳-实体耦合…）写成
Abaqus 方法名。方法挂在 model 上，它们连的区域属于装配：
```yaml
  - call: Tie
    name: {literal: MidPlane}
    main:      {surface: "Lower:face@y=max", name: BOND_MAIN, expect: "=1"}
    secondary: {surface: "Upper:face@y=min", name: BOND_SEC,  expect: "=1"}
    positionToleranceMethod: SPECIFIED
    positionTolerance: 0.01
    adjust: "OFF"
    expect: {gap: {max: 0.001}}
  - {call: ContactProperty, name: {literal: PROP}, as: prop}
  - {call: NormalBehavior, target: {ref: prop},
     pressureOverclosure: HARD, allowSeparation: "ON"}
  - call: SurfaceToSurfaceContactStd
    name: {literal: Pair}
    createStepName: {literal: Initial}
    main:      {surface: "Base:face@y=max",   name: PAIR_MAIN, expect: "=1"}
    secondary: {surface: "Slider:face@y=min", name: PAIR_SEC,  expect: "=1"}
    interactionProperty: {literal: PROP}
    sliding: FINITE
    expect: {gap: {max: 0.001}}
```
- 同一条里 `type` 和 `call` 只能有一个。
- **一次调用正好建了两个面，就必须写 expect.gap**（min / max 至少一个）。
  故意留间隙完全合法（`{min: 0.4, max: 0.6}`），要的是这个数被说出来并被核对。
- `as:` 绑住返回值，`target: {ref: <名字>}` 把后面的调用打到那个返回值上——
  NormalBehavior 是接触属性上的方法，model 上没有。通用接触还要
  `target: {ref: gc, attr: includedPairs}` 才够得着成员。
- main/secondary 与 master/slave 这边会自动改名重试，写哪个都行。

### steps（分析步，至少一个，按写的顺序跑）
命名简写：只能是 Static，自带 bcs 和 loads，previous 由生成器一步接一步串好，
顺序不可能错：
```yaml
steps:
  - name: Press
    type: Static             # 简写只有 Static
    time_period: 1.0
    initial_inc: 0.1
    min_inc: 1.0e-6
    max_num_inc: 200
    nlgeom: false
    bcs:
      - {name: Fix,   region: "Lower:face@z=min", type: encastre}
      - {name: HoldZ, region: "Slider:face@z=min", type: displacement, u3: 0.0}
    loads:
      - {name: Top, region: "Upper:face@y=max", type: pressure, value: 0.1}
```
- bcs.type 只能用 encastre | pinned | displacement | symmetry_x | symmetry_y |
  symmetry_z；displacement 至少给一个 u1/u2/u3。
- loads.type 只能用 pressure | concentrated_force。value 的符号是物理方向，
  **正压力是压进面里**（拉伸写负值）；concentrated_force 必须给 direction: 1|2|3，
  并且要写 points（见下面那条陷阱）。
- 同一个 name 在后一步再出现 = 同一个条件改值，region 必须一模一样。

Static 以外的分析步写成 Abaqus 方法名，这时边界条件和载荷搬到顶层 conditions：
```yaml
steps:
  - {call: StaticStep,    name: {literal: Press}, previous: {literal: Initial}}
  - {call: FrequencyStep, name: {literal: Modes}, previous: {literal: Press}, numEigen: 5}
```
还有 ImplicitDynamicsStep / ExplicitDynamicsStep / BuckleStep / HeatTransferStep /
ViscoStep / StaticRiksStep 等等，这一层不改代码就都能写。
- 派发形式的 name 必须是这边读得懂的字面量：`name: {literal: Press}`。
- ⚠️ **两个步都写 previous: Initial，两个都会被接受，而第二个被插到第一个前面**，
  分析整个反着跑，作业照样 COMPLETED。所以**第二步的 previous 必须写第一步的名字**，
  一步接一步串下去。
- 派发的步里不能写 bcs / loads / expect。

### conditions（边界条件 + 载荷 + 预定义场，配派发形式的步用）
Abaqus 不区分这三样——EncastreBC / DisplacementBC / VelocityBC / Pressure /
ConcentratedForce / Moment / SurfaceTraction / BodyForce / Gravity / Temperature
都是 model 上取 region 和 createStepName 的方法，所以它们同在一块：
```yaml
conditions:
  - call: EncastreBC
    name: {literal: Fix}
    createStepName: {literal: Initial}
    region: {set: "Bar:face@z=min", name: FIX, expect: "=1"}
  - call: ConcentratedForce
    name: {literal: Tip}
    createStepName: {literal: Press}
    region: {set: "Bar:vertices@z=max", name: TIP, expect: "=4"}
    cf2: -25.0
    expect: {points: 4}
  - call: Pressure
    name: {literal: Top}
    createStepName: {literal: Press}
    region: {surface: "Bar:face@y=max", name: TOP, expect: "=1"}
    magnitude: 0.1
  - call: SurfaceTraction
    name: {literal: Shear}
    createStepName: {literal: Press}
    region: {surface: "Bar:face@z=max", name: SHEAR, expect: "=1"}
    magnitude: 0.25
    directionVector: [[0.0, 0.0, 0.0], [0.0, -1.0, 0.0]]
    distributionType: UNIFORM
    traction: GENERAL
```
- 区域写 `{set: "<实例>:<kind>@<位置>", name: <集合名>, expect: "=N"}`（BC、集中力）
  或 `{surface: ...}`（压力、面牵引）。集合名会原样大写建在装配上。
- 两个 conditions **不许重名**：Abaqus 不报重复，它把前一个**整个替换掉**，
  只留后面那个的 region 和 step，第一步里一张边界卡都不剩，而且照样跑完。
  如果本意是「同一个条件在第二步改值」，那要写成
  `{call: setValuesInStep, target: {ref: <as 绑的名字>}, stepName: {literal: Two}, ...}`。
- ⚠️ **SurfaceTraction 没有 tr1/tr2/tr3**。方向靠 `directionVector`（两个点，向量从
  第一个指向第二个），大小靠 `magnitude`（单位是应力，总力 = magnitude × 受载面积），
  再加 `traction: GENERAL` 和 `distributionType: UNIFORM`。实测：照 cf2 类推写 `tr2`，
  CAE 停在 `keyword error on tr2`，.inp 根本不生成。
  **横向分布力用这个，不要用 Pressure**——Pressure 只能沿面法向，把「端面上向下压」
  写成 Pressure 就变成了沿梁轴的压缩，作业照样 COMPLETED（实测应力 0.47 MPa，
  而该有的是 15 MPa）。同一道题用上面这个 SurfaceTraction 写法实测得 15.72 MPa。
- ⚠️ **spec 里那个数不是载荷**：ConcentratedForce 的 cf1/cf2/cf3 是**每节点**
  写进 *Cload 的。实测 4 个角点上 cf2=-100，总载荷是 400 N（作业 COMPLETED、零警告）；
  同样 4 个点上 cf2=-25 才是 100 N。所以集中力必须做两件事：
  ①写 `expect: {points: N}` 声明它落在几个节点上；②spec 里那个数 = 总力 ÷ N。
  压力是按面积算的，没有这个问题。（命名简写里同一件事写成 `loads[].points: N`。）

### outputs（v2）
```yaml
outputs:
  regions:                        # 只为"量"而建的集合，不带任何条件
    - {name: HoleWall, region: "Plate:face@r=6"}
  kpis:
    - {name: HOOP_MAX, type: field_max, invariant: MISES, location: "REGION_HOLEWALL"}
    - {name: U_TIP,    type: field_min, location: whole_model, component: U2}
  field_variables: ["S", "E", "U", "RF"]
```
- outputs.regions 的 name 会建成装配集合 `REGION_<大写名>`，KPI 的 location 引它。
- location 也可以引条件建的集合：命名简写的 BC 是 `BC_<大写名>`、载荷是 `LOAD_<大写名>`，
  派发条件是你在 `{set: ..., name: X}` 里给的那个名字（大写）。
- **别拿 whole_model 当默认**：夹一端的板上最大 Mises 在夹持端而不在孔边，
  一个叫 HOOP_MAX 的 KPI 会安静地报夹持端的值。要量哪儿就先建哪儿的 region。
- field_max 的 KPI **名字里只要含 MISES 就一律按 Mises 读**（后处理按名字判定），
  这时 component 被忽略、不报错。要读某个分量（S22 之类）就别把 MISES 写进名字。
- field_variables 缺省是 ['S','E','U','RF']，那是应力分析要的。
  **传热步里 S/E/RF 根本不存在**，Abaqus 会拒掉整个输出请求、连 .inp 都不写——
  所以传热分析必须自己写 `field_variables: ["NT", "HFL"]`。变量名这边不校验，
  写错了 Abaqus 会指名道姓地拒。

### 通用调用的参数怎么写（parts / assembly.operations / interactions / steps / conditions 通用）
- 数字、列表原样传（列表变 tuple）。
- **全大写字符串 = abaqusConstants 符号**（生成的脚本 `from abaqusConstants import *`），
  所以 `sliding: FINITE`、`elemShape: TET`、`elemLibrary: STANDARD` 直接写裸词；
  不是符号就是一个把名字念出来的 NameError。真要传一个全大写的**字符串**
  （对象名之类）写 `{literal: RIM}`。
- **裸布尔值会被拒**：YAML 把裸 on/off/yes/no 读成 True/False，而 Abaqus 多数关键字
  要的是符号，所以写 `"ON"` / `"OFF"`（带引号）。同理键名也别用 on/off/yes/no，
  YAML 会把它们吃掉。少数关键字**真的**要 Python 布尔（实测
  `keywordBlock.synchVersions(storeNodesAndElements='OFF')` 会回
  `expecting False, True, 0 or 1`），那时写 `{bool: true}` 把话说明白。
- 一个映射里这 15 种形式**只能出现一种**，写两种会被指名拒绝：
  `{select: "edges@r=10", expect: "=2"}`  选一串几何实体（可带 expect 数个数）
  `{one: "face@z=max"}`                   正好一个实体——定位约束要的是单个面，
                                          给序列它会静默空转（螺栓停在原位、零报错）
  `{set: "<选择器>", name: FIX, expect: "=1"}`      建集合（BC、集中力、seam）
  `{surface: "<选择器>", name: TOP, expect: "=1"}`  建面（压力、接触、tie）
  `{named_set: FIX}`                      引用**前面某次调用建好的**集合，不重建
  `{reference_point: [0.0, 0.0, 100.0]}` 或 `{reference_point: {at: "Bar:vertex@z=max"},
   name: RP}`                             参考点（Coupling / RigidBody / MPC 要它）
  `{instance: Bolt}`                      引用一个实例对象本身
  `{vertex: {instance: Bar, at: [0.0, 0.0, 0.0]}}`  按坐标点一个顶点
  `{wire_at: [[0.0, 0.0, 0.0], [0.0, 0.0, 10.0]]}`  在两点之间连一根线（连接件）
  `{sketch: <id>}`                        引本零件先前画的草图
  `{datum: <名字>}` / `{ref: <名字>}`      引 `as:` 绑过的基准 / 任意返回值
  `{literal: RIM}`                        强制当字符串（不然全大写会被当符号）
  `{bool: true}`                          强制当 Python 布尔
  `{new: "mesh.ElemType", elemCode: C3D20R, elemLibrary: STANDARD}`  构造对象
                                          （可用模块：part, material, section,
                                          assembly, step, load, mesh, interaction,
                                          job, connectorBehavior）
- `{instance:}` / `{vertex:}` / `{wire_at:}` / `{reference_point:}` **只能写在装配域**
  （interactions / steps / conditions / assembly.operations）。零件特征跑在实例化之前，
  写在 parts 里会被指名拒绝。
- 另有 `{file: <路径>}`：相对 spec 文件所在目录解析，文件不存在当场拒。
- call 不能是下划线开头的名字。"""
