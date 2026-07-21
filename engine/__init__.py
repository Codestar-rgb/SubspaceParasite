"""
SRP Model Converter — Engine Package
=====================================

Animation processing engine that transforms parsed AnimationIR data
into clean, loop-aligned, catmullrom-baked keyframes ready for .bbmodel export.

Modules:
  mve_capture              — MVE code-level motion capture from Java source
  java_analyzer            — Java source analysis (state machine, variables, assignments)
  java_trig_simulator      — Java trigonometric expression simulation
  safe_evaluator           — AST-restricted safe expression evaluation
  mve_data_loader          — MVE data loading
  carry_forward            — Interpolation-aware axis value filling
  idle_walk_merger         — Idle-Walk animation merging
  walk_enhancer            — Walk animation enhancement
  frequency_snapper        — Frequency snapping + boundary blending
  catmullrom_baker         — Catmullrom curve baking
  keyframe_simplifier      — RDP keyframe simplification
  head_tracking_injector   — Head tracking Molang injection
  runtime_behavior_injector — Runtime behavior injection
  fft_validator            — FFT frequency validation
  reverse_validator        — Reverse sine-fit quality validation
  molang_injector          — Runtime variable Molang symbolic injection
  layered_loop             — Multi-frequency layered looping
"""
