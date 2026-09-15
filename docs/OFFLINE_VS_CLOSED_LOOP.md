# The 0.0077 rad policy that succeeds once in 240 tries

This is the finding that justifies the existence of this repository.

## The two numbers

The behaviour-cloning policy trained by
[`teleop-pipeline`](https://github.com/abyyworld/teleop-pipeline) was
evaluated twice: once offline on held-out demonstrations, once closed-loop here.

**Offline** (`teleop-pipeline eval`, 55 held-out episodes across 10 held-out
sessions, 8,054 windows):

| Metric | Value |
| --- | ---: |
| action MAE | 0.00773 rad (95% CI [0.00699, 0.00841]) |
| action RMSE | 0.03364 rad |
| gripper accuracy | 98.0% |
| rollout drift @1 step | 0.0046 |

An action error under a hundredth of a radian and 98% gripper agreement. Nothing
in that table says "this policy does not work".

The table is also missing the row that does. `teleop-pipeline` computes three
baselines on every evaluation, and the strongest of them here is persistence,
which repeats the previous action:

| Predictor | 1-step MAE | 8-step chunk MAE |
| --- | ---: | ---: |
| zero | 0.07255 | 0.07261 |
| train-set mean | 0.06668 | 0.06670 |
| **persistence** | **0.00362** | **0.01255** |
| the policy | 0.00773 | 0.01582 |

The policy is 113% worse than persistence at one step and 26% worse over the
chunk, and it is behind at all eight offsets. Against `zero` the same policy
looks like an 89% error reduction at one step and 78% over the chunk, which is
the number that goes on a slide.
Only one of those two comparisons carries information, and the flattering one
is the one that survives being quoted without its baseline.

That is a separate failure from the one below, and it is the cheaper of the
two to catch: it needs no simulator, only the discipline of printing a
reference number next to the headline.

**Closed-loop** (`policy-evals run`, 240 episodes across 4 tasks):

| Task | Successes | Rate |
| --- | ---: | ---: |
| `reach_near` | 0 / 60 | 0.0% |
| `reach_far` | 1 / 60 | 1.7% |
| `reach_precise` | 0 / 60 | 0.0% |
| `grasp_at_target` | 0 / 60 | 0.0% |
| **Overall** | **1 / 240** | **0.4%** (95% CI [0.0%, 1.3%]) |

One success in 240 episodes, and that one is an accident worth naming rather
than rounding away: `reach_far` at seed 4807 ended 4.8 cm from the target
against a 5 cm threshold, with the arm having wandered there rather than gone
there. Reported as 0.4% and not 0% because 0% is a stronger claim than n=240
supports, and because on another machine that episode may fall the other way.
Same checkpoint, same robot description, same units.

## Why

The policy's observation is:

```
q_0..q_6, dq_0..dq_6, ee_x, ee_y, ee_z, ee_qx..ee_qw, grip,
prev_act_q_0..prev_act_q_6, prev_act_grip
```

There is no goal channel. The policy was trained to imitate teleoperation
trajectories, and those trajectories never carried a representation of *where
the operator was trying to go* — the goal lived in the operator's head. So the
policy learned the marginal distribution of plausible next actions given the
arm's current state, which is genuinely what the offline metric measures, and
which is genuinely useful for predicting the next action.

It cannot reach a specified target, because it was never told there was one.

The offline metric is not wrong. It is answering a different question:

- **Offline action error** asks *"given this state, would a demonstrator have
  moved like this?"* Averaged over states drawn from demonstrations.
- **Closed-loop success** asks *"starting here, does this policy accomplish the
  task?"* Over states the policy itself drives into.

A goal-blind policy scores well on the first and essentially nothing on the
second, and no amount of staring at the first will reveal the second.

## Why this is not a straw man

The failure is stark here because the benchmark is goal-conditioned and the
policy is not. On real data the same gap appears in subtler and more dangerous
forms:

- **Compounding error.** Offline metrics evaluate at states drawn from
  demonstrations. A policy runs at states it produced itself, which drift from
  that distribution — the classic covariate shift argument for DAgger. Offline
  error is measured exactly where the policy is strongest.
- **Causal confusion.** A policy fed its own previous action can learn to copy
  it and ignore the state entirely. Offline this looks near-perfect; on hardware
  it drifts. This one is not hypothetical here: `teleop-pipeline` feeds
  `prev_act_*` in, and the policy losing to persistence at every offset is what
  that failure looks like from the outside. Its own `docs/BASELINES.md` records
  the trade-off and the configuration that scored worse still.
- **Multimodality.** When demonstrators solved a task two ways, the
  error-minimising prediction is the average of the two — which is often a
  trajectory that hits the obstacle between them. Low error, guaranteed failure.

In each case the offline number is fine and the robot does not work.

## What to do with this

Nothing here says the pipeline is broken. It says the evaluation was
incomplete, which was true and is now visible. Concretely:

1. **Goal-condition the policy.** Add a target channel to the observation and
   collect demonstrations labelled with what the operator was reaching for.
   That is a data-collection change, not a modelling one, and it is much cheaper
   to discover now than after the demonstrations are collected.
2. **Never quote an offline error without its baseline.** The policy's 0.0077
   rad is meaningless until persistence's 0.0036 rad is next to it. This costs
   nothing, needs no simulator, and would have caught the weaker half of this
   finding before any of the above was built.
3. **Keep both metrics.** Offline error is a fast regression signal — it catches
   a broken checkpoint or a normalisation mismatch in seconds. It is a smoke
   test, not a result.
4. **Gate promotions on closed-loop numbers only.** `policy-evals gate` compares
   against the production checkpoint on identical seeds and refuses to pass a
   regression, or an underpowered comparison that cannot tell.

## Reproducing

```bash
# in teleop-pipeline: synthetic sessions, fixed seeds, no data needed
pip install -e ".[train]"
dvc repro                       # or run the stages directly:
                                #   cli synth --sessions 48 --seed 0
                                #   cli ingest && cli validate --no-quarantine
                                #   cli score && cli dataset && cli train
                                #   cli eval --split val
cat reports/eval_val_metrics.json

# in vla-evals
policy-evals registry add ../teleop-pipeline/artifacts/policy.pt --name bc-teleop-v1
policy-evals run <checkpoint-id>
```

The numbers above were last reproduced on 15 September 2026 from a clean clone
on CPU, torch 2.14.0, in under a minute of training. The closed-loop run is
deterministic: two consecutive runs produced byte-identical results. The offline
figures move in the fourth decimal place across torch versions, which is why the
action MAE carries an interval and why the closed-loop figure is quoted as
1 / 240 rather than as a percentage alone.

## The honest caveat

The environment here is kinematic, not physical — no contacts, no dynamics. A
0% here is not a claim about hardware. But the *mechanism* is not an artefact of
the simulator: a policy with no goal input cannot reach a specified goal in any
environment, and that is exactly the class of thing the offline metric could
never have told you.
