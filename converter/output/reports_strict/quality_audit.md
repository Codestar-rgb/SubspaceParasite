# Quality Audit Report

**Timestamp:** 2026-06-05T17:42:41.013336+00:00
**Threshold Mode:** strict
**Total Models:** 2
**Total Animations:** 9

## 1. Executive Summary

| Metric | Value |
|--------|-------|
| C0 Perfect Rate | 22.2% |
| C1 Perfect Rate | 22.2% |
| Average Naturalness | 0.7773 |
| Naturalness Below Threshold | 9 |
| Average Amplitude Retention | 0.9842 |
| Amplitude Below Threshold | 2 |
| Critical Issues | 7 |
| Important Issues | 6 |

## 2. Overall Statistics

| Statistic | Quality Score | Naturalness | C0 Max Error (deg) | C1 Max Error (deg/s) |
|-----------|--------------|-------------|--------------------|---------------------|
| Mean | 61.03 | 0.7773 | 20.3551 | 47.4320 |
| Min | 49.22 | 0.5111 | 0.0000 | 0.0000 |
| Max | 95.69 | 0.8435 | 41.4596 | 127.7396 |

## 3. Quality Grade Distribution

  A:   2 ( 22.2%) ███████████
  B:   0 (  0.0%) 
  C:   0 (  0.0%) 
  D:   4 ( 44.4%) ██████████████████████
  F:   3 ( 33.3%) ████████████████

## 4. Per-Category Breakdown

| Category | Count | Avg Score | Avg Naturalness | C0 Perfect % | C1 Perfect % |
|----------|-------|-----------|----------------|-------------|-------------|
| attack | 1 | 50.1 | 0.8042 | 0.0% | 0.0% |
| fly | 2 | 72.1 | 0.8413 | 50.0% | 50.0% |
| idle | 2 | 55.0 | 0.6570 | 0.0% | 0.0% |
| other | 4 | 61.2 | 0.7987 | 25.0% | 25.0% |

## 5. Critical Issues

1. **heblu/animation.model.fly**: C0 error 41.46 deg exceeds 5 deg critical threshold
2. **heblu/animation.model.cosmic**: C0 error 27.43 deg exceeds 5 deg critical threshold
3. **heblu/animation.model.idle**: C0 error 27.41 deg exceeds 5 deg critical threshold
4. **heblu/animation.model.attack**: C0 error 24.13 deg exceeds 5 deg critical threshold
5. **heblu/animation.model.shaking**: C0 error 24.00 deg exceeds 5 deg critical threshold
6. **heblu/animation.model.cosmic_shaking**: C0 error 24.00 deg exceeds 5 deg critical threshold
7. **kirin/animation.srparasites.kirin.idle**: C0 error 14.77 deg exceeds 5 deg critical threshold

## 6. Important Issues

1. **heblu/animation.model.fly**: C1 error 127.74 deg/s is >3x threshold (3.00)
2. **heblu/animation.model.cosmic**: C1 error 75.13 deg/s is >3x threshold (3.00)
3. **heblu/animation.model.idle**: C1 error 69.84 deg/s is >3x threshold (3.00)
4. **heblu/animation.model.attack**: C1 error 53.60 deg/s is >3x threshold (3.00)
5. **heblu/animation.model.shaking**: C1 error 50.43 deg/s is >3x threshold (3.00)
6. **heblu/animation.model.cosmic_shaking**: C1 error 49.04 deg/s is >3x threshold (3.00)

## 7. Top 10 Worst Animations

| # | Animation | Score | Grade | C0 Error | C1 Error | Naturalness | Amp Retention |
|---|-----------|-------|-------|----------|----------|-------------|--------------|
| 1 | heblu/animation.model.fly | 49.2 | F | 41.4596 | 127.7396 | 0.8391 | 0.9121 |
| 2 | heblu/animation.model.cosmic_shaking | 49.4 | F | 23.9982 | 49.0428 | 0.7738 | 1.0000 |
| 3 | heblu/animation.model.shaking | 49.4 | F | 23.9982 | 50.4309 | 0.7755 | 1.0000 |
| 4 | heblu/animation.model.idle | 50.1 | D | 27.4090 | 69.8408 | 0.8029 | 1.0000 |
| 5 | heblu/animation.model.attack | 50.1 | D | 24.1329 | 53.5998 | 0.8042 | 1.0000 |
| 6 | heblu/animation.model.cosmic | 50.5 | D | 27.4307 | 75.1336 | 0.8178 | 1.0000 |
| 7 | kirin/animation.srparasites.kirin.idle | 60.0 | D | 14.7671 | 1.1002 | 0.5111 | 1.0000 |
| 8 | heblu/animation.model.fly_vomit | 95.0 | A | 0.0000 | 0.0000 | 0.8435 | 0.9455 |
| 9 | heblu/animation.model.vomit | 95.7 | A | 0.0000 | 0.0000 | 0.8276 | 1.0000 |

## 8. Amplitude Retention Analysis

- **Average retention:** 0.9829
- **Minimum retention:** 0.0000
- **Channels below threshold:** 17

Worst retention channels:
  - heblu/animation.model.fly / hjointD_1/rotation/z: 0.0000
  - heblu/animation.model.fly / hjointF_1/rotation/z: 0.0000
  - heblu/animation.model.fly / hjointB_1/rotation/z: 0.0000
  - heblu/animation.model.fly / hjointH_1/rotation/z: 0.0000
  - heblu/animation.model.fly / hjointA_1/rotation/z: 0.0000
  - heblu/animation.model.fly / hjointE_1/rotation/z: 0.0000
  - heblu/animation.model.fly_vomit / hjointD_1/rotation/z: 0.0000
  - heblu/animation.model.fly_vomit / hjointF_1/rotation/z: 0.0000
  - heblu/animation.model.fly_vomit / hjointB_1/rotation/z: 0.0000
  - heblu/animation.model.fly_vomit / hjointH_1/rotation/z: 0.0000

## 9. Naturalness Analysis

- **Method:** curvature_smoothness (replaces legacy sign-change counting)
- **Average naturalness:** 0.7773
- **Below threshold (0.9):** 9 animations

Animations with lowest naturalness:
  - kirin/animation.srparasites.kirin.idle: 0.5111 (method: curvature_smoothness)
  - heblu/animation.model.cosmic_shaking: 0.7738 (method: curvature_smoothness)
  - heblu/animation.model.shaking: 0.7755 (method: curvature_smoothness)
  - heblu/animation.model.idle: 0.8029 (method: curvature_smoothness)
  - heblu/animation.model.attack: 0.8042 (method: curvature_smoothness)
  - heblu/animation.model.cosmic: 0.8178 (method: curvature_smoothness)
  - heblu/animation.model.vomit: 0.8276 (method: curvature_smoothness)
  - heblu/animation.model.fly: 0.8391 (method: curvature_smoothness)
  - heblu/animation.model.fly_vomit: 0.8435 (method: curvature_smoothness)

## 10. Improvement Over Previous

_No previous report available for comparison._
