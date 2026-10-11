# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

iAmTime is a time-series foundation model for instruction-conditioned in-context learning (ICL): an *episode* is a prompt made of completed support examples (history → future) plus a query whose future is predicted. One architecture covers forecasting, imputation, anomaly detection and classification, but **only the forecasting checkpoint is released** (`anishsaha/iAmTime-base-forecast` on the HF Hub). Paper: arXiv:2603.22586.

## Commands

```bash
pip install -e ".[notebook]"     # dev install + notebook deps (matplotlib, jupyter)
pip install -e ".[training]"     # adds pandas + datasets, REQUIRED to import iAmTime.icl_data_factory
mypy src/iAmTime                 # config in [tool.mypy] (ignore_missing_imports = true)
jupyter lab notebooks/iamtime_forecasting_usage.ipynb
```

`uv.lock` is present and `.venv/` is a uv-managed Python 3.14 env, so `uv sync` / `uv run ...` also work.

There is **no test suite** yet (a `test` extra declares pytest, but no `tests/` directory exists). If you add tests, `pytest tests/test_x.py::test_name` runs a single one.

## Layout and import quirk

`src/iAmTime/` has **no `__init__.py`** — it is an implicit namespace package, declared to hatchling via `[tool.hatch.build.targets.wheel] packages = ["src/iAmTime"]`. Always import submodules explicitly (`from iAmTime.pipeline import iAmTimePipeline`); nothing is re-exported at package level.

## Architecture

Three layers, each with a distinct responsibility:

1. **`pipeline.py` — user-facing I/O normalization.** `iAmTimePipeline` (`from_pretrained`, `predict`, `predict_quantiles`, `predict_classes`, `embed`).
2. **`model.py` — `iAmTimeModel`**, a `PreTrainedModel` whose `config_class` is `T5Config`. Patching, instance norm, encoder/decoder orchestration, quantile loss.
3. **`blocks.py` / `layers.py` — the ICL encoder stack, decoder and primitives.** `blocks.py` also owns the *index arithmetic* that everything else depends on.

`icl_data_factory.py` and `utils_icl.py` are training/batching support and are independent of inference.

### The ICL tensor contract

Every path converges on these seven tensors (plus optional `query_target_future` for loss/eval), which are `iAmTimeModel.forward`'s signature and `pipeline.icl_input_attributes`:

```
example_target_histories (B, E, hist)        example_target_futures (B, E, fut)
example_exog_histories   (B, E, M, hist)     example_exog_futures   (B, E, M, fut)
query_target_history     (B, hist)
query_exog_history       (B, M, hist)        query_exog_future      (B, M, fut)
```

`E` = number of support examples, `M` = number of exogenous series. Each has a parallel `*_mask`; masks left as `None` are derived from `~isnan` in `_check_or_create_mask_for_tensor`. Zero examples (`E=0`) is the plain forecasting case — the ICL machinery is not optional, just empty.

`pipeline._convert_to_icl_inputs` accepts four public input shapes (raw 2-D array / list of 1-D arrays, `{"target", "past_covariates", "future_covariates"}` dicts, and full ICL dicts) and lowers all of them to the dict form above, filling absent keys with `np.array([])`. `GetPaddedBatchInputsForICL` (`utils_icl.py`) then pads a ragged list of per-item dicts into the batched tensors; `right_pad_icl_input_tensors` extends future-side tensors to `prediction_length`. Histories are truncated to the **last** `iamtime_config.context_length` steps.

**Multivariate targets are not native.** `pipeline._expand_multivariate` turns a `(variates, length)` target into `n_variates` univariate items, each with the other variates appended as exogenous covariates, and `_regroup_predictions` folds the results back using `group_sizes`. Any new input format must be handled in both `_convert_to_icl_inputs` and `_expand_multivariate`.

### Slot layouts (blocks.py)

Two pure index functions define the whole encoder geometry; change them and model weights become incompatible.

- `series_indices(E_max)` → `S = 2 + 2*E_max` series slots: `T_hist`, `X_hist[k]`, `T_fut`, `X_fut[k]`.
- `token_slots(E_max)` → `T = 5 + 2*E_max` semantic token slots in order `START, TARGET_HIST, EXOG_HIST[k], MID, TARGET_FUT, FUT_EXOG[k], END`. `start_idx` and `mid_idx` are threaded through the encoder and into the decoder.

`E_max` is `max(num_exog_examples, num_exog_query)` for the batch, so `_pad_exog_exists` pads existence flags to it. Three mask families must stay consistent: patch masks `M_*`, token-validity masks (`build_token_valid_mask`) and token→patch allow masks (`build_allow_patchsplit`).

### Forward pass

`_embed_component` is run four times (example history, example future, query history, query future). Each call: `_pack_context` stacks target + exog into one flat series axis → `InstanceNorm` → `Patch` → `input_patch_embedding` (a `ResidualBlock` over `[time_embedding, patch, patch_mask]`, hence `patch_size * 3` inputs) → reshape back to `(B, E, S, P, d)`.

Crucially, **future components reuse the history's `loc_scale`**, and the query's `query_hist_loc_scale` is what `instance_norm.inverse` uses to unscale predictions and what `_compute_loss` uses to scale targets. The query target future is fed in as zeros with an all-zero mask.

`_build_encoder_inputs` concatenates history+future along the patch axis, builds tokens and the three mask families, and (one subtle line) re-enables attention to the query's future target patches in `M_q`.

`CompositeICLEncoderStack` runs `num_layers` × `CompositeICLEncoderBlock`, each performing six scoped stages in order:

1. temporal self-attention within each series (RoPE enabled);
2. example-fusion attention across examples/series at each patch index (no RoPE);
3. token **read** (semantic tokens cross-attend to patches) then token self-attention within a block;
4. cross-example attention on the query's `[START]`/`[MID]` tokens against the examples';
5. token **write** — FiLM-style modulation of query patches from tokens (`TokenWrite`);
6. separate FFNs for patches and tokens.

Blocks avoid in-place writes into `Tok_*` (scatter/`unsqueeze` instead) so gradient checkpointing (`use_reentrant=False`) stays correct.

`PatchCrossAttentionDecoder` then consumes **only** the query's future target patches `X_q[:, 0, 0, P_h_q:, :]` plus the `[START]` and `[MID]` tokens, cross-attending over learned expert memory (`num_heads = iamtime_config.num_experts`) to emit `(B, num_quantiles, prediction_length)`.

### Prediction length

Resolved in two places with the same priority: `query_exog_future` length → `query_target_future` length → explicit argument → `patch_size * max_output_steps`. Conflicting sources raise `ValueError` (`pipeline._resolve_prediction_length`, `model._resolve_prediction_length`).

### Config

`from_pretrained` loads a `T5Config` and asserts it carries `iamtime_config` and `icl_config` dicts, which become the `iAmTimeConfig` / `ICLConfig` dataclasses in `model.py`. The vocabulary is tiny and structural: `shared_emb` holds only `[PAD]` (+ `[REG]` if `use_reg_token`), while `shared_token_emb` holds the 5–6 semantic ICL tokens (6 when `use_future_exog_token`). Adding a semantic token means changing `ICLConfig`, `icl_vocab_size`, `token_slots` and the mask builders together.

### Classification without a classification checkpoint

`predict_classes` takes **scalar class labels** as `example_target_futures` and encodes them as constant label-code series pre-compensated for per-series `InstanceNorm` (so they pass through unchanged), then maps decoder output back to labels. Reuses the forecasting checkpoint; no separate head.

### Attribution

Several layers (`RoPE`, patching, instance norm) are adapted from Chronos-2 and HuggingFace Llama/T5; source links are in the docstrings — keep them when editing.

## Research workflow

Before any experiment, read research/THEORY.md — it is the authoritative statement of the problem and current results. After every experiment that produces a result, append an entry to research/FINDINGS.md using the template in that file. Never edit THEORY.md; if you believe a theoretical result is wrong, log it in FINDINGS.md as CONTRADICTS with evidence.
