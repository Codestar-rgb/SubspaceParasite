# Quality Audit Report

**Timestamp:** 2026-06-05T17:45:49.430937+00:00
**Threshold Mode:** default
**Total Models:** 2
**Total Animations:** 9

## 1. Executive Summary

| Metric | Value |
|--------|-------|
| C0 Perfect Rate | 22.2% |
| C1 Perfect Rate | 33.3% |
| Average Naturalness | 0.9828 |
| Naturalness Below Threshold | 0 |
| Average Amplitude Retention | 0.9842 |
| Amplitude Below Threshold | 0 |
| Critical Issues | 7 |
| Important Issues | 6 |

## 2. Overall Statistics

| Statistic | Quality Score | Naturalness | C0 Max Error (deg) | C1 Max Error (deg/s) |
|-----------|--------------|-------------|--------------------|---------------------|
| Mean | 66.48 | 0.9828 | 20.3551 | 47.4320 |
| Min | 53.24 | 0.8598 | 0.0000 | 0.0000 |
| Max | 100.00 | 1.0000 | 41.4596 | 127.7396 |

## 3. Quality Grade Distribution

  A:   2 ( 22.2%) ███████████
  B:   0 (  0.0%) 
  C:   1 ( 11.1%) █████
  D:   6 ( 66.7%) █████████████████████████████████
  F:   0 (  0.0%) 

## 4. Per-Category Breakdown

| Category | Count | Avg Score | Avg Naturalness | C0 Perfect % | C1 Perfect % |
|----------|-------|-----------|----------------|-------------|-------------|
| attack | 1 | 55.0 | 1.0000 | 0.0% | 0.0% |
| fly | 2 | 76.1 | 1.0000 | 50.0% | 50.0% |
| idle | 2 | 63.2 | 0.9299 | 0.0% | 50.0% |
| other | 4 | 66.2 | 0.9964 | 25.0% | 25.0% |

## 5. Critical Issues

1. **heblu/animation.model.fly**: C0 error 41.46 deg exceeds 5 deg critical threshold
2. **heblu/animation.model.cosmic**: C0 error 27.43 deg exceeds 5 deg critical threshold
3. **heblu/animation.model.idle**: C0 error 27.41 deg exceeds 5 deg critical threshold
4. **heblu/animation.model.attack**: C0 error 24.13 deg exceeds 5 deg critical threshold
5. **heblu/animation.model.shaking**: C0 error 24.00 deg exceeds 5 deg critical threshold
6. **heblu/animation.model.cosmic_shaking**: C0 error 24.00 deg exceeds 5 deg critical threshold
7. **kirin/animation.srparasites.kirin.idle**: C0 error 14.77 deg exceeds 5 deg critical threshold

## 6. Important Issues

1. **heblu/animation.model.fly**: C1 error 127.74 deg/s is >3x threshold (4.50)
2. **heblu/animation.model.cosmic**: C1 error 75.13 deg/s is >3x threshold (4.50)
3. **heblu/animation.model.idle**: C1 error 69.84 deg/s is >3x threshold (4.50)
4. **heblu/animation.model.attack**: C1 error 53.60 deg/s is >3x threshold (4.50)
5. **heblu/animation.model.shaking**: C1 error 50.43 deg/s is >3x threshold (4.50)
6. **heblu/animation.model.cosmic_shaking**: C1 error 49.04 deg/s is >3x threshold (4.50)

## 7. Top 10 Worst Animations

| # | Animation | Score | Grade | C0 Error | C1 Error | Naturalness | Amp Retention |
|---|-----------|-------|-------|----------|----------|-------------|--------------|
| 1 | heblu/animation.model.fly | 53.2 | D | 41.4596 | 127.7396 | 1.0000 | 0.9121 |
| 2 | heblu/animation.model.cosmic_shaking | 54.7 | D | 23.9982 | 49.0428 | 0.9892 | 1.0000 |
| 3 | heblu/animation.model.shaking | 55.0 | D | 23.9982 | 50.4309 | 0.9979 | 1.0000 |
| 4 | heblu/animation.model.cosmic | 55.0 | D | 27.4307 | 75.1336 | 0.9984 | 1.0000 |
| 5 | heblu/animation.model.idle | 55.0 | D | 27.4090 | 69.8408 | 1.0000 | 1.0000 |
| 6 | heblu/animation.model.attack | 55.0 | D | 24.1329 | 53.5998 | 1.0000 | 1.0000 |
| 7 | kirin/animation.srparasites.kirin.idle | 71.5 | C | 14.7671 | 1.1002 | 0.8598 | 1.0000 |
| 8 | heblu/animation.model.fly_vomit | 98.9 | A | 0.0000 | 0.0000 | 1.0000 | 0.9455 |
| 9 | heblu/animation.model.vomit | 100.0 | A | 0.0000 | 0.0000 | 1.0000 | 1.0000 |

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
- **Average naturalness:** 0.9828
- **Below threshold (0.8):** 0 animations

## 10. Improvement Over Previous

- **c0_perfect_rate:** +0.0000 ↓
- **c1_perfect_rate:** +0.0000 ↓
- **naturalness_avg:** +0.0000 ↓
- **amplitude_retention_avg:** +0.0000 ↓
