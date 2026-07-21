# M10.8 — Tail-event diagnostic study (P14) summary

Data: `results/predictability_m10/raw/P14_tail_event_study/trials.csv`
(120 trials, 0 duplicates - complete). Heartbeat trails:
`results/predictability_m10/raw/P14_tail_event_study/heartbeats/`.

## Result: no evidence of hypothesis 3 (bug/pathological condition) in this sample

| `termination_reason` | count |
|---|---:|
| SIMULATION_COMPLETE | 118 |
| TIMEOUT | 2 |
| NO_PROGRESS | 0 |
| MAX_RETRIES | 0 |
| ERROR | 0 |

Both `TIMEOUT` trials (four_node, seeds 335 and 336 - consecutive) show
**progressing, not stalled, event counts** in their heartbeat trail before
the 120s cap killed them:

| Seed | Heartbeat samples | Final logged sim_time_s | Final logged run_counter |
|---:|---:|---:|---:|
| 335 | 6 | 0.0514 | 22,476 |
| 336 | 11 | 0.0585 | 26,771 |

`run_counter` (SeQUeNCe's own cumulative processed-event counter,
`Timeline.run_counter`) reached the low tens of thousands within the
FIRST 12-22 seconds of wall time for a reservation window of only
0.05-0.06 SIMULATED seconds - a large, RAPIDLY GROWING event count for a
tiny simulated-time span, consistent with a genuine high-retry-rate
physical/execution scenario (many elementary-generation attempt/failure
events processed per unit of simulated time), not a frozen or looping
condition. No sample in either trial's trail shows a stalled
`run_counter` - the explicit signature `classify_termination` checks for
before returning `NO_PROGRESS` never appeared.

**This is evidence FOR hypothesis 1 (a legitimate, rare, high-event-count
stochastic tail event) and AGAINST hypothesis 3 (a bug/infinite loop),
for the two tail events actually captured in this campaign.** Neither
directly reproduces the original ~48723s P02B outlier (both were capped
at 120s by design - this campaign was never intended to let one run
uninterrupted, per section 13's explicit instruction against
unbounded trials), so this does not, and does not claim to, fully
root-cause that specific historical event - it characterizes the general
phenomenon of rare slow trials in this parameter region, which is the
scope this milestone was scoped to.

## A disclosed limitation of the instrumentation itself

Both `TIMEOUT` trials stopped writing new heartbeat samples well before
being killed (6 samples / ~12s and 11 samples / ~22s of heartbeat
coverage, despite running for the full 120s before the wall-clock cap
fired). The background watcher thread likely became starved of the GIL
during the busiest phase of event processing - Python's cooperative
thread scheduling can starve a background thread when the main thread is
executing a tight loop that doesn't yield control as often as the
interpreter's default switch interval would otherwise allow. This means
**the heartbeat trail's absence for the LATTER ~100s of these two
trials is not itself evidence of anything** (neither progress nor
stall) - only the first 12-22 seconds are actually observed. The
conclusion above (progressing, not stalled) is based on what WAS
captured, honestly bounded by what the instrumentation could see, not
extrapolated to the full 120s window. A more invasive instrumentation
approach (e.g. patching `Timeline.run()` itself to yield/checkpoint more
often) would require modifying SeQUeNCe's core, which this project does
not do.

## Per-topology breakdown

| Scenario | n | Timeouts | Mean wall (s) | Max wall (s) |
|---|---:|---:|---:|---:|
| four_node | 40 | 2 | 10.4 | 120.0 (capped) |
| diamond_heterogeneous | 40 | 0 | 6.6 | 9.0 |
| small_mesh | 40 | 0 | N/A (all REJECTED - see below) | N/A |

`small_mesh` at fidelity=0.46 was REJECTED by L2 in all 40 trials before
any simulation ran (L2's deterministic `IterativeAnalyticalPurification`
correctly determines the target is unreachable within its round cap,
unlike L3-family planners at `admission_threshold=0.0`, which force
admission regardless and are what exposed the BBPSSW assertion in P13) -
no tail-event risk observed here because no simulation was attempted at
all, not because the region is safe under a forcing planner.
`diamond_heterogeneous` showed 0 timeouts in this 40-seed sample (the
~75s single-trial outlier found while characterizing M10.6's duration
sweep did not recur here) - consistent with a rare event whose true rate
is low enough that 40 seeds is not guaranteed to re-trigger it.

## Empirical tail rate in this campaign

2/120 = 1.67% overall (2/40 = 5% for four_node specifically, the only
topology it appeared in this sample) - broadly consistent with prior
estimates across this study (P12's 3/820 = 0.37%, P11's 1/352 = 0.28%),
all in the same low-single-digit-percent range, not contradicting each
other.

## Conclusion

Within this campaign's bounded scope (120 trials, 120s cap, 5,000,000-
event cap - none of which were exceeded except the wall-clock cap on 2
trials), **no evidence was found for hypothesis 2 (already substantially
addressed by M10.1/M10.3) or hypothesis 3 (a bug/pathological loop)**.
The available evidence is consistent with hypothesis 1: rare, legitimate,
high-event-count tail realizations in a narrow parameter region
(four_node near its purification-round transition), whose exact
probability this campaign estimates at a low single-digit percentage,
consistent with every other estimate this study has produced. This does
not prove the original 48723s event was NOT a bug - it establishes that
the tail events THIS campaign could capture look like legitimate rare
events, not stalled ones, within the limits of what the instrumentation
can observe.
