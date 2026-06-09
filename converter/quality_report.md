# Quality Audit Report

**Generated**: 2026-06-05T14:56:30.555603+00:00
**Converter Version**: v18
**Total Models**: 168
**Total Animations**: 316

## Overall Quality Score

**Score**: 71.3/100 — 🟡 ACCEPTABLE
**Previous Run**: 69.0 ↑ (+2.2)

## Summary Statistics

| Metric | Count | Percentage |
|--------|-------|------------|
| Models with geo.json | 168 | 100.0% |
| Models with animations | 168 | 100.0% |
| Models with textures | 168 | 100.0% |
| Models below Y=0 | 110 | 65.5% |
| Missing textures | 0 | 0.0% |
| Missing animations | 110 | — |

### Animation Continuity

| Metric | Perfect | Acceptable | Fail |
|--------|---------|------------|------|
| C0 (position) | 315 (99.7%) | 0 | 1 |
| C1 (velocity) | 134 (42.4%) | 140 | 42 |
| Naturalness ≥0.8 | 67 (21.2%) | — | 249 |
| Amplitude ≥90% | 286 (90.5%) | — | 30 |

## Category Breakdown

| Category | Models | Avg Score |
|----------|--------|-----------|
| abomination | 2 | 66.5 |
| adapted | 12 | 65.8 |
| ancient | 3 | 91.0 |
| awakened | 2 | 82.5 |
| crude | 11 | 63.2 |
| derived | 3 | 52.0 |
| deterrent | 33 | 74.5 |
| feral | 9 | 55.7 |
| focused | 2 | 80.0 |
| hijacked | 3 | 68.0 |
| inborn | 11 | 65.6 |
| infected | 29 | 64.4 |
| misc | 20 | 89.6 |
| primitive | 12 | 65.7 |
| projectile | 1 | 85.0 |
| pure | 15 | 78.8 |

## 🔴 Critical Issues

- derived/heblu/heblu.vomit: C0 error > 0.5°: 27.431°
- derived/heblu/heblu.vomit: C1 error > 5.0°/s: 355.170°/s
- derived/heblu/heblu.vomit: Naturalness < 0.8: 0.143
- derived/heblu/heblu.vomit: Transition smoothness < 0.8: 0.000

## 🟠 Major Issues

- abomination/aboBodies: Missing animations from source: aboBodies.evolved
- abomination/aboBodies: Geometry has 10 bone(s) with elements below Y=0
- abomination/aboBodies/abobodies.walk: C1 error > 5.0°/s: 6.741°/s
- abomination/aboBodies/abobodies.walk: Naturalness < 0.8: 0.467
- abomination/aboHead: Missing animations from source: aboHead.idle, aboHead.evolved
- adapted/banoAdapted: Geometry has 5 bone(s) with elements below Y=0
- adapted/canraAdapted: Missing animations from source: canraAdapted.evolved, canraAdapted.attack
- adapted/canraAdapted: Geometry has 3 bone(s) with elements below Y=0
- adapted/gimAdapted: Missing animations from source: gimAdapted.evolved, gimAdapted.stage9
- adapted/hullAdapted: Missing animations from source: hullAdapted.evolved
- adapted/hullAdapted: Geometry has 8 bone(s) with elements below Y=0
- adapted/ikiAdapted: Geometry has 54 bone(s) with elements below Y=0
- adapted/lumAdapted: Geometry has 110 bone(s) with elements below Y=0
- adapted/noglaAdapted: Missing animations from source: noglaAdapted.evolved
- adapted/noglaAdapted: Geometry has 8 bone(s) with elements below Y=0
- adapted/ranracAdapted: Missing animations from source: ranracAdapted.idle, ranracAdapted.evolved, ranracAdapted.attack
- adapted/shycoAdapted: Missing animations from source: shycoAdapted.evolved
- adapted/shycoAdapted: Geometry has 28 bone(s) with elements below Y=0
- adapted/wymoAdapted: Geometry has 1 bone(s) with elements below Y=0
- adapted/zaaAdapted: Missing animations from source: zaaAdapted.ft6, zaaAdapted.not_ft6
- adapted/zaaAdapted: Geometry has 3 bone(s) with elements below Y=0
- ancient/oronco: Missing animations from source: oronco.stage77, oronco.evolved
- awakened/oroncoAW: Geometry has 1 bone(s) with elements below Y=0
- awakened/oroncoAWFL: Geometry has 79 bone(s) with elements below Y=0
- crude/cruxA: Missing animations from source: cruxA.evolved, cruxA.attack, cruxA.unknown
- crude/cruxA: Geometry has 18 bone(s) with elements below Y=0
- crude/cruxB: Geometry has 17 bone(s) with elements below Y=0
- crude/done: Missing animations from source: done.evolved
- crude/heed/heed.walk: C1 error > 5.0°/s: 7.308°/s
- crude/heed/heed.walk: Naturalness < 0.8: 0.438
- ... and 241 more

## 🟡 Minor Issues

- abomination/aboBodies/abobodies.idle: C1 error > 1.0°/s (acceptable): 1.290°/s
- abomination/aboHead/abohead.walk: C1 error > 1.0°/s (acceptable): 1.379°/s
- abomination/aboHead/abohead.walk: Naturalness < 0.8: 0.632
- adapted/canraAdapted/canraadapted.walk: C1 error > 1.0°/s (acceptable): 1.337°/s
- adapted/canraAdapted/canraadapted.walk: Naturalness < 0.8: 0.385
- adapted/canraAdapted/canraadapted.idle: C1 error > 1.0°/s (acceptable): 1.157°/s
- adapted/canraAdapted/canraadapted.idle: Naturalness < 0.8: 0.500
- adapted/canraAdapted/canraadapted.sleeping: C1 error > 1.0°/s (acceptable): 1.597°/s
- adapted/canraAdapted/canraadapted.sleeping: Naturalness < 0.8: 0.583
- adapted/canraAdapted/canraadapted.stage25: C1 error > 1.0°/s (acceptable): 1.157°/s
- adapted/canraAdapted/canraadapted.stage25: Naturalness < 0.8: 0.500
- adapted/gimAdapted/gimadapted.walk: C1 error > 1.0°/s (acceptable): 2.867°/s
- adapted/gimAdapted/gimadapted.walk: Naturalness < 0.8: 0.385
- adapted/gimAdapted/gimadapted.idle: C1 error > 1.0°/s (acceptable): 1.484°/s
- adapted/gimAdapted/gimadapted.idle: Naturalness < 0.8: 0.562
- adapted/gimAdapted/gimadapted.attack: Naturalness < 0.8: 0.182
- adapted/hullAdapted/hulladapted.walk: Naturalness < 0.8: 0.462
- adapted/hullAdapted/hulladapted.attack: C1 error > 1.0°/s (acceptable): 1.729°/s
- adapted/hullAdapted/hulladapted.attack: Naturalness < 0.8: 0.750
- adapted/ikiAdapted/ikiadapted.idle: C1 error > 1.0°/s (acceptable): 1.295°/s
- ... and 357 more

## Reference Benchmark Comparisons

### kirin

- **Bones**: ref=1, out=142
- **Cubes**: ref=141, out=141
- **Animations**: ref=1, out=4
- **Y bounds**: ref=[60.8, 113.0], out=[24.0, 117.1]
- **Missing animations**: srparasites.kirin.idle
- ⚠️ Bone count mismatch: ref=1, out=142
- ⚠️ Missing animations: srparasites.kirin.idle

### heblu

- **Bones**: ref=1, out=357
- **Cubes**: ref=356, out=356
- **Animations**: ref=8, out=8
- **Y bounds**: ref=[-6.1, 99.9], out=[-11.1, 100.4]
- **Missing animations**: model.idle, model.attack, model.fly, model.vomit, model.fly_vomit, model.shaking, model.cosmic, model.cosmic_shaking
- ⚠️ Bone count mismatch: ref=1, out=357
- ⚠️ Missing animations: model.idle, model.attack, model.fly, model.vomit, model.fly_vomit, model.shaking, model.cosmic, model.cosmic_shaking

## Per-Model Issues

### abomination/aboBodies (score: 50.0)
- Missing animations from source: aboBodies.evolved
- Geometry has 10 bone(s) with elements below Y=0
  - **abobodies.walk**: C1 error > 5.0°/s: 6.741°/s; Naturalness < 0.8: 0.467
    - 💡 Enable septic_global_correction, increase transition_zone_max_ratio, or enable full_resample_velocity_correction
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes
  - **abobodies.idle**: C1 error > 1.0°/s (acceptable): 1.290°/s

### abomination/aboHead (score: 83.0)
- Missing animations from source: aboHead.idle, aboHead.evolved
  - **abohead.walk**: C1 error > 1.0°/s (acceptable): 1.379°/s; Naturalness < 0.8: 0.632
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes

### adapted/banoAdapted (score: 75.0)
- Geometry has 5 bone(s) with elements below Y=0

### adapted/canraAdapted (score: 47.0)
- Missing animations from source: canraAdapted.evolved, canraAdapted.attack
- Geometry has 3 bone(s) with elements below Y=0
  - **canraadapted.walk**: C1 error > 1.0°/s (acceptable): 1.337°/s; Naturalness < 0.8: 0.385
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes
  - **canraadapted.idle**: C1 error > 1.0°/s (acceptable): 1.157°/s; Naturalness < 0.8: 0.500
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes
  - **canraadapted.sleeping**: C1 error > 1.0°/s (acceptable): 1.597°/s; Naturalness < 0.8: 0.583
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes
  - **canraadapted.stage25**: C1 error > 1.0°/s (acceptable): 1.157°/s; Naturalness < 0.8: 0.500
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes

### adapted/gimAdapted (score: 71.0)
- Missing animations from source: gimAdapted.evolved, gimAdapted.stage9
  - **gimadapted.walk**: C1 error > 1.0°/s (acceptable): 2.867°/s; Naturalness < 0.8: 0.385
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes
  - **gimadapted.idle**: C1 error > 1.0°/s (acceptable): 1.484°/s; Naturalness < 0.8: 0.562
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes
  - **gimadapted.attack**: Naturalness < 0.8: 0.182
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes

### adapted/hullAdapted (score: 53.0)
- Missing animations from source: hullAdapted.evolved
- Geometry has 8 bone(s) with elements below Y=0
  - **hulladapted.walk**: Naturalness < 0.8: 0.462
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes
  - **hulladapted.attack**: C1 error > 1.0°/s (acceptable): 1.729°/s; Naturalness < 0.8: 0.750
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes

### adapted/ikiAdapted (score: 63.0)
- Geometry has 54 bone(s) with elements below Y=0
  - **ikiadapted.idle**: C1 error > 1.0°/s (acceptable): 1.295°/s; Naturalness < 0.8: 0.558
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes

### adapted/lumAdapted (score: 60.0)
- Geometry has 110 bone(s) with elements below Y=0
  - **lumadapted.idle**: Naturalness < 0.8: 0.500
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes
  - **lumadapted.evolved**: Naturalness < 0.8: 0.182
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes

### adapted/noglaAdapted (score: 34.0)
- Missing animations from source: noglaAdapted.evolved
- Geometry has 8 bone(s) with elements below Y=0
  - **noglaadapted.walk**: C1 error > 1.0°/s (acceptable): 1.209°/s; Naturalness < 0.8: 0.385
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes
  - **noglaadapted.idle**: C1 error > 1.0°/s (acceptable): 1.021°/s; Naturalness < 0.8: 0.500
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes
  - **noglaadapted.attack**: C1 error > 1.0°/s (acceptable): 1.168°/s; Naturalness < 0.8: 0.200
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes
  - **noglaadapted.death**: Naturalness < 0.8: 0.167
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes
  - **noglaadapted.stage25**: Naturalness < 0.8: 0.300
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes

### adapted/ranracAdapted (score: 76.0)
- Missing animations from source: ranracAdapted.idle, ranracAdapted.evolved, ranracAdapted.attack
  - **ranracadapted.walk**: C1 error > 1.0°/s (acceptable): 1.483°/s; Naturalness < 0.8: 0.364
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes
  - **ranracadapted.death**: C1 error > 1.0°/s (acceptable): 1.756°/s

### adapted/shycoAdapted (score: 41.0)
- Missing animations from source: shycoAdapted.evolved
- Geometry has 28 bone(s) with elements below Y=0
  - **shycoadapted.walk**: C1 error > 1.0°/s (acceptable): 1.889°/s; Naturalness < 0.8: 0.444
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes
  - **shycoadapted.idle**: Naturalness < 0.8: 0.500
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes
  - **shycoadapted.attack**: C1 error > 1.0°/s (acceptable): 1.536°/s; Naturalness < 0.8: 0.273
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes
  - **shycoadapted.stage25**: Naturalness < 0.8: 0.015
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes

### adapted/wymoAdapted (score: 95.0)
- Geometry has 1 bone(s) with elements below Y=0

### adapted/zaaAdapted (score: 75.0)
- Missing animations from source: zaaAdapted.ft6, zaaAdapted.not_ft6
- Geometry has 3 bone(s) with elements below Y=0

### ancient/oronco (score: 90.0)
- Missing animations from source: oronco.stage77, oronco.evolved

### awakened/oroncoAW (score: 95.0)
- Geometry has 1 bone(s) with elements below Y=0

### awakened/oroncoAWFL (score: 70.0)
- Geometry has 79 bone(s) with elements below Y=0

### crude/cruxA (score: 41.0)
- Missing animations from source: cruxA.evolved, cruxA.attack, cruxA.unknown
- Geometry has 18 bone(s) with elements below Y=0
  - **cruxa.walk**: C1 error > 1.0°/s (acceptable): 1.376°/s; Naturalness < 0.8: 0.385
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes
  - **cruxa.idle**: C1 error > 1.0°/s (acceptable): 1.411°/s; Naturalness < 0.8: 0.650
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes

### crude/cruxB (score: 61.0)
- Geometry has 17 bone(s) with elements below Y=0
  - **cruxb.walk**: C1 error > 1.0°/s (acceptable): 1.935°/s
  - **cruxb.idle**: C1 error > 1.0°/s (acceptable): 1.612°/s; Naturalness < 0.8: 0.725
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes

### crude/done (score: 69.0)
- Missing animations from source: done.evolved
  - **done.walk**: C1 error > 1.0°/s (acceptable): 1.196°/s; Amplitude reduction > 10%: min preservation = 0.537; Naturalness < 0.8: 0.385
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes
    - 💡 Enable peak_preservation_enabled, increase peak_preservation_max_reduction, or reduce transition_zone_ratio
  - **done.idle**: C1 error > 1.0°/s (acceptable): 1.595°/s; Naturalness < 0.8: 0.781
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes
  - **done.attack**: C1 error > 1.0°/s (acceptable): 1.550°/s; Naturalness < 0.8: 0.500
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes

### crude/host (score: 56.0)
- Geometry has 10 bone(s) with elements below Y=0
  - **host.closed**: C1 error > 1.0°/s (acceptable): 1.335°/s; Naturalness < 0.8: 0.500
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes
  - **host.open**: C1 error > 1.0°/s (acceptable): 1.335°/s; Naturalness < 0.8: 0.500
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes

### crude/hostII (score: 63.0)
- Geometry has 226 bone(s) with elements below Y=0
  - **hostii.closed**: C1 error > 1.0°/s (acceptable): 1.254°/s; Naturalness < 0.8: 0.750
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes

### crude/inhooM (score: 63.0)
- Geometry has 125 bone(s) with elements below Y=0
  - **inhoom.idle**: C1 error > 1.0°/s (acceptable): 1.288°/s; Naturalness < 0.8: 0.688
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes

### crude/inhooS (score: 63.0)
- Geometry has 44 bone(s) with elements below Y=0
  - **inhoos.idle**: C1 error > 1.0°/s (acceptable): 1.288°/s; Naturalness < 0.8: 0.688
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes

### crude/mes (score: 53.0)
- Missing animations from source: mes.idle
- Geometry has 8 bone(s) with elements below Y=0
  - **mes.walk**: C1 error > 1.0°/s (acceptable): 1.795°/s; Amplitude reduction > 10%: min preservation = 0.552; Naturalness < 0.8: 0.558
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes
    - 💡 Enable peak_preservation_enabled, increase peak_preservation_max_reduction, or reduce transition_zone_ratio

### crude/quac (score: 70.0)
- Geometry has 12 bone(s) with elements below Y=0

### derived/heblu (score: 0.0)
- Missing animations from source: model.idle, model.attack, model.fly, model.vomit, model.shaking (+3 more)
- Geometry has 14 bone(s) with elements below Y=0
  - **heblu.idle**: C1 error > 1.0°/s (acceptable): 1.734°/s; Naturalness < 0.8: 0.200
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes
  - **heblu.attack**: C1 error > 5.0°/s: 6.615°/s; Naturalness < 0.8: 0.250
    - 💡 Enable septic_global_correction, increase transition_zone_max_ratio, or enable full_resample_velocity_correction
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes
  - **heblu.fly**: C1 error > 1.0°/s (acceptable): 2.263°/s; Naturalness < 0.8: 0.231
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes
  - **heblu.vomit**: C0 error > 0.5°: 27.431°; C1 error > 5.0°/s: 355.170°/s; Naturalness < 0.8: 0.143; Transition smoothness < 0.8: 0.000
    - 💡 Enable final_c0_enforcement or increase loop_validation_iterations
    - 💡 Enable septic_global_correction, increase transition_zone_max_ratio, or enable full_resample_velocity_correction
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes
  - **heblu.shaking**: C1 error > 1.0°/s (acceptable): 1.645°/s; Naturalness < 0.8: 0.273
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes
  - **heblu.cosmic**: C1 error > 1.0°/s (acceptable): 1.799°/s; Naturalness < 0.8: 0.200
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes
  - **heblu.fly_vomit**: C1 error > 1.0°/s (acceptable): 1.084°/s; Naturalness < 0.8: 0.194
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes
  - **heblu.cosmic_shaking**: C1 error > 1.0°/s (acceptable): 1.778°/s; Naturalness < 0.8: 0.047; Transition smoothness < 0.8: 0.781
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes

### derived/kirin (score: 70.0)
- Missing animations from source: srparasites.kirin.shaking, srparasites.kirin.cosmic, srparasites.kirin.cosmic_shaking
  - **kirin.shaking**: Naturalness < 0.8: 0.119
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes
  - **kirin.cosmic**: Naturalness < 0.8: 0.436
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes
  - **kirin.cosmic_shaking**: Naturalness < 0.8: 0.008
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes

### derived/venkrolSIV (score: 86.0)
- Geometry has 1 bone(s) with elements below Y=0
  - **venkrolsiv.idle**: C1 error > 1.0°/s (acceptable): 1.658°/s; Naturalness < 0.8: 0.333
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes
  - **venkrolsiv.dormant**: C1 error > 1.0°/s (acceptable): 1.605°/s

### deterrent/dod (score: 63.0)
- Geometry has 7 bone(s) with elements below Y=0
  - **dod.idle**: C1 error > 1.0°/s (acceptable): 1.209°/s; Naturalness < 0.8: 0.182
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes

### deterrent/dodSII (score: 68.0)
- Geometry has 5 bone(s) with elements below Y=0
  - **dodsii.idle**: C1 error > 1.0°/s (acceptable): 1.209°/s; Naturalness < 0.8: 0.133
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes

### deterrent/dodSIII (score: 80.0)
- Geometry has 3 bone(s) with elements below Y=0
  - **dodsiii.idle**: Naturalness < 0.8: 0.118
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes

### deterrent/dodSIV (score: 75.0)
- Geometry has 4 bone(s) with elements below Y=0
  - **dodsiv.idle**: Naturalness < 0.8: 0.118
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes

### deterrent/dodSIVH (score: 83.0)
- Geometry has 2 bone(s) with elements below Y=0
  - **dodsivh.idle**: C1 error > 1.0°/s (acceptable): 1.999°/s; Naturalness < 0.8: 0.154
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes

### deterrent/dodT (score: 65.0)
- Geometry has 80 bone(s) with elements below Y=0
  - **dodt.idle**: Naturalness < 0.8: 0.598
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes

### deterrent/dodsii (score: 62.0)
- Geometry has 5 bone(s) with elements below Y=0
  - **dodsii.idle**: C1 error > 5.0°/s: 7.550°/s; Naturalness < 0.8: 0.036
    - 💡 Enable septic_global_correction, increase transition_zone_max_ratio, or enable full_resample_velocity_correction
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes

### deterrent/dodsiii (score: 78.0)
- Geometry has 3 bone(s) with elements below Y=0
  - **dodsiii.idle**: C1 error > 1.0°/s (acceptable): 2.531°/s; Naturalness < 0.8: 0.031
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes

### deterrent/dodsiv (score: 73.0)
- Geometry has 4 bone(s) with elements below Y=0
  - **dodsiv.idle**: C1 error > 1.0°/s (acceptable): 2.531°/s; Naturalness < 0.8: 0.031
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes

### deterrent/dodsivh (score: 77.0)
- Geometry has 2 bone(s) with elements below Y=0
  - **dodsivh.idle**: C1 error > 5.0°/s: 18.362°/s; Naturalness < 0.8: 0.094
    - 💡 Enable septic_global_correction, increase transition_zone_max_ratio, or enable full_resample_velocity_correction
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes

### deterrent/dodt (score: 57.0)
- Geometry has 80 bone(s) with elements below Y=0
  - **dodt.idle**: C1 error > 5.0°/s: 5.845°/s; Naturalness < 0.8: 0.400
    - 💡 Enable septic_global_correction, increase transition_zone_max_ratio, or enable full_resample_velocity_correction
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes

### deterrent/leem (score: 83.0)
- Geometry has 2 bone(s) with elements below Y=0
  - **leem.idle**: C1 error > 1.0°/s (acceptable): 1.572°/s; Naturalness < 0.8: 0.154
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes

### deterrent/leemB (score: 80.0)
- Geometry has 4 bone(s) with elements below Y=0

### deterrent/leemSII (score: 83.0)
- Geometry has 2 bone(s) with elements below Y=0
  - **leemsii.idle**: C1 error > 1.0°/s (acceptable): 1.817°/s; Naturalness < 0.8: 0.143
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes

### deterrent/leemSIII (score: 78.0)
- Geometry has 3 bone(s) with elements below Y=0
  - **leemsiii.idle**: C1 error > 1.0°/s (acceptable): 1.366°/s; Naturalness < 0.8: 0.143
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes

### deterrent/leemSIV (score: 80.0)
- Geometry has 3 bone(s) with elements below Y=0
  - **leemsiv.idle**: Naturalness < 0.8: 0.143
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes

### deterrent/leemb (score: 80.0)
- Geometry has 4 bone(s) with elements below Y=0

### deterrent/leemsii (score: 83.0)
- Geometry has 2 bone(s) with elements below Y=0
  - **leemsii.idle**: C1 error > 1.0°/s (acceptable): 1.777°/s; Naturalness < 0.8: 0.125
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes

### deterrent/leemsiii (score: 78.0)
- Geometry has 3 bone(s) with elements below Y=0
  - **leemsiii.idle**: C1 error > 1.0°/s (acceptable): 1.356°/s; Naturalness < 0.8: 0.222
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes

### deterrent/leemsiv (score: 78.0)
- Geometry has 3 bone(s) with elements below Y=0
  - **leemsiv.idle**: C1 error > 1.0°/s (acceptable): 1.815°/s; Naturalness < 0.8: 0.444
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes

### deterrent/nak (score: 65.0)
- Geometry has 23 bone(s) with elements below Y=0
  - **nak.idle**: Naturalness < 0.8: 0.558
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes

### deterrent/rof (score: 83.0)
- Geometry has 2 bone(s) with elements below Y=0
  - **rof.idle**: C1 error > 1.0°/s (acceptable): 1.752°/s; Naturalness < 0.8: 0.056
    - 💡 Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes

... and 88 more models with issues

## Recommendations

- 💡 abomination/aboBodies/abobodies.walk: Enable septic_global_correction, increase transition_zone_max_ratio, or enable full_resample_velocity_correction
- 💡 abomination/aboBodies/abobodies.walk: Reduce correction magnitude, use walk_lightweight_c1 for walk anims, or increase walk_dp_epsilon_factor to preserve natural keyframes
- 💡 ancient/terla/terla.walk: Enable peak_preservation_enabled, increase peak_preservation_max_reduction, or reduce transition_zone_ratio
- 💡 derived/heblu/heblu.vomit: Enable final_c0_enforcement or increase loop_validation_iterations

## Quality Thresholds Used

```
  c0_perfect_threshold: 0.1
  c0_acceptable_threshold: 0.5
  c1_perfect_threshold: 1.0
  c1_acceptable_threshold: 5.0
  c2_perfect_threshold: 10.0
  c2_acceptable_threshold: 50.0
  amplitude_preservation_threshold: 0.9
  naturalness_threshold: 0.8
  y_min_threshold: 0.0
  transition_smoothness_threshold: 0.8
  periodicity_threshold: 0.5
  quality_score_excellent: 95.0
  quality_score_good: 80.0
  quality_score_acceptable: 60.0
  quality_score_poor: 40.0
```
