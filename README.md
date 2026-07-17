# SRP Model Converter

将 Minecraft 1.12.2 **Scape and Run: Parasites** (SRP) 模组的 Java `ModelRenderer` 模型转换为 Blockbench `.bbmodel` 格式，并生成 GeckoLib 兼容的动画。

## 概述

本转换器读取 SRP 模组的反编译 Java 源码、GeckoLib `.geo.json` / `.animation.json` 文件和纹理贴图，通过 MVE (Model Variable Evaluator) 代码级动作捕捉技术，从 Java `setRotationAngles` 方法中提取骨骼动画数据，生成可直接在 Blockbench 中打开和编辑的 `.bbmodel` 项目文件。

## 特性

### 核心转换
- **Java ModelRenderer → Blockbench 骨骼**: 完整转换骨骼层级、旋转、枢轴点
- **Per-face UV 映射**: 正确处理负 uv_size 翻转和 180° 旋转面交换
- **RH→LH 坐标变换**: Minecraft 右手坐标系 → Blockbench 左手坐标系
- **纹理嵌入**: 自动将 PNG 纹理嵌入 .bbmodel 文件

### 动画系统
- **MVE 代码级动作捕捉**: 从 Java `setRotationAngles` 提取 ground-truth 动画
- **变量顺序处理**: 正确处理 Java 变量重新赋值（v6.9.6 修复）
- **频率吸附**: 检测正弦波频率，吸附到整数周期实现无缝循环
- **边界混合**: 非正弦骨骼的 smoothstep 边界过渡
- **Catmullrom 插值**: 平滑曲线插值，消除机械感
- **速度连续性**: 调整倒数第二帧确保循环边界速度匹配

### 质量优化
- **振幅自适应 RDP**: 根据骨骼振幅自动调整简化阈值
- **零振幅检测**: 移除无运动骨骼的多余关键帧
- **Stub 动画过滤**: 自动移除空动画和无效动画
- **组合动画生成**: 自动生成 idle_shaking、fly_vomit 等状态组合动画

## 项目结构

```
SubspaceParasite/
├── frontend/              # 解析器
│   └── geckolib_parser.py # 解析 .geo.json 和 .animation.json
├── engine/                # 转换引擎
│   ├── mve_capture.py     # MVE 代码级动作捕捉
│   ├── java_analyzer.py   # Java 源码分析
│   ├── java_trig_simulator.py # Java 三角函数模拟
│   ├── safe_evaluator.py  # 安全 AST 表达式求值
│   ├── carry_forward.py   # 插值感知的轴值填充
│   ├── idle_walk_merger.py # Idle-Walk 动画合并
│   ├── walk_enhancer.py   # 行走动画增强
│   ├── frequency_snapper.py # 频率吸附 + 边界混合
│   ├── catmullrom_baker.py # Catmullrom 曲线烘焙
│   ├── keyframe_simplifier.py # RDP 关键帧简化
│   ├── controller_generator.py # 控制器生成
│   ├── head_tracking_injector.py # 头部跟踪注入
│   └── runtime_behavior_injector.py # 运行时行为注入
├── backend/               # 导出器
│   └── bbmodel_exporter.py # .bbmodel 格式导出
├── batch/                 # 批量转换
│   └── mdo_srp.py         # 全量批量转换脚本
├── core/                  # 核心数据结构
│   ├── types.py           # AnimationIR, BoneIR, KeyframeData
│   ├── quaternion.py      # 四元数旋转
│   └── math_utils.py      # 数学工具
├── convert_model.py       # 单模型转换脚本
├── config.py              # 配置
└── MDO-SRP-SRC/           # 源数据 (geo.json + animation.json + png)
```

## 使用方法

### 单模型转换

```bash
python3 convert_model.py <category> <name>
# 示例: python3 convert_model.py pure pheon
# 示例: python3 convert_model.py deterrent dod
```

### 批量转换

```bash
python3 batch/mdo_srp.py
```

### 输出

转换后的 `.bbmodel` 文件保存在 `models/<category>/` 目录下。

## 转换流程

```
1. 解析 geo.json → BoneIR (骨骼结构)
2. 加载动画数据 (MVE + upstream animation.json)
3. Carry-forward 插值填充
4. Idle-Walk 动画合并
5. Walk 动画增强
6. 频率吸附 + 边界混合
7. Catmullrom 烘焙
8. RDP 关键帧简化
9. 导出 .bbmodel
```

## 版本历史

| 版本 | 主要改进 |
|------|----------|
| v6.9.15 | 修复 fly mainbody 位置 (移除错误 Z 旋转) |
| v6.9.13 | 添加组合状态动画 (idle_shaking, fly_vomit) |
| v6.9.12 | 振幅自适应 RDP + 移除速度平滑尖峰 |
| v6.9.11 | 精确 180° 旋转烘焙 + UV 面交换 |
| v6.9.10 | 纯单轴 180° 烘焙修复 |
| v6.9.8 | 频率吸附 + 边界混合 + 速度平滑 |
| v6.9.6 | 变量重新赋值 bug 修复 (影响 146 个模型) |
| v6.9.5 | Catmullrom 插值 (消除机械感) |
| v6.9.0 | RDP 关键帧简化 |

## 技术细节

### MVE 代码级动作捕捉

MVE (Model Variable Evaluator) 通过解析 Java `setRotationAngles` 方法的反编译源码，提取每个骨骼的三角函数赋值表达式，然后在多帧时间点上求值，生成 ground-truth 动画数据。

**变量顺序处理** (v6.9.6): Java 代码中变量可能被重新赋值（如 `f1` 先用于 idle 频率，再赋值为 state1 频率）。MVE 按源码顺序处理变量赋值和骨骼赋值，确保每个骨骼使用正确的变量值。

### 频率吸附

对于正弦波驱动的骨骼（如触手摆动），检测其频率并吸附到最近的整数周期，实现无缝循环。4 个不可约分频率通过选择最优动画长度 + 强制首末帧一致实现近似无缝。

### Catmullrom 插值

所有旋转通道使用 catmullrom 插值（而非 linear），通过关键帧点绘制平滑 C1 连续曲线，匹配原始正弦波形状，消除机械感。

### 振幅自适应 RDP

关键帧简化阈值根据骨骼振幅自适应：
- 振幅 > 30°: 阈值 = 振幅 × 0.2%（保留更多关键帧）
- 振幅 ≤ 30°: 默认 0.15° 阈值
- 零振幅骨骼: 仅保留首末两帧

## 许可

本转换器仅用于学习和研究目的。SRP 模组版权归 [Dhanantry](https://www.curseforge.com/minecraft/mc-mods/scape-and-run-parasites) 所有。
