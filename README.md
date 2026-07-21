# SRP Model Converter

> 将 Minecraft 1.12.2 **Scape and Run: Parasites** (SRP) 模组的 Java `ModelRenderer` 模型转换为 Blockbench `.bbmodel` 格式，并生成 GeckoLib 兼容的动画。

## 快速开始

```bash
# 单模型转换
python3 convert_model.py <category> <name>
# 示例: python3 convert_model.py deterrent dodT
# 示例: python3 convert_model.py feral ferEnderman

# 批量转换
python3 batch/mdo_srp.py

# 逆向验证（检查动画质量）
python3 -c "from engine.reverse_validator import validate_bbmodel_against_java, print_report; import config; print_report(validate_bbmodel_against_java('path/to/model.bbmodel', 'modelName', config.DECOMPILED_DIR))"
```

## 项目结构

```
SubspaceParasite/
├── frontend/                        # 输入解析
│   ├── geckolib_parser.py           # 解析 .geo.json / .animation.json
│   └── axis_tracker.py              # 轴存在性追踪
├── engine/                          # 转换引擎
│   ├── mve_capture.py               # MVE 代码级动作捕捉（核心）
│   ├── java_analyzer.py             # Java 源码分析（状态机/变量/赋值）
│   ├── java_trig_simulator.py       # Java 三角函数模拟
│   ├── safe_evaluator.py            # 安全 AST 表达式求值
│   ├── mve_data_loader.py           # MVE 数据加载
│   ├── carry_forward.py             # 插值感知轴值填充
│   ├── idle_walk_merger.py          # Idle-Walk 动画合并
│   ├── walk_enhancer.py             # 行走动画增强
│   ├── frequency_snapper.py         # 频率吸附 + 边界混合
│   ├── catmullrom_baker.py          # Catmullrom 曲线烘焙
│   ├── keyframe_simplifier.py       # RDP 关键帧简化
│   ├── head_tracking_injector.py    # 头部跟踪 Molang 注入
│   ├── runtime_behavior_injector.py # 运行时行为注入
│   ├── fft_validator.py             # FFT 频率验证
│   ├── reverse_validator.py         # 逆向正弦拟合质量验证
│   ├── molang_injector.py           # 运行时变量 Molang 符号化
│   └── layered_loop.py              # 多频率分层循环
├── backend/                         # 导出器
│   └── bbmodel_exporter.py          # .bbmodel 格式导出
├── batch/                           # 批量转换
│   └── mdo_srp.py                   # 全量批量转换脚本
├── core/                            # 核心数据结构
│   ├── types.py                     # AnimationIR / BoneIR / KeyframeData
│   ├── quaternion.py                # 四元数旋转
│   ├── coords.py                    # 坐标变换
│   └── math_utils.py                # 数学工具
├── convert_model.py                 # 单模型转换入口
├── config.py                        # 配置
└── MDO-SRP-SRC/                     # 源数据（.gitignore 忽略）
```

## 转换流水线

```
geo.json ──▶ BoneIR 解析 ──▶ 坐标变换(RH→LH) ──▶ 元素构建(UV) ─┐
                                                                │
Java 源码 ──▶ MVE 捕获 ──▶ Carry-forward ──▶ Idle-Walk 合并 ──┤
              │                                                  │
              ├─▶ 频率吸附 ──▶ Catmullrom 烘焙 ──▶ RDP 简化 ──┤
              │                                                  │
              ├─▶ FFT 验证 ──▶ 逆向验证 ──────────────────────┤
              │                                                  ▼
              └─▶ Molang 注入 ──────────────────────▶ .bbmodel 导出
```

## 核心技术

### MVE 代码级动作捕捉

从 Java `setRotationAngles` 方法中提取 `this.bone.field = expression` 赋值，在多时间点求值生成 ground-truth 关键帧。处理状态机 if/else、变量重赋值、共享代码。

### 频率吸附

检测正弦波频率，吸附到整数周期实现无缝循环。对非正弦骨骼应用 smoothstep 边界混合。

### Catmullrom 插值

所有旋转通道使用 catmullrom 插值，通过关键帧点绘制平滑 C1 连续曲线，消除机械感。

### 180° 旋转烘焙

纯单轴 180° 旋转烘焙到立方体位置，避免 Blockbench 双重镜像。UV 面交换处理 east/west。

### 逆向验证

读取 `.bbmodel` 关键帧，拟合正弦波，与 Java 源码频率/振幅比较，计算质量分数。

### 自适应采样

基于 Nyquist 定理的自适应采样率（16x 过采样），确保高频骨骼的平滑捕获。

## 版本历史

| 版本 | 主要改进 |
|------|----------|
| v6.9.18 | 逆向验证器（.bbmodel → Java 正弦拟合质量指标） |
| v6.9.17 | FFT 验证、自适应采样、Molang 注入、分层循环 |
| v6.9.16 | 共享代码提取修复 |
| v6.9.15 | Fly mainbody 位置修复 |
| v6.9.13 | 组合状态动画（idle_shaking, fly_vomit） |
| v6.9.11 | 精确 180° 旋转烘焙 + UV 面交换 |
| v6.9.8 | 频率吸附 + 边界混合 |
| v6.9.6 | 变量重新赋值 bug 修复（影响 146 模型） |
| v6.9.5 | Catmullrom 插值 |
| v6.9.0 | RDP 关键帧简化 |

## 许可

本转换器仅用于学习和研究目的。SRP 模组版权归 [Dhanantry](https://www.curseforge.com/minecraft/mc-mods/scape-and-run-parasites) 所有。
