# SRP Model Converter

> 将 Minecraft 1.12.2 **Scape and Run: Parasites** (SRP) 模组的 Java `ModelRenderer` 模型转换为 Blockbench `.bbmodel` 格式，并生成 GeckoLib 兼容的动画。

## 项目背景

SRP（Scape and Run: Parasites）是 Minecraft 1.12.2 的知名寄生虫主题模组，由 Dhanantry 开发，CurseForge 下载量超过 2000 万。模组使用 Java `ModelRenderer` 系统渲染生物模型，通过 `setRotationAngles` 方法驱动骨骼动画。

本转换器解决的核心问题：**将 Java ModelRenderer 模型转换为 Blockbench 可编辑的 .bbmodel 格式**，使模组开发者能够在 Blockbench 中查看、编辑和移植 SRP 模型到其他 Minecraft 版本。

## 技术架构

### 转换流水线

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐    ┌──────────────┐
│  geo.json   │───▶│  BoneIR 解析  │───▶│  坐标变换   │───▶│  元素构建    │
│  .png 贴图  │    │  骨骼层级     │    │  RH → LH    │    │  UV 映射     │
└─────────────┘    └──────────────┘    └─────────────┘    └──────────────┘
                                                                │
┌─────────────┐    ┌──────────────┐    ┌─────────────┐         ▼
│  Java 源码  │───▶│  MVE 捕获    │───▶│  动画处理   │───▶┌──────────────┐
│  .anim.json │    │  代码级动作   │    │  频率吸附   │    │  .bbmodel    │
└─────────────┘    └──────────────┘    │  Catmullrom │    │  导出        │
                                       │  RDP 简化   │    └──────────────┘
                                       └─────────────┘
```

### 核心模块

| 模块 | 文件 | 功能 |
|------|------|------|
| **MVE 代码级动作捕捉** | `engine/mve_capture.py` | 从 Java `setRotationAngles` 提取 ground-truth 动画 |
| **Java 源码分析** | `engine/java_analyzer.py` | 状态机解析、变量提取、骨骼赋值提取 |
| **安全表达式求值** | `engine/safe_evaluator.py` | AST 限制的 Java 三角函数表达式求值 |
| **变量顺序处理** | `engine/java_analyzer.py` | 按源码顺序处理变量赋值（v6.9.6 修复） |
| **共享代码提取** | `engine/java_analyzer.py` | 提取状态 if/else 之后的共享动画代码 |
| **频率吸附** | `engine/frequency_snapper.py` | 检测正弦波频率，吸附到整数周期 |
| **Catmullrom 烘焙** | `engine/catmullrom_baker.py` | Catmullrom 曲线烘焙为线性关键帧 |
| **RDP 简化** | `engine/keyframe_simplifier.py` | Ramer-Douglas-Peucker 关键帧简化 |
| **Carry-forward** | `engine/carry_forward.py` | 插值感知的缺失轴值填充 |
| **Idle-Walk 合并** | `engine/idle_walk_merger.py` | 合并 idle 动画到 walk（模拟 GeckoLib 分层） |
| **Walk 增强** | `engine/walk_enhancer.py` | 生成合成行走运动 |
| **180° 旋转烘焙** | `backend/bbmodel_exporter.py` | 纯单轴 180° 旋转烘焙到立方体位置 |
| **FFT 频率验证** | `engine/fft_validator.py` | FFT 验证 MVE 捕获频率 vs Java 源码频率 |
| **Molang 符号化注入** | `engine/molang_injector.py` | 运行时变量映射为 GeckoLib Molang 表达式 |
| **分层循环** | `engine/layered_loop.py` | 按频率分组骨骼，每层独立最优循环长度 |
| **自适应采样** | `engine/mve_capture.py` | 基于 Nyquist 定理的自适应采样率 |
| **UV 面交换** | `backend/bbmodel_exporter.py` | 180° 旋转骨骼的 east/west UV 交换 |

## 关键技术

### 1. MVE 代码级动作捕捉 (Model Variable Evaluator)

MVE 是本转换器的核心创新。传统方法从 GeckoLib `.animation.json` 提取动画，但 SRP 的很多动画逻辑在 Java 代码中（`setRotationAngles` 方法），`.animation.json` 只捕获了部分骨骼。

MVE 工作原理：
1. 解析 Java 反编译源码中的 `setRotationAngles` 方法
2. 提取所有 `this.bone.field = expression` 赋值
3. 在多个时间点求值表达式，生成 ground-truth 关键帧
4. 处理变量声明、重新赋值、共享代码

**变量顺序处理** (v6.9.6)：Java 代码中变量可能被重新赋值（如 `f1` 先用于 idle 频率，后赋值为 state1 频率）。MVE 按源码顺序处理变量赋值和骨骼赋值，确保每个骨骼使用正确的变量值。

**共享代码提取**：Java 的 `setRotationAngles` 结构为：
```java
if (state == 0) { /* state 0 动画 */ }
else if (state == 1) { /* state 1 动画 */ }
// 共享代码：触手摆动（所有状态都执行）
jointLLD1.x = sin(ageInTicks * 0.199) * 0.05;
```
转换器提取每个状态的 if 块体 **并追加共享代码**，确保共享动画在所有状态中都被捕获。

### 2. 频率吸附与无缝循环

SRP 的触手/触须动画使用多个不可约分的正弦波频率（如 0.07, 0.0755, 0.0811, 0.0844 rad/tick）。没有任何单一动画长度能让所有频率完成整数周期。

频率吸附策略：
- 对每个骨骼轴拟合正弦波 `value = DC + A * sin(2πft + φ)`
- 搜索最优动画长度，最小化最大频率变化率
- 将每个频率吸附到最近的整数周期
- 对非正弦骨骼应用 smoothstep 边界混合

### 3. Catmullrom 插值

所有旋转通道使用 catmullrom 插值（而非 linear），通过关键帧点绘制平滑 C1 连续曲线，匹配原始正弦波形状，消除机械感。

### 4. 180° 旋转烘焙

部分骨骼有纯单轴 180° 旋转（如 `[0, 0, 180]`）。Blockbench 渲染时会镜像立方体，导致位置错误。转换器将 180° 旋转的镜像分量烘焙到立方体位置中，然后清零旋转。

规则（已对照参考文件验证）：
- Y=180°: 镜像 Z 绕枢轴
- Z=180°: 镜像 X 和 Y 绕枢轴
- X=180°: 镜像 Y 和 Z 绕枢轴
- 组合旋转（如 `[-180, 0, 180]`）保留不烘焙

### 5. getBODY() 运行时变量模拟

部分模型（如 venkrol 系列）使用 `parasite.getBODY()` —— 一个运行时增长的变量（0 → 0.6）。MVE 无法求值运行时方法调用。

解决方案：
- 对于循环 idle 动画，`getBODY()` 已达最大值（实体已完全生成）
- 使用 `body = body_max`（常数），只有正弦波组件动画
- 从上游 `animation.json` 的 `jointFL3.y` 提取 f3 值，用于计算腿部骨骼旋转

## 转换流程

### 单模型转换

```bash
python3 convert_model.py <category> <name>
# 示例: python3 convert_model.py deterrent dodT
# 示例: python3 convert_model.py feral ferEnderman
```

### 批量转换

```bash
python3 batch/mdo_srp.py
```

### 输出

转换后的 `.bbmodel` 文件保存在 `models/<category>/` 目录下。

## 项目结构

```
SubspaceParasite/
├── frontend/                    # 解析器
│   └── geckolib_parser.py       # 解析 .geo.json 和 .animation.json
├── engine/                      # 转换引擎
│   ├── mve_capture.py           # MVE 代码级动作捕捉
│   ├── java_analyzer.py         # Java 源码分析（状态机、变量、赋值）
│   ├── java_trig_simulator.py   # Java 三角函数模拟
│   ├── safe_evaluator.py        # 安全 AST 表达式求值
│   ├── carry_forward.py         # 插值感知的轴值填充
│   ├── idle_walk_merger.py      # Idle-Walk 动画合并
│   ├── walk_enhancer.py         # 行走动画增强
│   ├── frequency_snapper.py     # 频率吸附 + 边界混合
│   ├── catmullrom_baker.py      # Catmullrom 曲线烘焙
│   ├── keyframe_simplifier.py   # RDP 关键帧简化
│   ├── controller_generator.py  # 控制器生成
│   ├── head_tracking_injector.py# 头部跟踪注入
│   ├── runtime_behavior_injector.py # 运行时行为注入
│   └── mve_data_loader.py       # MVE 数据加载
├── backend/                     # 导出器
│   └── bbmodel_exporter.py      # .bbmodel 格式导出
├── batch/                       # 批量转换
│   └── mdo_srp.py               # 全量批量转换脚本
├── core/                        # 核心数据结构
│   ├── types.py                 # AnimationIR, BoneIR, KeyframeData
│   ├── quaternion.py            # 四元数旋转
│   └── math_utils.py            # 数学工具
├── convert_model.py             # 单模型转换脚本
├── config.py                    # 配置
└── MDO-SRP-SRC/                 # 源数据 (geo.json + animation.json + png)
```

## 版本历史

| 版本 | 主要改进 |
|------|----------|
| v6.9.17 | FFT 频率验证、自适应采样率、Molang 符号化注入、分层循环 |
| v6.9.16 | 共享代码提取修复（_extract_states 包含 if/else 后的共享动画） |
| v6.9.15 | 修复 fly mainbody 位置（移除错误 Z 旋转，使用正确 position） |
| v6.9.13 | 添加组合状态动画（idle_shaking, fly_vomit） |
| v6.9.12 | 振幅自适应 RDP + 移除速度平滑尖峰 |
| v6.9.11 | 精确 180° 旋转烘焙 + UV 面交换 |
| v6.9.10 | 纯单轴 180° 烘焙修复 |
| v6.9.8 | 频率吸附 + 边界混合 + 速度平滑 |
| v6.9.6 | 变量重新赋值 bug 修复（影响 146 个模型） |
| v6.9.5 | Catmullrom 插值（消除机械感） |
| v6.9.0 | RDP 关键帧简化 |

## 研究经验总结

### SRP 模型特点

1. **Java ModelRenderer 系统**：SRP 不使用 GeckoLib 的标准动画系统，而是通过 Java 代码直接操作 `ModelRenderer` 的 `rotateAngleX/Y/Z` 字段
2. **状态机驱动**：`getParasiteStatus()` 返回状态值（0/1/2/10/25/77），不同状态有不同的动画
3. **getStillAni 分支**：每个状态内分为行走（`!getStillAni()`）和闲置（`else`）两个分支
4. **共享代码**：状态 if/else 之后有共享的触手/身体摆动代码，所有状态都执行
5. **运行时变量**：`getBODY()`, `getFloorTimer()` 等运行时方法返回动态值，MVE 无法直接求值

### 转换器开发经验

1. **变量顺序至关重要**：Java 代码中变量可能被重新赋值，必须按源码顺序处理，否则所有骨骼会用最后一个赋值的频率
2. **共享代码不能遗漏**：状态 if/else 之后的共享代码包含大量触手/身体动画，必须追加到每个状态体
3. **Catmullrom > Linear**：对于正弦波驱动的动画，catmullrom 插值远优于 linear，消除机械感
4. **频率不可约分**：多个触手频率的比值是无理数，没有完美长度让所有频率循环。频率吸附 + 强制首末帧一致 + 速度连续性调整是最优方案
5. **180° 旋转需要烘焙**：纯单轴 180° 旋转会导致 Blockbench 双重镜像，必须烘焙到立方体位置
6. **UV 面交换**：180° 旋转骨骼需要交换 east/west 面 UV，但组合旋转不需要

### 已知限制

1. **运行时变量**：`getBODY()`, `getFloorTimer()` 等无法自动求值，需要手动模拟
2. **limbSwing 驱动**：行走动画的 `limbSwing` 参数依赖运行时移动速度，MVE 使用固定值 0.5 模拟
3. **头部跟踪**：`netHeadYaw` / `headPitch` 是运行时值，注入为 Molang 表达式
4. **不可约分频率**：多个触手频率无法完美循环，存在微小速度跳变（< 1°/s）

## 未来方向

### 短期
- [ ] 自动检测并模拟更多运行时变量（`getAttackTimer`, `shakingC` 等）
- [ ] 改进 MVE 对 `swingX/Y/Z` 辅助方法的参数解析
- [ ] 支持 SRP 1.10.7+ 新增模型

### 中期
- [ ] 转换为 GeckoLib 1.20+ 格式（直接用于新版本模组）
- [ ] 添加 Blockbench 插件前端，可视化转换流程
- [ ] 支持批量转换进度追踪和错误恢复

### 长期
- [ ] 通用化：支持其他 Minecraft 1.12.2 模组的 ModelRenderer → Blockbench 转换
- [ ] 逆向工程：从 `.bbmodel` 生成 Java `setRotationAngles` 代码
- [ ] AI 辅助：使用机器学习预测缺失的动画参数

## 许可

本转换器仅用于学习和研究目的。SRP 模组版权归 [Dhanantry](https://www.curseforge.com/minecraft/mc-mods/scape-and-run-parasites) 所有。

## 致谢

- **Dhanantry** — SRP 模组开发者
- **Blockbench** — 模型编辑工具
- **GeckoLib** — 动画库
- **CFR** — Java 反编译器
