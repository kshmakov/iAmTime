# FINDINGS.md — experiment log

Append one entry per experiment that produced a result. Newest entries at the bottom. Never edit `THEORY.md`; if a result contradicts it, log it here as CONTRADICTS with the evidence. Result ids (R1–R12), questions (Q1–Q8) and planned experiments (E1–E15) refer to `THEORY.md`.

## Entry template

```
### <YYYY-MM-DD> — <entry id> — <one-line title>  [<THEORY ids: R#, E#, Q#>]
Hypothesis: <what was tested; copy from THEORY.md where it exists>
Setup: script/notebook (+ section), parameters (L, H, k, selector, N series × origins, seeds),
       data (dataset/config, split, snapshot), checkpoint, device/dtype, commit hash (or "uncommitted")
Result: numbers (mean / median MASE, win rate, Δ with 95 % CI, or the measured quantity);
        artifact paths (CSV, figures, notebook cell)
Implication for theory: what this does to the named result(s); the decisive number
Flag: CONFIRMS | CONTRADICTS | SUGGESTS-NEW-PATH | UNVERIFIED
```

Flag meanings:
- **CONFIRMS**: reproduced (at least two independent runs agree) and consistent with the named result.
- **CONTRADICTS**: reproduced and inconsistent with the named result as stated.
- **SUGGESTS-NEW-PATH**: reproduced, and tests something the theory does not state or only partly states.
- **UNVERIFIED**: the numbers come from saved notebook outputs or prose and have not been reproduced. The implication line then says what the flag would be once reproduced. `THEORY.md`'s preamble also mentions REFINES; until the theory owner decides how to map it, log a refinement as SUGGESTS-NEW-PATH and say so in the implication line.

## Backfill notes (2026-10-10)

The entries below were reconstructed from the repository on 2026-10-10 without running anything. Sources: git log, the notebooks' saved outputs, `notebooks/iamtime_forecasting_findings.md`, `notebooks/finance_dataset_handoff.md`, `notebooks/docs/figures/`, the finance data manifest and the pytest cache.

- **No result files exist.** No CSVs or per-series score tables were saved. Every number is copied from a notebook output cell (or, where stated, from Markdown prose with no output behind it). Figures in `notebooks/docs/figures/` are the only file artifacts.
- **Dates** are the notebook's last-saved time (outputs were produced on or before that day). **Commits**: `169951b` (2026-09-25, publish), `0bc7ac1` (2026-10-05, promotion strengths in the usage notebook), `6e02fab` (2026-10-06, fev-bench study notebooks). The finance notebook, `build_finance_dataset.py` and `tests/` are **uncommitted**.
- **Flags.** All backfilled entries are UNVERIFIED except the econ ones (B33–B40). `notebooks/iamtime_econ_forecasting_demo.ipynb` was re-executed from a fresh kernel on 2026-10-10 (working copy; figures `econ_*` re-saved 18:10–18:21). Every printed number matches the committed outputs in `6e02fab` exactly. That is two independent runs on the public checkpoint, so those entries carry a theory flag. I compared the two runs myself; I did not run them.
- **Rerunnable?** Notebooks on public fev-bench data with the public checkpoint can be rerun as they are. The finance notebook reruns only on this machine (the parquet is in the gitignored `notebooks/data/`). The Walmart eval notebook (B02) cannot be rerun from this repo: it loads a private checkpoint path on a remote GPU host. Prose-only claims (B11, B12, B17) have no code at all.
- **Overwritten figures.** `iamtime_walmart_forecasting_demo.ipynb` and `…demo.104.ipynb` save to the same figure names. The files on disk (20:48–20:50 on 2026-10-05) come from the 52-week notebook, so the 104-week variant's figures no longer exist.

---

## Entries

### 2026-10-05 — B01 — Synthetic promotion dose-response (usage notebook)  [R6, Q8]
Hypothesis: the model scales a planned promotion's uplift with its strength.
Setup: `notebooks/iamtime_forecasting_usage.ipynb` §3, "Promotion strength scenarios". Synthetic hourly demand, HISTORY=192, H=48, seed `default_rng(19)`. Two 1x promotions in the history; future promotions at 1x/2x/3x; uplift = scenario median − baseline. Public checkpoint, CPU float32. Commit `0bc7ac1`.
Result: predicted/true uplift (two windows) = 1x 0.93/0.93, 2x 0.93/0.95, 3x 0.86/0.86 (true 12/24/36; predicted 11.1–11.2 / 22.2–22.8 / 30.9–31.1). Figure: shown inline only, not saved. §4 (ICL with a driver covariate in the examples) is qualitative, with no score.
Implication for theory: monotone and sub-linear as R6 says, but the shrinkage at 3x is much milder (0.86) than on Walmart (0.67, B07). That supports Q8's idea that shrinkage depends on how far the value lies outside the history in normalised units, not on the raw multiple.
Flag: UNVERIFIED (would CONFIRM R6's sign and sub-linearity, and be evidence for Q8)

### 2026-10-05 — B02 — Walmart full-dataset 4-category evaluation (private checkpoint)  [R4, R9, new]
Hypothesis: none stated; a benchmark of zero-shot vs covariates vs in-series examples vs both.
Setup: `notebooks/iAmTime-Walmart-forecast-demo-eval.ipynb`. All 2,936 Walmart items (lengths 86–143); last H=39 weeks held out; full remaining history; batch 16. Examples: 3 random-length windows from the item's own history (no leakage), left-padded with NaN, `SEED=0`. MASE via gluonts with seasonality 1. **Checkpoint loaded from a private path** (`/home/jupyter/.../iamtime-checkpoint`, via GCS), CUDA, float32. Commit `6e02fab`.
Result (mean MASE; no CI or win rate reported): zero-shot 0.870; 10 covariates 0.823; 3 in-series examples 0.868; 10 covariates + 3 examples carrying covariates 0.852. Mean signed % error over the horizon: −5.6 / −2.5 / −3.6 / −1.9. Artifact: notebook cell 24 table; no files.
Implication for theory: covariates help at full scale (−5.4 %, consistent with R4). Random own-history examples are neutral when the history is long (consistent with R2). Adding examples that carry covariates gives back about a third of the covariate gain (0.823 → 0.852), which points the same way as R9 but is not a test of the covariate response. The checkpoint may not be the public one, and the device is CUDA, not CPU (breaks A5).
Flag: UNVERIFIED (not rerunnable from this repo)

### 2026-10-05 — B03 — Walmart zero-shot vs seasonal naive  [R7]
Hypothesis: zero-shot beats the domain baseline on persistent-structure retail series.
Setup: `iamtime_walmart_forecasting_demo.ipynb` §1b. 64 random complete series (`default_rng(0)`), L=104 w, H=39 w, MASE scaled by one-step naive. Public checkpoint, CPU float32. Commit `6e02fab`.
Result: zero-shot 0.799 (median 0.722) vs seasonal naive 0.956 (0.883); win rate 84.4 %; Δ −0.157 [−0.232, −0.083]. Figure `notebooks/docs/figures/01_univariate.png`.
Implication for theory: matches R7's Walmart row exactly.
Flag: UNVERIFIED (would CONFIRM R7)

### 2026-10-05 — B04 — Walmart multivariate: 80 hand-picked correlated triples  [R5, Q5]
Hypothesis: joint input of correlated departments helps.
Setup: demo §2b. Stores 1–20, 12 top-volume departments each, the 4 most-correlated triples per store (80 triples, 240 variates). Joint `(80,3,104)` vs each variate alone. Commit `6e02fab`.
Result: joint 0.652 (median 0.542) vs separate 0.671 (0.567); win rate 64.6 %; Δ −0.019 [−0.028, −0.010]. All three variates improved in 22/80 triples, at least one in 75/80. Hero triple correlations 0.85–0.90. Figure `02_multivariate.png`.
Implication for theory: matches R5's Walmart row; the only "reliable" multivariate gain, on a selected subset, with ρ ≈ 0.85–0.9 (the middle of Q5's inverted U).
Flag: UNVERIFIED (would CONFIRM R5)

### 2026-10-05 — B05 — Walmart 10 observed covariates  [R4]
Hypothesis: the dataset's covariates (observed future values) improve forecasts.
Setup: demo §3a (identical output in `iamtime_walmart_forecasting_usage.ipynb`). The same 64 series as B03, all 10 covariates as past + future. Commit `6e02fab`.
Result: mean 0.799 → 0.749, median 0.722 → 0.725; better on 36/64. No CI computed. Figure `03_exogenous_covariates.png`.
Implication for theory: matches R4's Walmart row. The gain is in the tail, not the median, and the future values are observed rather than forecast, so it is optimistic.
Flag: UNVERIFIED (would CONFIRM R4)

### 2026-10-05 — B06 — Walmart synthetic promotions 1x–3x and dose-response  [R6, E13, Q8]
Hypothesis: predicted uplift scales with planned strength; strengths beyond the history are extrapolated.
Setup: demo §3b–3c. Series `1_2`, uplift = 25 % of mean sales per unit strength. Past promotions at weeks 18–21 and 76–79 (1x); future windows at HISTORY+6..9 and +22..25. Strengths 0.5–3x; uplift = scenario median − 0x median. L=104. Commit `6e02fab`.
Result: predicted/true = 1.32, 1.02, 0.90, 0.81, 0.73, 0.67 at 0.5, 1, 1.5, 2, 2.5, 3x. Figures `03_promotion_scenarios.png`, `03_dose_response.png`.
Implication for theory: matches R6's Walmart numbers. One series, one origin, one uplift design.
Flag: UNVERIFIED (would CONFIRM R6)

### 2026-10-05 — B07 — Walmart ICL selector ladder + shuffled-futures control, L=52  [R1, R2, R3, X1, X2]
Hypothesis: examples help a 52-week query; the choice of examples matters; shuffled futures break the gain.
Setup: demo §4e–4f. 512 random series (`default_rng(1)`); query L=52; each example = 52-week history + 39-week future, one year earlier (L_e=L). 5 examples = own + 4 by the selector. k-means with 8 clusters on z-normalised 104-week histories. Control = season-matched set with futures rotated by one. Commit `6e02fab`.
Result (mean MASE; win rate vs zero-shot; Δ CI):
| variant | mean | median | win | Δ 95 % CI |
|---|---|---|---|---|
| zero-shot, 52 w | 1.026 | 0.874 | – | – |
| own example only | 1.019 | 0.850 | 0.553 | [−0.067, 0.058] |
| own + 4 random other-cluster | 0.958 | 0.822 | 0.594 | [−0.114, −0.016] |
| own + 4 cluster neighbours | 0.992 | 0.805 | 0.607 | [−0.094, 0.030] |
| own + 4 season-matched | 0.946 | 0.784 | 0.617 | [−0.131, −0.021] |
| own + 4 siblings (same dept) | 0.904 | 0.799 | 0.637 | [−0.165, −0.079] |
| control: season-matched, futures shuffled | 2.947 | 1.822 | 0.246 | [1.646, 2.202] |
Figures `04a_clusters.png`, `04b_*`, `04c_season_neighbours.png`, `04d_season_examples.png`, `04f_relevance_ladder.png`.
Implication for theory: matches the R1, R2 (g = 12 %) and R3 Walmart numbers. Note that **random other-cluster series also give a reliable gain** (CI excludes 0) while cluster neighbours do not. So on Walmart, "any 5 completed examples" captures about half of the best selector's gain.
Flag: UNVERIFIED (would CONFIRM R1, R2, R3)

### 2026-10-05 — B08 — Walmart k-shot curve, L=52  [R3c, R11, E15]
Hypothesis: error falls as season-matched examples are added; nothing breaks beyond k=6.
Setup: demo §4g. The first 256 of B07's series; own + (k−1) season-matched; k ∈ {0,1,2,4,6,8,10,12}. Commit `6e02fab`.
Result: mean 0.977, 0.977, 0.984, 0.940, 0.913, 0.894, 0.884, 0.887; median 0.840, 0.843, 0.832, 0.779, 0.777, 0.769, 0.786, 0.775. Figure `04g_example_count_curve.png`.
Implication for theory: matches R3(c) and R11 ("flat to 2, improving to 10"). On this subset k=0 is 0.977, not B07's 1.026, so quote gains against the subset's own k=0.
Flag: UNVERIFIED (would CONFIRM R3c, R11)

### 2026-10-05 — B09 — Walmart cold start, 12 weeks  [R2, R3, X4]
Hypothesis: sibling examples substitute for missing history.
Setup: demo §4h. 128 series; query L=12 w; 5 examples with L_e=12 w + 39-week future, one year earlier; the query's own past is not used. Commit `6e02fab`.
Result: zero-shot 1.329 (median 1.147); 5 siblings 1.059 (0.855), win 68.8 %, Δ −0.270 [−0.395, −0.133]; 5 season-matched (any department) 1.545 (1.035), win 57.8 %, Δ +0.216 [−0.106, 0.644]. Figures `04h_cold_start.png`, `04h_cold_start_prompt.png`, `04h_cold_start_ladder.png`.
Implication for theory: matches R2 (g = 20 %) and X4.
Flag: UNVERIFIED (would CONFIRM R2, R3, X4)

### 2026-10-05 — B10 — Walmart "teacher" examples carrying a promotion covariate, L=52  [R9, E5, E8]
Hypothesis: examples that demonstrate 1x–3x promotions teach the query the elasticity.
Setup: demo §4i. Query `1_2`, L=52 (one 1x promotion at relative weeks 24–27). 5 teachers = department 2 of stores 10–14, window = 52 + 39 weeks one year earlier (L_e=L=52). Teacher promotions sit at the same relative positions as the query's (history 24–27; future windows 6–9 and 22–25), with future strengths 1/1.5/2/2.5/3x. Covariates passed in `example_exog_*` and `query_exog_*`. Uplift vs the 0x scenario with the same examples. Commit `6e02fab`.
Result: predicted/true with teachers = −0.09, 0.03, 0.04, 0.05, 0.05, 0.05 at 0.5–3x; zero-shot (same 52 w) = 0.94, 0.90, 0.89, 0.82, 0.75, 0.69. Figure `04i_promotion_elasticity.png`.
Implication for theory: this is R9's source observation, and the numbers match.
Flag: UNVERIFIED (would CONFIRM R9's observation; it does not discriminate H9a/b/c)

### 2026-10-05 — B11 — R9 side checks (single example; 1x-only teachers; teachers without the covariate)  [R9]
Hypothesis: the collapse happens whenever examples carry the covariate.
Setup: described only in demo §4i's "Result" Markdown and in `notebooks/iamtime_forecasting_findings.md`. **No code or output in the repo.**
Result: prose only: "happens whenever the examples carry the promotion covariate, even with a single example and even when every example shows 1x promotions; the same examples without promotions leave the query's uplift intact."
Implication for theory: R9 cites this, but there is nothing to check it against. Reconstruct it in E5.
Flag: UNVERIFIED (no artifact)

### 2026-10-05 — B12 — Walmart full-population replication of the L=52 ladder (prose)  [R2, R3]
Hypothesis: the 512-series result holds on all series.
Setup: `iamtime_walmart_forecasting_usage.ipynb` §4e Markdown: "Running it on all 2,660 series gives…". **No output cell.**
Result (prose): mean (median) 0.794 (0.717) zero-shot 104 w; 1.031 (0.901) zero-shot 52 w; 1.013 (0.873) own; 0.954 (0.846) random other-cluster; 0.968 (0.840) cluster; 0.945 (0.834) season-matched.
Implication for theory: the same ordering as B07 (random other-cluster 0.954 beats cluster neighbours 0.968). Consistent with R3(b).
Flag: UNVERIFIED (no artifact)

### 2026-10-05 — B13 — Walmart long-context ceiling: zero-shot L=104 vs L=52  [R2, X8]
Hypothesis: a long own history beats short-context ICL.
Setup: `iamtime_walmart_forecasting_usage.ipynb` §4e; the same 512 series as B07. Commit `6e02fab`.
Result: zero-shot 104 w 0.784 (median 0.709) vs zero-shot 52 w 1.026 and the best 52-week ICL variant (siblings, B07) 0.904.
Implication for theory: matches R2's "Walmart zero-shot with L=104 (0.78) beats the best L=52 ICL variant (0.90)".
Flag: UNVERIFIED (would CONFIRM R2)

### 2026-10-05 — B14 — Walmart ICL ladder and k-curve with the full 104-week query  [R1, R2, X2, X8]
Hypothesis: examples still help when the query sees two full seasons.
Setup: `iamtime_walmart_forecasting_demo.104.ipynb` §4e–4g. The same 512 series and selectors as B07, but the query uses L=104 while examples keep L_e=52 (data starts 2010-02), **so L_e ≠ L, unlike A4**. Commit `6e02fab`. Figures were overwritten by B07's run.
Result (Δ vs zero-shot 104 w = 0.784, median 0.709): own +0.057 [0.033, 0.084]; own + 4 random +0.032 [0.014, 0.053]; cluster +0.041 [0.016, 0.070]; season-matched +0.033 [0.014, 0.055]; siblings +0.014 [−0.003, 0.031] (0.797, win 43.6 %); control 1.726 (+0.942 [0.780, 1.115]). k-curve mean: 0.775, 0.826, 0.828, 0.813, 0.798, 0.799, 0.793, 0.797 for k = 0, 1, 2, 4, 6, 8, 10, 12. Cold-start mature reference (zero-shot 104 w on B09's 128 series): 0.751.
Implication for theory: R2 predicts g → 0 at two seasons; here **g is reliably negative** (−4 % to −7 % for four of five selectors). Redundant examples cost accuracy rather than being neutral, which matters for E3's refute criterion. The shuffled control is still about 2× worse (R1 holds). The L_e ≠ L mismatch is a confound.
Flag: UNVERIFIED (would be SUGGESTS-NEW-PATH, a refinement of R2: g < 0 when redundant)

### 2026-10-05 — B15 — Walmart teacher examples with a promotion covariate, 104-week query  [R9, E5]
Hypothesis: as B10, with the query's full history.
Setup: `…demo.104.ipynb` §4i. Query `1_2`, L=104 (two 1x promotions, weeks 18–21 and 76–79). Teachers = department 2 of 5 other stores; example history = weeks 0–52 (L_e=52, one 1x promotion at 18–21); example future = weeks 52–91 with promotions at the query's future positions shifted one year back (the **same relative positions** as the query's planned windows), at strengths 1–3x. Covariates in `example_exog_*`. Commit `6e02fab`. The figure was overwritten.
Result: predicted/true with teachers = 1.65, 1.08, 0.93, 0.83, 0.76, 0.70 at 0.5–3x; zero-shot = 1.32, 1.02, 0.90, 0.81, 0.73, 0.67. **The query's covariate response is intact** (slightly larger), not collapsed.
Implication for theory: R9 says covariates inside examples suppress the query's response, and its side check (B11) claims generality. With teachers carrying the covariate and futures aligned at the query's event positions, the response is **not** suppressed when L=104 and L_e=52. The two runs differ mainly in query length / L_e≠L (and in the query history having 2 events instead of 1). Aligned futures are present in both, so this is evidence against H9a as the sole cause and suggests a new hypothesis: suppression requires L_e = L, i.e. identical query/example layout. That makes R9 conditional, not general.
Flag: UNVERIFIED (would be CONTRADICTS R9 as stated, scope only; the observation in B10 stands)

### 2026-10-05 — B16 — ERCOT zero-shot vs weekly seasonal naive  [R7]
Setup: `iamtime_energy_forecasting_demo.ipynb` §1b. 8 zones × 8 origins 6 weeks apart (64), L=8 w hourly, H=168 h, MASE season 24. Commit `6e02fab`.
Result: zero-shot 0.913 (median 0.856) vs 1.480 (1.285); win 93.8 %; Δ −0.567 [−0.686, −0.465]. Figure `energy_01_univariate.png`.
Implication for theory: matches R7.
Flag: UNVERIFIED (would CONFIRM R7)

### 2026-10-05 — B17 — proenfo_bull buildings ICL (prose)  [R2]
Setup: mentioned in energy notebook cell 0 and in `iamtime_forecasting_findings.md`: "examples from same-usage buildings did not improve on zero-shot in our tests, even for 14-day cold starts". **No code, output or figure.**
Implication for theory: would be an R2 case (14 days already contain the weekly cycle that drives building load). Not cited in `THEORY.md`.
Flag: UNVERIFIED (no artifact)

### 2026-10-05 — B18 — ETT 7-channel multivariate  [R5, Q5]
Setup: energy §2b. ETTh1 and ETTh2 × 10 origins 4 weeks apart (20 joint, 140 channel forecasts), L=8 w hourly, H=168, season 24. Commit `6e02fab`.
Result: joint 1.104 (median 0.939) vs 1.113 (0.959); win 55 %; Δ −0.008 [−0.030, 0.013]. Per channel joint vs alone: HUFL 1.074/1.120, MUFL 1.059/1.097, LULL 0.980/1.021, OT 1.316/1.241 (worse). Context correlations: HUFL–MUFL 0.99, OT ≈ −0.2 to 0.2 with the loads. Figure `energy_02_multivariate.png`.
Implication for theory: matches R5 and Q5's ETT observations. HUFL/MUFL (ρ = 0.99) *improve* here, which cuts against Q5's "losses at ρ ≈ 1" (that rests on Rossmann, B23).
Flag: UNVERIFIED (would CONFIRM R5; a counter-example for Q5's upper arm)

### 2026-10-05 — B19 — EPF day-ahead load/generation forecasts as covariates  [R4]
Setup: energy §3a. 5 markets × 24 origins at midnight, 15 days apart (120), L=4 w hourly, H=24, season 24. Commit `6e02fab`.
Result: with covariates 0.504 (median 0.388) vs without 0.600 (0.476); win 70 %; Δ −0.096 [−0.139, −0.054]; seasonal naive 0.918. Per market (without → with): BE 0.648 → 0.576, DE 0.503 → 0.349, FR 0.585 → 0.483, NP 0.622 → 0.541, PJM 0.641 → 0.569. Figure `energy_03_exogenous_prices.png`.
Implication for theory: matches R4 (g = 16 %, all five markets).
Flag: UNVERIFIED (would CONFIRM R4)

### 2026-10-05 — B20 — EPF renewable what-if and merit-order dose-response  [R6]
Setup: energy §3b–3c. DE, origin 2017-11-15; PV+wind forecast scaled 0.5–1.5x; slope vs an OLS of price on load + renewables + hour dummies over the 4-week context. Commit `6e02fab`.
Result: price change +3.73, +1.81, 0, −1.72, −3.38 €/MWh for −2.67 … +2.67 GW; model slope −1.33 vs historical −2.02 €/MWh per GW (0.66×). Figures `energy_03_renewable_scenarios.png`, `energy_03_dose_response.png`.
Implication for theory: matches R6. One origin, one market.
Flag: UNVERIFIED (would CONFIRM R6)

### 2026-10-05 — B21 — ENTSO-e daily load ICL ladder + control, L=56 d  [R1, R2, R3]
Setup: energy §4c. 6 countries, daily load (hourly summed), 256 random (country, weekly origin) pairs 2018-02 to 2019-11 (`default_rng(0)`). Query L=56, H=28, season 7; examples = the same window in earlier years (364-day shifts), own years first, then other countries by z-normalised season shape. Commit `6e02fab`.
Result:
| variant | mean | median | win | Δ 95 % CI |
|---|---|---|---|---|
| zero-shot | 1.315 | 1.111 | – | – |
| 1 own year | 1.125 | 0.999 | 0.547 | [−0.264, −0.118] |
| 3 own years | 1.052 | 0.902 | 0.621 | [−0.337, −0.191] |
| 3 own + 2 other countries | 1.047 | 0.941 | 0.629 | [−0.343, −0.194] |
| 5 other countries only | 1.114 | 1.052 | 0.559 | [−0.273, −0.129] |
| control (futures shuffled) | 6.043 | 4.459 | 0.086 | [4.113, 5.381] |
Figures `energy_04a_christmas.png`, `energy_04b_prompt_anatomy.png`, `energy_04c_relevance_ladder.png`.
Implication for theory: matches R1 (6.04 vs 1.32), R2 (g = 20 %) and R3.
Flag: UNVERIFIED (would CONFIRM R1, R2, R3)

### 2026-10-05 — B22 — ENTSO-e k-curve and 14-day cold start  [R3c, R11, R2]
Setup: energy §4d–4e, the same 256 pairs. k ∈ {0,1,2,3,4,6,8,10,12} from the ranked pool; cold start L=L_e=14 with the 5 best other-country windows. Commit `6e02fab`.
Result: k-curve mean 1.315, 1.125, 1.093, 1.052, 1.057, 1.045, 1.045, 1.044, 1.041. Cold start: 1.870 (median 1.528) → 1.608 (1.215), win 68.8 %, Δ −0.262 [−0.366, −0.158]. Figures `energy_04d_example_count_curve.png`, `energy_04e_cold_start.png`, `energy_04e_cold_start_ladder.png`.
Implication for theory: matches R3(c) ("flat after 3"), R11 (clean futures saturate early) and R2 cold start (g = 14 %).
Flag: UNVERIFIED (would CONFIRM R2, R3c, R11)

### 2026-10-05 — B23 — Rossmann zero-shot, sales+customers joint input, calendar covariates  [R7, R5, R4]
Setup: `iamtime_rossmann_forecasting_demo.ipynb` §1b, §2b, §3a. 934 complete stores; 64 random stores (`default_rng(0)`) × 2 origins (the last 48 days and 13 weeks earlier) = 128; L=364 d, H=48, MASE season 7. Commit `6e02fab`.
Result: zero-shot 0.658 (median 0.631) vs seasonal naive 0.794, win 82.8 %, Δ −0.136 [−0.163, −0.111]. Joint sales+customers (ρ = 0.99) 0.663 vs 0.652, win 29.3 %, Δ +0.012 [0.007, 0.016] (sales 0.665/0.658, customers 0.662/0.645). Covariates: none 0.658 → Open+holidays 0.554 (win **51.6 %**, Δ −0.104 [−0.139, −0.072]) → +Promo 0.375 (median 0.341, win 96.9 %, Δ −0.282 [−0.322, −0.244]). Figures `rossmann_01_univariate.png`, `rossmann_02_multivariate.png`, `rossmann_03_calendar_covariates.png`.
Implication for theory: matches R7, R5 and R4 (g = 43 %). The Open/holiday step wins on only half the forecasts: it fixes a few large errors on closed days rather than shifting the bulk.
Flag: UNVERIFIED (would CONFIRM R4, R5, R7)

### 2026-10-05 — B24 — Rossmann promotion-plan what-if and dose-response  [R6]
Setup: Rossmann §3b–3c. Store 1, origin = the last 48 days; promote on open weekdays of the first n weeks, n = 0..6; slope vs the store's own weekday-matched promo uplift in the 364-day context. Commit `6e02fab`.
Result: model 1,124 vs historical 1,210 extra sales per promotion day (0.93×), near-linear in promo days. Figures `rossmann_03_promo_scenarios.png`, `rossmann_03_dose_response.png`.
Implication for theory: matches R6. Promotions here are within the historical range, so no extrapolation is tested.
Flag: UNVERIFIED (would CONFIRM R6)

### 2026-10-05 — B25 — Rossmann Christmas ICL ladder + control, L=56 d  [R1, R2, R3]
Setup: Rossmann §4c (first table). 52 random stores (`default_rng(1)`) × 5 weekly origins 2014-11-10..12-08 (260). L=L_e=56, H=48; examples = the same window 364 days earlier; siblings = the same StoreType/Assortment ranked by last year's season shape. Commit `6e02fab`.
Result:
| variant | mean | median | win | Δ 95 % CI |
|---|---|---|---|---|
| zero-shot | 1.360 | 1.277 | – | – |
| 1 own (last year) | 1.072 | 1.017 | 0.969 | [−0.329, −0.250] |
| own + 4 siblings | 1.016 | 0.965 | 0.992 | [−0.377, −0.313] |
| 5 siblings, no own | 1.020 | 0.982 | 0.988 | [−0.372, −0.310] |
| own + 4 random other-class | 1.045 | 1.010 | 0.962 | [−0.348, −0.284] |
| control (futures shuffled) | 1.197 | 1.083 | 0.792 | [−0.205, −0.119] |
Figures `rossmann_04a_christmas.png`, `rossmann_04b_prompt_anatomy.png`, `rossmann_04c_christmas_ladder.png`.
Implication for theory: matches R1's stated exception (the control beats zero-shot), R2 (g = 25 %) and R3. Random other-class stores get 92 % of the sibling gain, so selection matters little when every future contains Christmas.
Flag: UNVERIFIED (would CONFIRM R1, R2, R3)

### 2026-10-05 — B26 — Rossmann year-round ICL, L=56 d  [R2, X2]
Setup: Rossmann §4c (second table). 256 random store-origin pairs, weekly origins 2014-02-25..2015-06-09 (`default_rng(0)`). Commit `6e02fab`.
Result: zero-shot 0.713 (median 0.609); own last year 0.784, win 43.4 %, Δ +0.071 [0.008, 0.174]; own + 4 siblings 0.731, win 48.4 %, Δ +0.019 [−0.013, 0.049]; control 0.876, Δ +0.163 [0.120, 0.207].
Implication for theory: matches R2 and X2 (own year alone is reliably worse). The shuffled control is worse than zero-shot here, as R1 expects.
Flag: UNVERIFIED (would CONFIRM R2)

### 2026-10-05 — B27 — Rossmann new store (14 d) cold start + control, and k-curve  [R1, R2, R3, R11]
Setup: Rossmann §4d–4e. B26's 256 pairs; query L=L_e=14, H=48; siblings ranked by their last 14 days' shape (same class); the query's own past is not used. k ∈ {0,1,2,3,5,8,10,12}. Commit `6e02fab`.
Result: zero-shot 1.234 (median 1.116); 5 siblings 0.924 (0.857), win 89.5 %, Δ −0.310 [−0.346, −0.275]; 5 random other-class 0.957, win 88.3 %, Δ −0.277 [−0.311, −0.244]; **control (shuffled) 1.033, win 75.8 %, Δ −0.201 [−0.242, −0.162]**. k-curve mean 1.234, 0.962, 0.945, 0.937, 0.924, 0.918, 0.914, 0.911. Figures `rossmann_04d_new_store.png`, `rossmann_04d_new_store_ladder.png`, `rossmann_04e_example_count_curve.png`.
Implication for theory: R2 (g = 25 %) and R3(c) (most of the gain at k=1) match. But (i) the shuffled control **beats** zero-shot here too, so R1's list of exceptions (Christmas only) is incomplete. A plausible joint preserved by π is the weekly open/closed pattern shared by all store futures, which fits R1's explanation but should be stated. (ii) Random stores of other classes give 89 % of the sibling gain, so "selection matters more than count" (R3) does not hold for Rossmann cold start.
Flag: UNVERIFIED (would be SUGGESTS-NEW-PATH for R1's exception list and R3's scope)

### 2026-10-06 — B28 — Finance dataset build and unit tests (infrastructure)  [none]
Setup: `notebooks/build_finance_dataset.py --snapshot 2026-10-02 --start 2015-01-01`; manifest `notebooks/data/finance_sp500_2026-10-02_manifest.json` (built_on 2026-10-06, 499 tickers, 2,955 trading days, 43,434 earnings rows, FOMC source "built-in", sha256 `fe603944…f586`). `tests/test_build_finance_dataset.py`: 12 tests, all passed in the last pytest run (`.pytest_cache`, no `lastfailed`). Uncommitted; `notebooks/data/` is gitignored.
Result: no forecasting result. Note that `finance_dataset_handoff.md` §7 still says "Roadmap 1 (live run): not yet run", which is stale: the full build exists.
Implication for theory: none. Prerequisite for B29–B32. The FOMC dates are typed from memory (handoff §4.1) and unverified.
Flag: UNVERIFIED

### 2026-10-06 — B29 — Finance zero-shot: log volume, realised vol, returns  [R7, X10]
Setup: `notebooks/iamtime_finance_forecasting_demo.ipynb` §1b. 464 complete tickers; 128 random (ticker, origin) pairs (`default_rng(0)`), 8 monthly origins in the last year; L=252, H=20, MASE season 1. Public checkpoint, CPU float32. Uncommitted.
Result: log volume: zero-shot 1.036 (median 0.978) vs random walk 1.285, 20-day mean 1.074, weekly seasonal naive 1.319. Realised vol (Garman–Klass): 0.842 vs 20-day mean 0.845, random walk 1.131. Returns: 0.773 vs zero forecast 0.769, Δ +0.004 [0.001, 0.007]. Figure `finance_01_univariate.png`.
Implication for theory: matches R7 and X10. No paired CI vs the 20-day mean was computed (the reference was the random walk), so "tie" is inferred from overlapping means.
Flag: UNVERIFIED (would CONFIRM R7)

### 2026-10-06 — B30 — Finance multivariate groupings  [R5, Q5]
Setup: finance §2a–2c. k-means (11 clusters) on z-normalised returns over the first 3 years (ARI vs GICS sectors 0.47). Joint vs separate log-volume forecasts over 4 origins 63 days apart (`default_rng(1)`); L=252, H=20. Uncommitted.
Result (Δ joint − separate, CI): within-ticker (vol, rv, |ret|) −0.014 [−0.024, −0.005], win 66.7 %; same industry −0.008 [−0.016, −0.001]; same k-means −0.008 [−0.014, −0.003]; random −0.006 [−0.012, −0.000]. Hero triple (BSX, ABT, MDT) ρ ≈ 0.55. Figure `finance_02_industry_triple.png`.
Implication for theory: matches R5 (tiny gains; random is no worse than structured). Every CI technically excludes 0, so "no dependable gain" means "negligible", not "not significant".
Flag: UNVERIFIED (would CONFIRM R5)

### 2026-10-06 — B31 — Finance calendar, earnings and market covariates; earnings what-if; surprise dose-response  [R4, R6, R10, Q7]
Setup: finance §3a–3c. B29's 128 pairs. Known-future: CALENDAR (opex, triple witching, FOMC, month/quarter end, weekday) and EARNINGS (day, reaction, window, days-to); past-only: VIX, SPX, sector ETF, 10y, 10y−2y, sentiment. Dose-response: hero stock, `eps_surprise_pct` passed **as known-future** at the reaction day, 0–40 %. Uncommitted.
Result: none 1.036 → calendar 0.995 (win 69.5 %) → + earnings 0.957 (median 0.894, win 73.4 %, Δ −0.079 [−0.104, −0.056]) → + past-only market 0.967. On the 38/128 pairs with an earnings reaction in the horizon: 1.104 → 1.042 → 0.921 (win 89.5 %, Δ −0.182 [−0.245, −0.134]) → 0.925. Surprise response (log-volume change on the reaction day): 0.142, 0.171, 0.189, 0.203, 0.215 at 2, 5, 10, 20, 40 % vs a pooled regression 0.84 + 0.0011·|surprise| over 20,594 announcements. The earnings-date what-if is a figure only (`finance_03_earnings_scenarios.png`). Figures `finance_03_calendar_covariates.png`, `finance_03_surprise_dose_response.png`.
Implication for theory: matches R4 (g = 8 % / 17 %) and R6 (concave). Contexts of 252 days contain ~4 announcements, so R10's zero-event case is not exercised. The model's 2 % → 40 % increment (0.07) is of the same order as the regression's (0.04). Absolute levels are not comparable: the model's response is relative to a 0 % surprise with the earnings flags already present, while the regression's 0.84 intercept is the whole abnormal volume. Most of the 0 → 2 % step (0.14) is a jump at the first non-zero value, which a sparse past-only covariate fed as known-future may cause (related to R10).
Flag: UNVERIFIED (would CONFIRM R4, R6)

### 2026-10-06 — B32 — Finance event-aligned ICL ladder + control, cold start, k-curve  [R1, R8, R11]
Setup: finance §4c–4e. 256 event queries (from 2023-09-28), lead 2–15 days before an earnings reaction; L=L_e=40, H=20; examples aligned at the same lead from own earlier announcements and industry peers; cold start L=L_e=20 with peers only. Uncommitted.
Result: zero-shot 1.240 (median 1.103); 1 own 1.353 (Δ +0.113 [0.071, 0.156]); 4 own 1.230 (Δ −0.010 [−0.047, 0.027]); 2 own + 3 peers 1.296 (+0.056 [0.017, 0.097]); 5 peers 1.302 (+0.062 [0.018, 0.107]); 5 non-aligned own 1.348 (+0.108 [0.066, 0.146]); control 1.884 (+0.644 [0.498, 0.800]). Cold start: 1.393 → 1.435 (Δ +0.042 [−0.019, 0.107]); control 2.478. k-curve mean 1.240, 1.353, 1.333, 1.307, 1.230, 1.231, 1.223, 1.213, 1.208. Figures `finance_04a_event_examples.png`, `finance_04b_prompt_anatomy.png`, `finance_04c_relevance_ladder.png`, `finance_04d_cold_start_ladder.png`, `finance_04e_example_count_curve.png`.
Implication for theory: matches R8, R1 (control 1.88 / 2.48) and R11's prediction (ii). Aligned own examples (1.230 at k=4) beat non-aligned own windows (1.348), so alignment carries *some* information even though nothing beats zero-shot.
Flag: UNVERIFIED (would CONFIRM R1, R8, R11)

### 2026-10-06 — B33 — US consumption zero-shot vs random walk with drift  [R7]
Setup: `notebooks/iamtime_econ_forecasting_demo.ipynb` §1b. 31 categories × 10 yearly origins 2015–2024 (310), L=120 months, H=12, MASE season 1. Public checkpoint, CPU float32. Commit `6e02fab`; re-run 2026-10-10 (working copy) with identical output.
Result: zero-shot 3.930 (median 2.434) vs 4.228 (2.588); win 56.8 %; Δ −0.298 [−0.493, −0.101]. By year (RW / iAmTime): 2015 2.18/2.70, 2018 2.83/2.88, 2024 1.35/1.71 (iAmTime worse); 2020 11.88/11.42. Figure `econ_01_univariate.png`.
Implication for theory: R7 as stated.
Flag: CONFIRMS R7

### 2026-10-06 — B34 — FRED-MD CEE trio multivariate  [R5]
Setup: econ §2b. PAYEMS, CPIAUCSL, FEDFUNDS; 20 yearly origins 2005–2024 (60 forecasts); L=240, H=12. Commit `6e02fab`; reproduced 2026-10-10.
Result: joint 4.854 (median 2.787) vs 5.046 (2.862); win 46.7 %; Δ −0.192 [−0.595, 0.115]. Per variable: PAYEMS 5.141/5.369, CPI 5.235/5.616, FEDFUNDS 4.187/4.155. Figure `econ_02_multivariate.png`.
Implication for theory: R5's FRED row as stated.
Flag: CONFIRMS R5

### 2026-10-06 — B35 — GVAR inflation with past-only vs oracle-future commodity prices  [R4, X7]
Setup: econ §3a. 33 countries × 6 origins 2011–2021 (198); target Dp, L=60 quarters, H=8; covariates poil, pmat, pmetal. Commit `6e02fab`; reproduced 2026-10-10.
Result: none 1.217 (median 0.889); past-only 1.214, win 51.0 %, Δ −0.004 [−0.015, 0.007]; oracle future 1.150 (0.845), win 67.7 %, Δ −0.067 [−0.095, −0.041]. By year, the oracle gain is concentrated in 2013, 2019 and 2021. Figure `econ_03_inflation_commodities.png`.
Implication for theory: R4's past-only vs future-path contrast as stated.
Flag: CONFIRMS R4

### 2026-10-06 — B36 — Oil-price scenarios and pass-through dose-response  [R6]
Setup: econ §3b–3c. US, DE, JP, IN at the last origin; oil path linear to −40..+40 % over 8 quarters, other commodities flat; compared with an OLS Dp ~ Δpoil + lag over the 60-quarter context. Commit `6e02fab`; reproduced 2026-10-10.
Result (pp per +40 % oil, model / regression): US 0.021/0.177, DE 0.034/0.088, JP 0.064/0.045, IN 0.117/0.064; monotone and positive in all four. Figures `econ_03_oil_scenarios.png`, `econ_03_dose_response.png`.
Implication for theory: R6's oil row (ratios 0.12×–1.83×) as stated. The ratio varies 15× across countries, which does not fit a single "shrinks by 20–33 %" rule. R6's quantitative shrinkage claim rests on Walmart's synthetic promotion (B06) only.
Flag: CONFIRMS R6 (sign and monotonicity); the magnitude rule is not supported outside retail

### 2026-10-06 — B37 — GDP analogue examples ladder + control, L=20 quarters  [R1, R3, Q4]
Setup: econ §4c (GDP). 256 random (country, yearly origin 1999–2021) pairs (`default_rng(0)`); L=L_e=20, H=8; analogues = nearest z-normalised 20-quarter windows from any country (non-overlapping per country, futures ending before the origin). Commit `6e02fab`; reproduced 2026-10-10.
Result: zero-shot 2.790 (median 2.130); **5 analogues, own country only 2.750, win 48.0 %, Δ −0.040 [−0.234, 0.159] (n.s.)**; 5 analogues, any country 2.486 (1.743), win 56.2 %, Δ −0.304 [−0.476, −0.134]; 10 any-country 2.487; **5 random windows 2.814 (n.s.)**; control 8.303 (Δ +5.513 [4.807, 6.263]). Figures `econ_04a_analogues.png`, `econ_04b_prompt_anatomy.png`, `econ_04c_relevance_ladder.png`.
Implication for theory: R1 (8.30 vs 2.79) as stated. For R3, GDP is a case where **similarity search across series beats the structural "own earlier years" selector** (own country only: no gain) and random windows give nothing. That runs against R3(a)'s general claim that structural selectors beat similarity search, and fits Q4's signal-to-noise conjecture: GDP is smooth, so the context's shape is informative.
Flag: SUGGESTS-NEW-PATH (limits R3a's scope; supports Q4)

### 2026-10-06 — B38 — Inflation analogue examples  [R3, X3, Q4]
Setup: econ §4c (second table). The same 256 pairs and design as B37, target Dp. Commit `6e02fab`; reproduced 2026-10-10.
Result: zero-shot 1.282 (median 0.981); 5 analogues 1.573, win 25.0 %, Δ +0.291 [0.215, 0.378]; 10 analogues 1.488 (+0.206 [0.145, 0.268]); 5 random windows 1.400 (+0.117 [0.052, 0.188]).
Implication for theory: X3 and Q4's GVAR-inflation evidence as stated. Random windows are also reliably harmful (not neutral), consistent with R1's corollary.
Flag: CONFIRMS X3

### 2026-10-06 — B39 — GDP analogue k-curve  [R3c, R11]
Setup: econ §4d, the same 256 pairs; k ∈ {0,1,2,3,5,8,10,12} any-country analogues. Commit `6e02fab`; reproduced 2026-10-10.
Result: mean 2.790, 2.829, 2.640, 2.545, 2.486, 2.511, 2.487, 2.481; median 2.130, 1.988, 1.977, 1.801, 1.743, 1.656, 1.713, 1.689. Figure `econ_04d_example_count_curve.png`.
Implication for theory: R3(c) ("2.79 → 2.49 at k=5, flat after") as stated. k=1 is slightly worse than zero-shot, the noisy-template signature R11 predicts.
Flag: CONFIRMS R3c

### 2026-10-06 — B40 — GDP cold start, 8 quarters  [R2, Q4]
Setup: econ §4e, the same 256 pairs; L=L_e=8; 5 analogues from other countries; MASE scaled on the 8-quarter context. Commit `6e02fab`; reproduced 2026-10-10.
Result: zero-shot 3.277 (median 2.584); with analogues 3.385 (2.692), win 48.4 %, Δ +0.108 [−0.139, 0.347]. Figure `econ_04e_cold_start_ladder.png`.
Implication for theory: Q4's "GDP cold start with 8 quarters: no gain" as stated. It is also the one cold start of four with no gain, so R2's cold-start claim needs a minimum context for a similarity selector to work.
Flag: CONFIRMS Q4's observation

---

## Gaps

### Theory results with no experiment yet

- **E1, reproduction of the reference rows.** Only the econ notebook has been reproduced (B33–B40). Every Walmart, Rossmann, energy and finance number in R1–R8 rests on a single saved run. B02 uses a private checkpoint on CUDA, contrary to A1/A5.
- **R9 mechanism (H9a / H9b / H9c, E5).** No discriminating run exists. The only evidence is B10 (the observation), B11 (prose-only side checks) and B15, which points to a fourth factor (L_e = L) that the theory does not list.
- **R10, degenerate-scale covariates (E7).** Untested. No run fed a known-future flag with an event-free context (finance contexts have ~4 events; Walmart's `IsHoliday` in a 104-week context always has events).
- **R12 / pipeline contract (E14) and R5's code fact (E12).** No tests in `tests/` touch `pipeline.py`. One related clue: B02's builder comments say that, without `query_target_future = NaN(H)`, the padder used length 1 for example futures. The current `pipeline._process_icl_inputs` right-pads to `prediction_length`, so this may be an older internal pipeline. It is worth a case in E14.
- **R2 monotonicity in L (E3).** At most three context lengths per dataset (Walmart 12/52/104 w, Rossmann 14/56 d, ENTSO-e 14/56 d), never a sweep, and the 104-week point has L_e ≠ L (B14).
- **R1 graded shuffling and time-shift control (E2).** Only full rotation has been run.
- **R3 robustness (E4).** Single seed and single sample everywhere; no stratification by seasonal strength or SNR.
- **R6 measurement validity (E13) and Q8 (E11).** No perturbation test of the uplift measure. The dose-response magnitude rule rests on one synthetic Walmart series (B06); B01 and B36 suggest it does not generalise.
- **R8 discrimination (E6), Q3 regime examples (E8), Q5 correlation sweep (E9), Q7 timing vs magnitude (E10), R11 dispersion model (E15).** None started. The existing k-curves (B08, B22, B27, B32, B39) are reusable inputs for E15.
- **No per-series score files anywhere.** Section 5 of THEORY.md asks for `research/exp_<id>.py` writing CSVs; none exist, so no backfilled result can be re-analysed without rerunning.

### Experiments that test nothing currently stated in the theory

- **B02**, the full-dataset 4-category benchmark: random in-series examples are neutral at full history (0.868 vs 0.870); covariates cut the mean signed bias from −5.6 % to −2.5 %; examples carrying covariates erode the covariate gain. Horizon bias and APE by quarter are not in the theory.
- **B15**, the 104-week teacher run: the covariate response survives example covariates. Not in THEORY.md, and it bears directly on R9/Q1.
- **B14**, redundant examples are reliably harmful (g < 0), not neutral. R2 only predicts g → 0.
- **B37**, own-country vs any-country analogues for GDP: an explicit selector contrast THEORY.md does not record.
- **B27 control and random-class results**: a second shuffled-control exception and near-equal random vs sibling selection, neither in R1 or R3.
- **B01**, synthetic dose-response with milder shrinkage, and the qualitative synthetic ICL-with-covariates example in the same notebook. Not cited.
- **B17** (proenfo_bull, prose only) and **B12** (2,660-series replication, prose only): cited in `iamtime_forecasting_findings.md` but not in THEORY.md, and without artifacts.
- **B28**, finance dataset build and unit tests: infrastructure; tests no theory statement.
- **B30's k-means vs GICS ARI = 0.47** and **B31's earnings-date what-if** (figure only): descriptive, with no corresponding claim.
