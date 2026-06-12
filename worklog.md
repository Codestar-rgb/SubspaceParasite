---
Task ID: 1
Agent: Main Agent
Task: 动画问题诊断与修复 — MDO-SRP转换器

Work Log:
- 全面审查转换器代码架构（6阶段管线 + 批量转换器）
- 对比源GeckoLib动画数据与输出bbmodel动画数据
- 对比参考文件（kirin.bbmodel, heblu-SubSRP.bbmodel）与当前输出
- 发现5个关键问题并全部修复

Stage Summary:
- 修复1：插值模式硬编码 → 使用IR中正确插值（rotation: catmullrom, position: linear）
- 修复2：循环模式映射（hold_on_last_frame → hold）
- 修复3：动画旋转变换（-rx, -ry, rz）与模型静态旋转变换一致
- 修复4：动画位置变换（-px, py, pz）与模型位置变换一致
- 修复5：deterrent目录大小写重复文件去重（优先小写版本，更多关键帧）
- 批量重建155模型，0失败
- 验证：102,273个旋转关键帧使用catmullrom，0个hold_on_last_frame残留
