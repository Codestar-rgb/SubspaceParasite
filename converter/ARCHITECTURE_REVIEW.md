# SubspaceParasite 架构评估报告

> 基于对代码库的逐行审计，对社区建议的客观评估与实施路线图

---

## 评估结论总览

| 建议 | 判定 | 优先级 | 理由 |
|------|------|--------|------|
| javalang → tree-sitter-java | ✅ 正确，应实施 | 高 | javalang 确实已废弃，且当前代码已回退到 regex |
| 欧拉角 → 四元数链路 | ⚠️ 部分正确，需细化 | 高 | core_math.py 已有矩阵方法，但 bbmodel_generator 仍有问题 |
| 采样 → Molang 直出 | ⚠️ 理论正确，实际困难 | 中 | GeckoLib Molang 支持有限，且现有 .bbmodel 路径依赖采样 |
| 绝对坐标 → 相对坐标 | ✅ 正确，应实施 | 高 | 这是 Model Scattering 的根因 |
| Model Floating 修复 | ✅ 正确，setSize 动态偏移 | 高 | 硬编码 Y=24 仅适用于标准双足 |
| sympy/librosa/trimesh 引入 | ❌ 过度工程化 | 低 | ROI 极低，现有工具链已覆盖 |
| "双轨制智能管道" | ❌ 过度设计 | 低 | 当前应先修复已知 Bug，而非重构架构 |

---

## 一、Java 源码解析层：javalang → tree-sitter-java

### 当前状况（代码实证）

```python
# model_converter.py 第 121-129 行
def parse_java_source(self, java_source: str):
    try:
        import javalang
        tree = javalang.parse.parse(java_source)
        self._parse_ast(tree, java_source)
    except Exception as e:
        warnings.warn(f"javalang AST parsing failed ({e}), falling back to text parsing")
        self._parse_text(java_source)

# _parse_ast 第 131-143 行
def _parse_ast(self, tree, java_source: str):
    for path, node in tree:
        if isinstance(node, javalang.tree.ClassDeclaration):
            for elem in node.body:
                if isinstance(elem, javalang.tree.MethodDeclaration) and elem.name == '<init>':
                    pass  # 什么都不做！
    # 最终还是回退到文本解析
    self._parse_text(java_source)
```

### 评估

**建议完全正确。** 当前代码的 javalang AST 解析是**空操作**——`_parse_ast` 方法遍历了 AST 树但没有提取任何信息，最终总是回退到 `_parse_text`。而 `_parse_text` 完全依赖正则表达式（`re.compile`），这对 SRG 混淆名有效，但对嵌套作用域和复杂表达式（如 `setRotationAngles` 中的链式三元运算符）确实无力。

### 实施方案

1. **引入 `tree-sitter-java`**，替换 javalang 作为主解析器
2. **保留 regex 作为 fallback**，但仅用于 SRG 名映射（当前已工作良好）
3. **利用 CST 遍历精准提取 `setRotationAngles` 方法体**，而非依赖正则大括号计数（当前 `_extract_method_body` 用大括号深度计数，遇到字符串中的 `{}` 会出错）
4. **不需要全面重写**——可以在现有 `_parse_text` 基础上增加 tree-sitter 辅助方法

### 工作量估算：3-5 天

---

## 二、坐标系与多轴旋转：欧拉角 → 四元数链路

### 当前状况（代码实证）

`core_math.py` **已经实现了正确的矩阵方法**：

```python
# core_math.py 第 499-580 行
def convert_model_rotation_order(rx, ry, rz):
    """矩阵相似变换 R' = M_model * R * M_model^{-1}，然后分解回欧拉角"""
    R_1122 = _rz(rz) @ _ry(ry) @ _rx(rx)
    R_prime = M_MODEL @ R_1122 @ M_MODEL_INV
    # Graphics Gems IV 分解...
```

`model_converter.py` **已经使用了这个方法**：

```python
# model_converter.py 第 744-748 行
if non_zero_count > 1:
    new_rx, new_ry, new_rz = convert_model_rotation_order(rx, ry, rz)  # 矩阵方法
else:
    new_rx, new_ry, new_rz = convert_model_rot(rx, ry, rz)  # 简单取反
```

但 `bbmodel_generator.py` **仍然使用了 scipy 的欧拉角转换**（已被证明是错误的）：

```python
# bbmodel_generator.py 第 226-227 行
r = Rotation.from_euler("XYZ", rotation_deg, degrees=True)
result = r.as_euler("xyz", degrees=True)  # extrinsic→intrinsic 转换，HANDOFF_DOC 明确说这是错的
```

### 评估

**建议部分正确，但诊断不够精确。** 

- `core_math.py` 的数学推导是正确的，`M_model = diag(1,-1,-1)` 的相似变换对单骨骼旋转是完备的
- **Heblu Wing Tips 的真正根因不是坐标系转换，而是骨骼链的层级旋转累积**。在 MC 1.12.2 中，子骨骼的 `setRotationPoint` 是相对于父骨骼的**旋转后**空间。当前的 `_compute_absolute_pivots` 方法（第 386-401 行）只用简单加法累积，**忽略了父骨骼旋转对子骨骼偏移的影响**：

```python
# model_converter.py 第 397-399 行
bone.abs_pivot_x = parent_abs[0] + bone.pivot_x  # ❌ 没有应用父骨骼旋转！
bone.abs_pivot_y = parent_abs[1] + bone.pivot_y
bone.abs_pivot_z = parent_abs[2] + bone.pivot_z
```

正确的做法是：`child_abs = parent_abs + R_parent * child_offset`

- `bbmodel_generator.py` 中的 scipy 欧拉角转换确实需要移除，应该直接传递值（正如 HANDOFF_DOC 所述）

### 实施方案

1. **修复 `_compute_absolute_pivots`**：引入父骨骼旋转矩阵，正确计算子骨骼绝对位置
2. **移除 `bbmodel_generator.py` 中的 scipy `Rotation.from_euler` 调用**，改为直接传递值
3. **四元数链路不需要全面引入**——当前 `convert_model_rotation_order` 的矩阵方法在数学上是等价的。只需修复层级累积即可

### 工作量估算：2-3 天

---

## 三、动画采样 → Molang 直出

### 当前状况（代码实证）

`animation_converter.py` 的采样流程：

1. 从 Java 提取 `setRotationAngles` 方法体
2. 将 `MathHelper.cos/sin` 替换为 `math.cos/sin`
3. 用 `eval()` 对表达式求值，在 2π 周期内取 120 个采样点
4. Douglas-Peucker 简化后输出关键帧

`bbmodel_animation_converter_v18.py` 更是高达 240Hz/480Hz 重采样 + C0/C1/C2 修正。

### 评估

**理论上完全正确，但实际可行性存疑。**

**Molang 直出的优势**：
- 0 插值误差，完美循环
- 文件体积缩小 95%
- 数学上等价于原版

**实际障碍**：
1. **GeckoLib 的 Molang 支持是有限的**——它支持 Bedrock Edition 的 Molang 子集，但不支持所有表达式。特别是条件表达式（三元运算符）在 Molang 中的表达受限
2. **现有 .bbmodel 路径完全依赖采样**——所有 154 个模型的动画都来自 .bbmodel 文件，不是 Java 源码。Molang 直出只能用于从 Java 直接转换的路径
3. **SRParasites 的大量动画是 limbSwing 驱动的**——这些动画在 GeckoLib 中需要通过 `AnimationController` + `codeAnimations` 实现，而不是 `.animation.json`。Molang 对 `limbSwing` 的访问方式（`query.anim_time` vs `query.limb_swing`）需要验证
4. **复杂表达式难以自动翻译**——Java 中的 `f11 = MathHelper.cos(ageInTicks * 0.130998f) * 0.107215f; this.bipedHead.field_78795_f = f11;` 需要变量内联和表达式简化才能转为 Molang

### 实施方案

**分阶段实施，不要一步到位**：

1. **Phase 1（推荐先做）**：对纯 `ageInTicks` 驱动的简单三角函数动画，生成 Molang 表达式。用 `sympy` 简化表达式（这里 sympy 确实有用），然后输出到 `.animation.json` 的 `"pre_animation_script"` 或 Molang 关键帧
2. **Phase 2**：对 `limbSwing` 驱动的动画，继续使用采样 + 高质量修正，但提高采样精度
3. **Phase 3（远期）**：探索完整的 Java→Molang AST 翻译器

### 工作量估算：Phase 1 约 5-7 天

---

## 四、BBModel 绝对坐标 → 相对坐标

### 当前状况（代码实证）

`bbmodel_generator.py` 明确注释：

```python
# bbmodel_generator.py 第 21-25 行
# .bbmodel uses ABSOLUTE world-space coordinates for element positions and
# bone-local (relative to parent) coordinates.
# Element from/to: ABSOLUTE world position (bone-local origin + absolute pivot)
```

第 363-369 行的转换逻辑：

```python
# Convert from bone-local to ABSOLUTE world space
abs_from[i] = bone_local_origin[i] + abs_pivot[i]
abs_to[i] = bone_local_origin[i] + bone_size[i] + abs_pivot[i]
```

### 评估

**建议正确，这是 Model Scattering 的直接根因。**

Blockbench 的 `.bbmodel` 格式规范中，element 的 `from/to` 确实使用绝对坐标，但当父 group 存在旋转时，绝对坐标的计算需要考虑旋转矩阵。当前的 `_compute_absolute_pivots` 仅用加法累积（如上所述），导致旋转后的骨骼绝对位置计算错误，进而导致方块的 `from/to` 偏移。

**但修复方向需要明确**：不是从"绝对坐标"改为"相对坐标"（.bbmodel 规范确实使用绝对坐标），而是**修复绝对坐标的计算方式**——在累积父骨骼位置时必须考虑旋转。

### 实施方案

1. **修复绝对坐标计算**：在 `_compute_absolute_pivots` 中加入父骨骼旋转矩阵
2. **为 .bbmodel 添加验证步骤**：输出后用 `trimesh` 或简单的 AABB 比对确认方块位置正确
3. **考虑添加"局部模式"选项**：对于旋转复杂的骨骼链，提供直接使用局部坐标的备选输出路径

### 工作量估算：3-5 天

---

## 五、Model Floating 修复

### 当前状况

```python
# model_converter.py 第 103 行
ROOT_BONE_PIVOT = [0.0, 24.0, 0.0]  # 硬编码！
```

### 评估

**建议完全正确。** SRParasites 中的实体远不止标准双足（1.5 格高 = 24px），很多巨型实体的 hitbox 高度远超 24px。应该从 Java 源码中解析 `setSize(width, height)` 调用，动态计算根骨骼偏移。

### 实施方案

1. **编写 `EntityMetaExtractor`**：从 `EntityXxx.java` 中提取 `setSize(w, h)` 调用
2. **动态计算 `Y_offset = height * 16`**（MC 1 单位 = 16 像素）
3. **向后兼容**：如果无法提取，默认使用 24.0

### 工作量估算：1-2 天

---

## 六、不建议实施的建议

### 1. sympy 全面引入

`sympy` 在 Molang 直出的 Phase 1 中有用（简化三角表达式），但作为通用符号计算引擎引入是过度工程化。当前的 `eval()` + regex 方法对大多数表达式已经足够。

### 2. librosa / 高级 scipy.signal

 librosa 是音频处理库，用于动画频谱分析是杀鸡用牛刀。当前的 FFT 自相关检测（已在 v18 中实现）已经覆盖了周期检测需求。Kalman 滤波更是过度——动画采样不是信号恢复问题。

### 3. trimesh 顶点级比对

`trimesh` 的 AABB 和顶点法线比对听起来完美，但实际实现成本极高（需要构建 1.12.2 模型的完整拓扑网格），且收益仅限于验证。用简单的视觉比对或 AABB 采样检测即可。

### 4. "双轨制智能管道"

当前最紧迫的问题是修复已知 Bug（Heblu Wing、Model Scattering、Model Floating），而不是重构整体架构。双轨制增加了维护复杂度，在 Bug 修复前不应引入。

---

## 七、推荐实施路线图

### 第一阶段：Bug 修复（1-2 周）

1. **修复 `_compute_absolute_pivots` 层级旋转累积** → 解决 Heblu Wing + Model Scattering
2. **移除 `bbmodel_generator.py` 中的 scipy 欧拉角转换** → 直接传递值
3. **动态 `ROOT_BONE_PIVOT`** → 解决 Model Floating
4. **修复 Mirror 逻辑验证** → 确保无双镜像

### 第二阶段：解析器升级（1 周）

5. **引入 tree-sitter-java** → 替换 javalang，增强 `setRotationAngles` 方法体提取
6. **改进表达式解析** → 支持嵌套三元运算符和复杂链式调用

### 第三阶段：动画质量提升（1-2 周）

7. **Molang 直出 Phase 1** → 对简单 ageInTicks 动画生成 Molang 表达式
8. **提高采样精度** → limbSwing 动画使用更高采样率 + 更好的循环边界处理

### 第四阶段：验证与质量保障（1 周）

9. **添加 AABB 验证** → 简单的包围盒比对，而非顶点级
10. **批量回归测试** → 对所有 154 个模型运行转换并输出差异报告

---

*评估基于 2026-03-05 代码库快照，由逐行代码审计得出*
