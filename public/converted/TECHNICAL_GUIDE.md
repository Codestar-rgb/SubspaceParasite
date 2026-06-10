# MinecraftModelMigrator-Pro 技术指南

## 从 Minecraft 1.12.2 到 GeckoLib 1.20.1 的模型/动画迁移完全手册

---

> **版本**: 1.0.0  
> **适用范围**: Minecraft Mod 开发者、模型转换研究者、GeckoLib 迁移工程师  
> **项目背景**: 本项目源于将 Scape and Run Parasites (SRParasites) mod 的实体模型从 MC 1.12.2 迁移到 MC 1.20.1 + GeckoLib 4.x 的实际需求。经过 6+ 轮迭代调试、数十次 A/B 测试，最终实现了 98% 的视觉还原度。

---

## 目录

1. [项目概述](#1-项目概述)
2. [坐标系统深度分析](#2-坐标系统深度分析)
3. [模型转换管线](#3-模型转换管线)
4. [Blockbench .bbmodel 生成的坑](#4-blockbench-bbmodel-生成的坑)
5. [动画转换体系](#5-动画转换体系)
6. [UV 坐标处理](#6-uv-坐标处理)
7. [Mirror 镜像处理](#7-mirror-镜像处理)
8. [骨骼层级与轴心点](#8-骨骼层级与轴心点)
9. [常见陷阱与经验总结](#9-常见陷阱与经验总结)
10. [格式参考](#10-格式参考)
11. [扩展指南](#11-扩展指南)

---

## 1. 项目概述

### 1.1 问题定义

Minecraft 1.12.2 的实体模型使用 `ModelRenderer` 系统（Y 轴向下，右手坐标系），而 GeckoLib 1.20.1 使用 Bedrock Edition 的 geo.json 格式（Y 轴向上，左手坐标系）。两者之间存在根本性的坐标系差异，这使得直接迁移几乎不可能。

### 1.2 核心挑战

| 挑战 | 描述 | 难度 |
|------|------|------|
| 坐标系转换 | Y-down RH → Y-up LH，涉及位置、旋转、尺寸全方位变换 | ★★★★★ |
| 旋转顺序差异 | MC 1.12.2 X→Y→Z vs GeckoLib Z→Y→X | ★★★★☆ |
| 骨骼轴心点 | 绝对坐标 vs 相对坐标的转换 | ★★★★☆ |
| .bbmodel 格式 | Blockbench 内部格式与 geo.json 的微妙差异 | ★★★★★ |
| UV 映射 | 不同格式的 UV 表示方式不同 | ★★★☆☆ |
| 镜像处理 | mirror 标志在不同系统中的语义差异 | ★★★★☆ |
| SRG 混淆名 | 反编译代码中的方法/字段名混淆 | ★★★☆☆ |

### 1.3 项目架构

```
converter/
├── core_math.py              # 坐标变换数学库（M_model = diag(1,-1,-1)）
├── model_converter.py        # 模型转换引擎（Java → geo.json）
├── animation_converter.py    # 动画转换引擎（3 种动画类别）
├── bbmodel_generator.py      # Blockbench .bbmodel 生成器
├── verifier.py               # 验证系统（7 种验证检查）
├── cli.py                    # 命令行入口
├── run_kirin.py              # Kirin 实体转换脚本（21 步管线）
├── parsers/                  # 插件式解析器架构
│   ├── base_parser.py        # 解析器基类
│   ├── java_source_parser.py # Java 源码解析器
│   ├── bytecode_parser.py    # .class 字节码解析器
│   └── __init__.py           # ParserRegistry
├── templates/                # Jinja2 代码生成模板
│   ├── animation.json.j2     # 动画 JSON 模板
│   ├── java_model.java.j2    # GeoModel 类模板
│   ├── java_animation.java.j2 # 动画代码模板
│   ├── java_controller.java.j2 # AnimationController 模板
│   └── utility_class.java.j2  # 工具类模板
└── enhancements/             # 增强分析模块
    ├── render_effect_parser.py       # 渲染效果检测
    ├── easing_fitter.py              # 缓动拟合
    ├── swing_analyzer.py             # 摆动物理分析
    ├── animation_layer_separator.py  # 动画层分离
    ├── keyframe_event_marker.py      # 关键帧事件标记
    ├── dynamic_visibility_detector.py # 动态可见性检测
    └── layer1_deep/                  # 深层增强
        ├── overlay_detector.py       # 叠加层检测
        ├── firstperson_detector.py   # 第一人称检测
        ├── particle_detector.py      # 粒子挂载点检测
        ├── sound_keyframe_filler.py  # 音效关键帧填充
        ├── animation_naming_manager.py # 动画命名管理
        └── animation_reference_validator.py # 引用验证
```

---

## 2. 坐标系统深度分析

### 2.1 两个坐标系的根本差异

这是整个项目最核心、最难的部分。理解不透彻会导致模型完全错乱。

#### MC 1.12.2 ModelRenderer 坐标系

```
      Y (向下 ↓)
      |
      |
      +------ X (向右)
     /
    Z (向屏幕内，右手系)
```

- **Y 轴向下**：原点在实体碰撞箱顶部，Y 正方向朝脚
- **Z 轴向屏幕内**：右手坐标系
- **setRotationPoint(x, y, z)**：对顶级骨骼是绝对坐标，对子骨骼是相对于父骨骼的偏移

#### GeckoLib 1.20.1 geo.json 坐标系

```
      Y (向上 ↑)
      |
      |
      +------ X (向右)
     /
    Z (向屏幕外，左手系)
```

- **Y 轴向上**：原点在实体脚底，Y 正方向朝头
- **Z 轴向屏幕外**：左手坐标系（Bedrock 约定）
- **bone.pivot**：始终相对于父骨骼坐标系

### 2.2 变换矩阵推导

从 MC 1.12.2 到 GeckoLib 需要两个变换：

1. **Y 轴翻转**：Y-down → Y-up
2. **Z 轴翻转**：右手系 → 左手系

合并变换矩阵：

```
M_model = diag(1, -1, -1) = | 1   0   0 |
                              | 0  -1   0 |
                              | 0   0  -1 |
```

**关键性质**：M_model 是自逆矩阵（M_model² = I），这意味着正向和逆向变换相同。

### 2.3 位置变换

```
P_GeckoLib = M_model × P_MC1122 = (x, -y, -z)
```

示例：
- MC 1.12.2 中 pivot (5, 12, 3) → GeckoLib (5, -12, -3)
- 需要额外 +24 Y 偏移（根骨骼位置）来对齐原点

### 2.4 旋转变换

旋转变换通过相似变换推导：

```
R' = M_model × R × M_model⁻¹
```

对于单轴旋转：

| 轴 | MC 1.12.2 角度 | GeckoLib 角度 | 变换规则 |
|----|----------------|---------------|----------|
| X  | θ              | θ             | **不变** |
| Y  | φ              | -φ            | **取反** |
| Z  | ψ              | -ψ            | **取反** |

即：`(rx, ry, rz) → (rx, -ry, -rz)`

#### 为什么 X 不取反而 Y、Z 取反？

通过矩阵相似变换严格证明：

**X 轴旋转**（X 轴不受 M_model 影响）：
```
M_model × Rx(θ) × M_model = Rx(θ)  // X 轴旋转不变
```

**Y 轴旋转**（Y 轴被翻转）：
```
M_model × Ry(φ) × M_model = Ry(-φ)  // Y 轴旋转取反
```

**Z 轴旋转**（Z 轴被翻转）：
```
M_model × Rz(ψ) × M_model = Rz(-ψ)  // Z 轴旋转取反
```

### 2.5 旋转顺序的关键发现

**这是本项目最重要的发现之一**。

MC 1.12.2 和 GeckoLib 都使用 **Z→Y→X 的外旋等价于 X→Y→Z 的内旋** 旋转应用顺序：

```
R = Rz(rz) × Ry(ry) × Rx(rx)
```

因为两者使用相同的旋转顺序，M_model 的相似变换可以因式分解：

```
M × (Rz × Ry × Rx) × M = (M×Rz×M) × (M×Ry×M) × (M×Rx×M)
                        = Rz(-rz) × Ry(-ry) × Rx(rx)
```

**这意味着简单的角度变换 `(rx, -ry, -rz)` 对所有情况都是精确的**，包括多轴旋转！不需要矩阵分解。

> ⚠️ **历史教训**：早期版本使用了 `convert_model_rotation_order()` 进行矩阵分解，但分解目标设定为 `Rx × Ry × Rz`（错误的旋转顺序约定），导致多轴旋转出现约 180° 的误差。后来确认旋转顺序相同时，直接使用简单角度变换即可。

### 2.6 方块原点变换

MC 1.12.2 `addBox(ox, oy, oz, w, h, d)` 创建的方块占据：
- X: [ox, ox+w]
- Y: [oy, oy+h]（Y-down）
- Z: [oz, oz+d]（Z into screen）

经过 M_model 变换后：
- X: [ox, ox+w]（不变）
- Y: [-(oy+h), -oy]（翻转，最小角在 -(oy+h)）
- Z: [-(oz+d), -oz]（翻转，最小角在 -(oz+d)）

GeckoLib 格式要求 `origin` 为最小角，因此：

```
new_origin = (ox, -(oy+h), -(oz+d))
new_size   = (w, h, d)  // 尺寸不变
```

**负尺寸处理**：当 h < 0 或 d < 0 时，最小角计算不同：
- h < 0: new_origin_y = -oy（而非 -(oy+h)）
- d < 0: new_origin_z = -oz（而非 -(oz+d)）

---

## 3. 模型转换管线

### 3.1 转换流程

```
Java Source (.java)          .class Bytecode
       │                          │
       ▼                          ▼
  Text Parser              Bytecode Parser
  (SRG Name Resolution)    (Constant Pool → CFR Decompile)
       │                          │
       └──────────┬───────────────┘
                  ▼
         BoneData Hierarchy
                  │
                  ▼
     Coordinate Conversion (M_model)
                  │
                  ▼
         .geo.json (Game Format)
          │              │
          ▼              ▼
  Blockbench Format   .bbmodel Format
  (minecraft:geometry) (Blockbench Project)
```

### 3.2 SRG 名称映射

反编译的 MC 1.12.2 代码使用混淆名，需要映射到可读名称：

| SRG 名称 | 可读名称 | 用途 |
|----------|---------|------|
| `func_78793_a` | `setRotationPoint` | 设置骨骼旋转点 |
| `func_78790_a` | `addBox` | 添加方块 |
| `func_78792_a` | `addChild` | 添加子骨骼 |
| `field_78795_f` | `rotateAngleX` | X 轴旋转角度 |
| `field_78796_g` | `rotateAngleY` | Y 轴旋转角度 |
| `field_78808_h` | `rotateAngleZ` | Z 轴旋转角度 |
| `field_78809_i` | `mirror` | 镜像标志 |
| `field_78090_t` | `textureWidth` | 纹理宽度 |
| `field_78089_u` | `textureHeight` | 纹理高度 |

### 3.3 解析器插件架构

项目使用插件式解析器架构，通过 `ParserRegistry` 管理：

```python
from parsers import ParserRegistry

registry = ParserRegistry()

# 自动检测：.java → JavaSourceModelParser, .class → BytecodeModelParser
result = registry.parse_model(source_path_or_text)

# 显式指定解析器
result = registry.parse_model(source, parser_name="bytecode")
```

---

## 4. Blockbench .bbmodel 生成的坑

> **这是整个项目调试最久的部分**，经历了 6+ 轮迭代，从"不可名状的镜像堆叠物"到 98% 还原度。

### 4.1 Round 1-4：坐标方案的反复试错

前 4 轮的核心问题是：**.bbmodel 到底使用什么坐标系？**

我们尝试了：
1. **骨局部坐标**（相对坐标）→ 方块堆成一堆
2. **绝对世界坐标** → 方块散开（双倍偏移）
3. **带 X 翻转的绝对坐标** → 镜像不可名状物
4. **带 X 翻转的相对坐标** → 高度 y≈-12 的镜像物

### 4.2 Round 5 突破：model_format = "bedrock"

**关键发现**：.bbmodel 的 `meta.model_format` 决定了坐标系约定！

```json
{
  "meta": {
    "model_format": "bedrock"  // 不是 "free"!
  }
}
```

- `"free"` 格式：Blockbench 使用 Three.js 右手坐标系渲染，不执行 Bedrock 坐标变换
- `"bedrock"` 格式：Blockbench 使用 Bedrock 左手坐标系，内部自动处理 LH→RH 渲染转换

**选择 "bedrock" 的原因**：我们的数据来自 geo.json，已经是 Bedrock LH 坐标系。使用 "bedrock" 格式可以避免额外的坐标变换。

### 4.3 Round 5-6：坐标约定的最终确定

当 `model_format = "bedrock"` 时，.bbmodel 的坐标约定为：

| 数据 | 坐标系 | 说明 |
|------|--------|------|
| 元素 from/to | **绝对世界坐标** | abs_pivot[bone] + cube.origin/size |
| 元素 origin | **绝对世界坐标** | abs_pivot[bone]（旋转中心 = 骨骼轴心） |
| 骨骼 origin | **绝对世界坐标** | Blockbench 通过 child.origin - parent.origin 计算相对偏移 |
| 骨骼 rotation | **geo.json 原值** | 不需要额外变换 |

**关键理解**：Blockbench .bbmodel 中所有坐标都是绝对的！Blockbench 内部通过 `mesh.position = group.origin - parent.origin` 来计算相对偏移。因此，我们存储的 origin 必须是绝对坐标，这样减法才能得到正确的相对偏移。

### 4.4 X 翻转的教训

**最重要的教训之一**：**.bbmodel 不需要 X 翻转**。

X 翻转只发生在 .geo.json 的导入/导出过程中（Blockbench 在导出为 .geo.json 时自动应用 X 翻转来匹配 Bedrock 的渲染约定）。但 .bbmodel 是 Blockbench 的内部格式，直接使用 Bedrock 坐标系，不需要 X 翻转。

```
.geo.json 导入/导出: 需要 X-flip（Blockbench 自动处理）
.bbmodel 内部格式:   不需要 X-flip（直接使用 Bedrock LH 坐标）
```

### 4.5 旋转的双重转换 Bug

在 Round 5 中发现翅膀旋转方向反转的 Bug：

**根因**：代码对旋转应用了双重转换。

1. `model_converter.py` 已经将 MC 1.12.2 旋转转换为 Bedrock LH 约定：`(rx, -ry, -rz)`
2. `bbmodel_generator.py` 又应用了一次 `(rx, -ry, -rz)`：结果变成 `(rx, ry, rz)` — 完全反转！

**修复**：.bbmodel with `model_format="bedrock"` 使用与 geo.json 相同的 Bedrock LH 旋转约定，直接使用 geo.json 的旋转值，不做任何转换。

**为什么大多数骨骼看起来正确**：
- 纯 X 旋转：`(rx, 0, 0) → (rx, 0, 0)` — 不变 ✓
- Z 旋转 ±180°：`(0, 0, ±180) → (0, 0, ∓180) ≡ (0, 0, ±180)` — 不变 ✓
- Y 旋转 ±180°：同理不变 ✓
- **但非 ±180° 的 Y/Z 旋转会反转**（翅膀、触手、牙齿等）

### 4.6 绝对轴心点计算

.bbmodel 需要绝对轴心点，但 geo.json 中的 pivot 是相对的。需要沿骨骼层级累加：

```python
def _compute_absolute_pivots(bones):
    """沿骨骼层级计算绝对世界坐标轴心点"""
    for root_bone in root_bones:
        abs_pivot = root_bone.pivot  # 根骨骼的 pivot 就是绝对的
        for child in children:
            child_abs = abs_pivot + child.pivot  # 累加
            # 递归处理孙子骨骼...
```

---

## 5. 动画转换体系

### 5.1 动画类别分类

| 类别 | 驱动源 | 输出格式 | 示例 |
|------|--------|----------|------|
| **Class A-1** | `ageInTicks`（时间驱动） | .animation.json | 空闲呼吸动画 |
| **Class A-2** | `limbSwing`（运动驱动） | Java 代码 (GeoBone API) | 行走摆动动画 |
| **Class B** | 实体状态（状态机） | AnimationController Java 代码 | 攻击/受伤/死亡切换 |

### 5.2 Class A-1 转换方法

时间驱动动画使用**数值采样法**：

1. 识别 `ageInTicks` 依赖的表达式
2. 在 2π 周期内采样 120 个点
3. 应用旋转变换 `(rx, -ry, -rz)` 到采样值
4. 使用 Douglas-Peucker 算法简化关键帧（阈值 0.01°）
5. 生成 .animation.json 格式

```
原始 Java: this.bone.field_78795_f = MathHelper.cos(ageInTicks * 0.13f) * 0.107f;
                    ↓ 采样 + 变换
.animation.json: "rotation": { "x": { "0.0000": 6.13, "0.5236": 3.07, ... } }
```

### 5.3 Class A-2 转换方法

运动驱动动画生成**可编译的 Java 代码**：

```java
// 自动生成的 GeckoLib 动画代码
float limbSwing = animatable.limbSwing;
float limbSwingAmount = animatable.limbSwingAmount;

GeoBone legBone = this.getAnimationProcessor().getBone("leg");
if (legBone != null) {
    legBone.setRotationX((float)(Math.cos(limbSwing * 0.6662f) * limbSwingAmount));
    legBone.setRotationZ((float)(-(Math.sin(limbSwing * 0.6662f) * limbSwingAmount)));  // Z 取反
}
```

### 5.4 缓动拟合

使用最小二乘法将采样数据拟合到 GeckoLib 支持的缓动类型：

- `linear`（线性）
- `ease_in_quad` / `ease_out_quad` / `ease_in_out_quad`
- `ease_in_cubic` / `ease_out_cubic` / `ease_in_out_cubic`
- 等等

### 5.5 动画旋转变换

动画中的旋转值也需要 M_model 变换：

```
animation_rx = rx       // X 不变
animation_ry = -ry      // Y 取反
animation_rz = -rz      // Z 取反
```

这与模型旋转的变换规则一致。

---

## 6. UV 坐标处理

### 6.1 MC 1.12.2 UV 计算公式

标准 Minecraft 1.12.2 UV 布局（addBox 的纹理偏移 u, v，方块尺寸 w, h, d）：

| 面 | UV 起点 | UV 尺寸 |
|----|---------|---------|
| North | (u+d, v+d) | (w, h) |
| South | (u+2d+w, v+d) | (w, h) |
| West | (u, v+d) | (d, h) |
| East | (u+d+w, v+d) | (d, h) |
| Up | (u+d, v) | (w, d) |
| Down | (u+d+w, v) | (w, d) |

### 6.2 geo.json UV 格式

```json
{
  "north": { "uv": [u+d, v+d], "uv_size": [w, h] },
  "south": { "uv": [u+2d+w, v+d], "uv_size": [w, h] }
}
```

### 6.3 .bbmodel UV 格式

```json
{
  "north": { "uv": [u+d, v+d, u+d+w, v+d+h], "texture": 0 },
  "south": { "uv": [u+2d+w, v+d, u+2d+2w, v+d+h], "texture": 0 }
}
```

**转换公式**：`{uv:[u,v], uv_size:[w,h]} → {uv:[u, v, u+w, v+h]}`

### 6.4 重要：纹理坐标不需要坐标变换

UV 坐标是纹理空间的 2D 坐标，与 3D 坐标系无关。M_model 变换不影响 UV 计算。

---

## 7. Mirror 镜像处理

### 7.1 MC 1.12.2 的镜像

MC 1.12.2 中 `mirror = true` 导致 `GlStateManager.scale(-1, 1, 1)`，在 X 轴方向翻转整个方块。

### 7.2 GeckoLib 的镜像

GeckoLib 的 `mirror: true` 属性执行相同的 X 轴翻转，并自动交换 west/east 面的渲染和翻转 UV。

### 7.3 关键规则：不要双重镜像

**错误做法**（早期版本的 Bug）：
```python
# 交换 west/east UV 坐标 AND 设置 mirror=True → 双重镜像！
uv['west'] = east_uv  # 手动交换
uv['east'] = west_uv  # 手动交换
cube["mirror"] = True  # GeckoLib 又会再翻转一次
```

**正确做法**：
```python
# 只设置 mirror 标志，不交换 UV
cube["mirror"] = True  # GeckoLib 自动处理 X 翻转和 UV
```

### 7.4 .bbmodel 中的镜像

在 .bbmodel 中，镜像通过 `mirror_uv` 字段表示：

```json
{
  "mirror_uv": true  // 对应 geo.json 的 mirror: true
}
```

---

## 8. 骨骼层级与轴心点

### 8.1 轴心点的相对性

**MC 1.12.2**：
- 顶级骨骼：`setRotationPoint` 是绝对坐标（相对于模型原点）
- 子骨骼：`setRotationPoint` 是相对于父骨骼旋转后的坐标空间

**GeckoLib**：
- 所有骨骼的 `pivot` 都相对于父骨骼坐标系
- 根骨骼 pivot = [0, 24, 0]（标准实体原点）

### 8.2 相对轴心点计算

对于顶级骨骼（parent = "root"）：

```
bone.pivot = convert_model_pos(abs_pivot)  // 不需要减去 root.pivot！
```

**关键理解**：

```
abs_GL = convert_model_pos(abs_MC) + (0, 24, 0)  // GL 世界坐标
root_GL = (0, 24, 0)                               // 根骨骼 GL 坐标
rel = abs_GL - root_GL = convert_model_pos(abs_MC) // +24 抵消了！
```

对于子骨骼（parent ≠ "root"）：

```
rel_pivot = convert_model_pos(bone_abs) - convert_model_pos(parent_abs)
```

由于 M_model 是线性变换（无平移），+24 在减法中抵消。

### 8.3 子骨骼旋转对位置的影响

**重要**：MC 1.12.2 中子骨骼的 `setRotationPoint` 是相对于父骨骼**旋转后**的坐标空间。真正的绝对位置需要：

```
child_abs = parent_abs + R_parent × child_relative
```

然而，对于 GeckoLib 的相对轴心点计算，由于 M_model 的线性性质：

```
M × (parent + R × child_rel) = M × parent + (M × R × M⁻¹) × (M × child_rel)
```

这意味着 `child.pivot = M × child_rel = convert_model_pos(srp)`，与父骨骼的旋转无关！

---

## 9. 常见陷阱与经验总结

### 9.1 坐标系陷阱

| 陷阱 | 症状 | 原因 | 解决方案 |
|------|------|------|----------|
| Z 原点偏移 | 所有方块在 Z 方向偏移 | 使用 `-oz` 而非 `-(oz+d)` | 使用 `convert_model_cube_origin` |
| Y 原点偏移 | 模型悬浮或下沉 | 忘记 +24 Y 偏移或错误减去 | 正确计算相对轴心点 |
| X 翻转误用 | .bbmodel 镜像错乱 | 对 .bbmodel 应用了 X-flip | .bbmodel 不需要 X-flip |
| 绝对/相对混淆 | .bbmodel 方块散开或堆叠 | 混用绝对和相对坐标 | .bbmodel 使用绝对世界坐标 |

### 9.2 旋转陷阱

| 陷阱 | 症状 | 原因 | 解决方案 |
|------|------|------|----------|
| 双重旋转转换 | 翅膀/触手旋转反了 | 对 geo.json 旋转再次应用 M_model | .bbmodel 直接使用 geo.json 旋转 |
| 旋转顺序错误 | 多轴旋转约 180° 偏差 | 矩阵分解使用错误的旋转顺序 | 简单角度变换 `(rx, -ry, -rz)` 即可 |
| 度/弧度混淆 | 旋转角度异常 | geo.json 用度，Java 用弧度 | 注意 `rad_to_deg` 转换 |

### 9.3 格式陷阱

| 陷阱 | 症状 | 原因 | 解决方案 |
|------|------|------|----------|
| model_format 错误 | Blockbench 以方块模型打开 | 缺少 `model_format: "bedrock"` | 设置正确的 model_format |
| UV 格式错误 | 纹理映射错乱 | 混用 `[u,v,w,h]` 和 `[u1,v1,u2,v2]` | geo.json 用前者，.bbmodel 用后者 |
| 镜像双重翻转 | 镜像骨骼纹理错误 | 同时交换 UV 和设 mirror=True | 只设 mirror=True |
| visible_box 太小 | 模型在视口中不可见 | 默认 visible_box 太小 | 根据模型边界框计算 |

### 9.4 调试方法论

1. **创建最简测试用例**：用一个 2×2×2 的方块在已知位置测试坐标系
2. **A/B 对比测试**：生成多个版本，在 Blockbench 中逐一打开对比
3. **逐步验证**：先验证位置，再验证旋转，最后验证 UV
4. **检查 Blockbench 内部值**：在 Blockbench 中手动检查骨骼的 pivot、rotation、cube 的 from/to
5. **数学推导优先**：遇到坐标问题先做数学推导，不要盲目试错

### 9.5 性能优化经验

- 使用 `dict` 代替 `list` 进行关键帧查找：O(1) vs O(n)
- Douglas-Peucker 阈值 0.01° 在精度和文件大小间取得良好平衡
- 120 个采样点对 2π 周期动画足够（更高采样数不会显著提升质量）

---

## 10. 格式参考

### 10.1 geo.json (Game Format)

```json
{
  "format_version": "1.12.0",
  "model": {
    "identifier": "model.kirin",
    "texture_width": 256,
    "texture_height": 256,
    "bones": [
      {
        "name": "root",
        "pivot": [0, 24, 0]
      },
      {
        "name": "mainbody",
        "parent": "root",
        "pivot": [0, 53, 16],
        "rotation": [25, 0, 180],
        "cubes": [
          {
            "origin": [-9.5, -21, -5],
            "size": [19, 24, 10],
            "uv": {
              "north": { "uv": [80, 80], "uv_size": [19, 24] },
              "south": { "uv": [80, 80], "uv_size": [19, 24] }
            },
            "mirror": true
          }
        ]
      }
    ]
  }
}
```

### 10.2 geo.json (Blockbench Preview Format)

```json
{
  "format_version": "1.12.0",
  "minecraft:geometry": [{
    "description": {
      "identifier": "model.kirin",
      "texture_width": 256,
      "texture_height": 256,
      "visible_bounds_width": 10,
      "visible_bounds_height": 10,
      "visible_bounds_offset": [0, 2, 0]
    },
    "bones": [ /* 同 game format */ ]
  }]
}
```

### 10.3 .bbmodel (Blockbench Project)

```json
{
  "meta": {
    "format_version": "4.10",
    "model_format": "bedrock",
    "box_uv": false
  },
  "name": "kirin",
  "resolution": { "width": 256, "height": 256 },
  "elements": [
    {
      "name": "mainbody_c0",
      "type": "cube",
      "from": [-9.5, 56.5, 11.0],     // 绝对世界坐标
      "to": [9.5, 80.5, 21.0],         // 绝对世界坐标
      "origin": [0.0, 77.0, 16.0],     // 绝对世界坐标（= 骨骼轴心）
      "rotation": [0, 0, 0],
      "faces": {
        "north": { "uv": [80, 80, 99, 104], "texture": 0 }
      }
    }
  ],
  "outliner": [
    {
      "name": "root",
      "origin": [0, 24, 0],           // 绝对世界坐标
      "rotation": [0, 0, 0],
      "children": [
        {
          "name": "mainbody",
          "origin": [0, 77, 16],       // 绝对世界坐标
          "rotation": [25, 0, 180]      // geo.json 原值，不转换
        }
      ]
    }
  ],
  "textures": [
    {
      "name": "kirin",
      "source": "data:image/png;base64,..."
    }
  ]
}
```

### 10.4 .animation.json

```json
{
  "format_version": "1.8.0",
  "animations": {
    "animation.srparasites.kirin.idle": {
      "loop": "hold_on_last_frame",
      "animation_length": 6.2832,
      "bones": {
        "mainbody": {
          "rotation": {
            "x": {
              "0.0000": { "vector": [25.0], "easing": "linear" },
              "1.5708": { "vector": [25.5], "easing": "ease_in_out_quad" }
            }
          }
        }
      }
    }
  }
}
```

---

## 11. 扩展指南

### 11.1 添加新实体

1. 准备反编译的 Java 源码或 .class 文件
2. 确认 SRG 名称映射（使用 bytecode_parser 自动检测）
3. 创建类似 `run_kirin.py` 的运行脚本
4. 配置实体特定参数（纹理路径、动画名称等）
5. 运行转换管线
6. 在 Blockbench 中打开 .bbmodel 文件验证

### 11.2 自定义解析器

```python
from parsers import BaseModelSourceParser, ParserRegistry

class CustomModelParser(BaseModelSourceParser):
    def parse_model(self, source, **kwargs):
        # 实现自定义解析逻辑
        return {
            'bones': [...],
            'texture_width': 256,
            'texture_height': 256,
            'warnings': []
        }

# 注册到 ParserRegistry
registry = ParserRegistry()
registry.register_model_parser("custom", CustomModelParser, extensions=[".custom"])
```

### 11.3 增强模块开发

增强模块遵循统一的接口模式：

```python
class CustomEnhancer:
    def __init__(self, bone_mapping):
        self.bone_mapping = bone_mapping
    
    def analyze(self, model_source, render_source):
        """分析并返回增强数据"""
        result = CustomResult()
        # ... 分析逻辑
        return result
```

### 11.4 验证系统扩展

```python
from verifier import ModelVerifier

class ExtendedVerifier(ModelVerifier):
    def check_custom_property(self, geo_json):
        """添加自定义验证检查"""
        issues = []
        # ... 验证逻辑
        return {'passed': len(issues) == 0, 'issues': issues}
```

---

## 附录 A：坐标变换速查表

### 位置变换

| 数据 | MC 1.12.2 | GeckoLib | 公式 |
|------|-----------|----------|------|
| 骨骼 pivot | (px, py, pz) | (px, -py, -pz) | `convert_model_pos` |
| 方块 origin | (ox, oy, oz) | (ox, -(oy+h), -(oz+d)) | `convert_model_cube_origin` |
| 方块 size | (w, h, d) | (w, h, d) | `convert_model_cube_size` |

### 旋转变换

| 数据 | MC 1.12.2 | GeckoLib | 公式 |
|------|-----------|----------|------|
| 骨骼 rotation | (rx, ry, rz) | (rx, -ry, -rz) | `convert_model_rot` |
| 动画 rotation | (rx, ry, rz) | (rx, -ry, -rz) | 同上 |

### .bbmodel 特殊规则

| 数据 | geo.json 值 | .bbmodel 值 | 说明 |
|------|-------------|-------------|------|
| 元素 from/to | 骨局部坐标 | 绝对世界坐标 | abs_pivot + cube.origin/size |
| 元素 origin | 骨骼 pivot | 绝对世界坐标 | abs_pivot[bone] |
| 骨骼 origin | 相对 pivot | 绝对世界坐标 | Blockbench 自动计算相对偏移 |
| 骨骼 rotation | geo.json 原值 | geo.json 原值 | **不做任何转换** |
| UV | [u, v, w, h] | [u1, v1, u2, v2] | 格式转换 |
| Mirror | `mirror: true` | `mirror_uv: true` | 字段名不同 |

---

## 附录 B：SRG 名称完整映射

```python
SRG_MAP = {
    # ModelRenderer 方法
    'func_78793_a': 'setRotationPoint',   # setRotationPoint(x, y, z)
    'func_78790_a': 'addBox',              # addBox(offX, offY, offZ, w, h, d, inflate?)
    'func_78792_a': 'addChild',            # addChild(child)
    'func_78785_a': 'render',              # render(scale)
    
    # ModelRenderer 字段
    'field_78795_f': 'rotateAngleX',       # X 轴旋转角度（弧度）
    'field_78796_g': 'rotateAngleY',       # Y 轴旋转角度（弧度）
    'field_78808_h': 'rotateAngleZ',       # Z 轴旋转角度（弧度）
    'field_78809_i': 'mirror',             # 镜像标志
    'field_82906_o': 'offsetX',            # X 偏移
    'field_82907_q': 'offsetY',            # Y 偏移
    'field_82908_p': 'offsetZ',            # Z 偏移
    
    # ModelBase 字段
    'field_78090_t': 'textureWidth',       # 纹理宽度
    'field_78089_u': 'textureHeight',      # 纹理高度
    
    # MathHelper 方法
    'func_76134_b': 'cos',                 # MathHelper.cos
    'func_76126_a': 'sin',                 # MathHelper.sin
    'func_76133_a': 'sin',                 # MathHelper.sin (备用 SRG)
    'func_76129_a': 'sqrt',                # MathHelper.sqrt
    'func_76130_a': 'sqrt',                # MathHelper.sqrt (备用 SRG)
    'func_76142_g': 'floor',               # MathHelper.floor
    'func_76128_c': 'abs',                 # MathHelper.abs
    'func_76131_a': 'clamp',               # MathHelper.clamp
    
    # ModelBase 方法
    'func_78087_a': 'setRotationAngles',   # setRotationAngles
    'func_78088_a': 'animate',             # animate
}
```

---

## 附录 C：Blockbench 渲染链验证

以下验证了 .bbmodel 中绝对坐标的正确性：

**场景**：骨骼在 [0,24,0]（root），子骨骼在 [0,53,16]（mainbody，相对 root），方块从 [-9.5,-21,-5] 到 [9.5,3,5]（相对于 mainbody）

**.bbmodel 中的值**：
- root origin: [0, 24, 0]
- mainbody origin: [0, 77, 0+16+11=0+53+24=77, 16]  (绝对坐标)

**Blockbench 渲染计算**：
1. root mesh.position = root.origin = [0, 24, 0]
2. mainbody mesh.position = mainbody.origin - root.origin = [0, 53, 16] ✓
3. cube mesh.position = cube.origin - mainbody.origin = [0, 0, 0]
4. cube geometry = (from-origin) to (to-origin) = [-9.5, -21, -5] to [9.5, 3, 5]
5. 世界位置 = [0,24,0] + [0,53,16] + [0,0,0] + [-9.5,-21,-5] = [-9.5, 56, 11] ✓

---

## 附录 D：项目开发历程与关键转折点

| 阶段 | 描述 | 关键发现 |
|------|------|----------|
| Phase 1 | 基础转换管线搭建 | M_model = diag(1,-1,-1) 变换矩阵 |
| Phase 2 | Z 原点 Bug 修复 | cube origin Z 应为 -(oz+d) 非 -oz |
| Phase 3 | UV 格式修正 | minecraft:geometry 使用相同 UV 格式 |
| Phase 4 | Mirror 双重翻转修复 | 不应手动交换 UV，只设 mirror 标志 |
| Phase 5 | 相对轴心点修复 | 顶级骨骼 pivot 需相对于 root.pivot |
| Phase 6 | .bbmodel 格式探索 | 6+ 轮迭代，最终确定 bedrock 格式 + 绝对坐标 |
| Phase 7 | 旋转双重转换修复 | .bbmodel 不需要额外旋转变换 |
| Phase 8 | 增强模块开发 | 12 项视觉/动画保真度增强 |
| Phase 9 | 深层增强 | 6 项深层增强（叠加层、粒子、音效等） |
| Phase 10 | 细节优化 | 98% 还原度，微调翅膀/触手/嘴部细节 |

---

> **致后来者**：如果你正在阅读这份文档，说明你可能也面临着类似的 Minecraft 模型迁移挑战。请记住，坐标系转换是数学问题，不是试错问题。先做严格的数学推导，再写代码。当模型看起来"几乎对但有点怪"时，99% 的情况是某个坐标变换被多应用或少应用了一次。祝你好运！
>
> — MinecraftModelMigrator-Pro 开发团队
