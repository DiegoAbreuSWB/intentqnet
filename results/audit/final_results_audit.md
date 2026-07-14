# Final results audit (Fase K1)

| Campaign | Expected | Raw rows | Manifest | Audit |
|---|---:|---:|---|---|
| F01_architecture_baselines | 120 | 120 | present | WARN |
| F02_routing | 120 | 120 | present | PASS |
| F03_purification | 480 | 480 | present | WARN |
| F05_reconciliation | 100 | 100 | present | WARN |
| F06_overhead | 60 | 60 | present | WARN |
| F07_estimators | 120 | 120 | present | PASS |
| F08_resource_semantics | 80 | 80 | present | PASS |

## F01_architecture_baselines - WARN

| Check | Status | Detail |
|---|---|---|
| trials_csv_exists | PASS | 120 rows |
| manifest_exists | PASS | F01_architecture_baselines.json |
| manifest_arithmetic | PASS | 120 == 120+0+0 |
| row_count_matches_manifest | PASS | 120 rows == completed_trials |
| key_uniqueness | PASS | 0 duplicates on ['condition', 'seed'] |
| seeds_complete[diamond_heterogeneous] | PASS | 20 seeds present |
| block_row_count[diamond_heterogeneous] | PASS | 120 rows |
| commit_consistency | WARN | no per-row project_git_commit column (ad-hoc script - see docs/results_provenance.md known gap) |

## F02_routing - PASS

| Check | Status | Detail |
|---|---|---|
| trials_csv_exists | PASS | 120 rows |
| manifest_exists | PASS | F02_routing.json |
| manifest_arithmetic | PASS | 120 == 120+0+0 |
| row_count_matches_manifest | PASS | 120 rows == completed_trials |
| key_uniqueness | PASS | 0 duplicates on ['trial_id'] |
| seeds_complete[diamond_heterogeneous] | PASS | 20 seeds present |
| block_row_count[diamond_heterogeneous] | PASS | 60 rows |
| grid_combinations_complete[diamond_heterogeneous] | PASS | 3 combinations x 20 seeds |
| seeds_complete[small_mesh] | PASS | 20 seeds present |
| block_row_count[small_mesh] | PASS | 60 rows |
| grid_combinations_complete[small_mesh] | PASS | 3 combinations x 20 seeds |
| commit_consistency | PASS | single commit: ['f4343c314e5de5e01ee6970aaa14b5974c1b49ea'] |

## F03_purification - WARN

| Check | Status | Detail |
|---|---|---|
| trials_csv_exists | PASS | 480 rows |
| manifest_exists | PASS | F03_purification.json |
| manifest_arithmetic | PASS | 480 == 480+0+0 |
| row_count_matches_manifest | PASS | 480 rows == completed_trials |
| key_uniqueness | PASS | 0 duplicates on ['trial_id'] |
| seeds_complete[linear_chain_2_repeaters] | PASS | 20 seeds present |
| block_row_count[linear_chain_2_repeaters] | PASS | 160 rows |
| grid_combinations_complete[linear_chain_2_repeaters] | PASS | 8 combinations x 20 seeds |
| seeds_complete[three_node_1_repeater] | PASS | 20 seeds present |
| block_row_count[three_node_1_repeater] | PASS | 320 rows |
| grid_combinations_complete[three_node_1_repeater] | PASS | 16 combinations x 20 seeds |
| commit_consistency | WARN | multiple commits (check manifest blocks - may be a legitimately extended campaign): {'f4343c314e5de5e01ee6970aaa14b5974c1b49ea': 320, '346d13d73b314be70c16e143c68a04cb832af4fc': 160} |

## F05_reconciliation - WARN

| Check | Status | Detail |
|---|---|---|
| trials_csv_exists | PASS | 100 rows |
| manifest_exists | PASS | F05_reconciliation.json |
| manifest_arithmetic | PASS | 100 == 100+0+0 |
| row_count_matches_manifest | PASS | 100 rows == completed_trials |
| key_uniqueness | PASS | 0 duplicates on ['case', 'seed'] |
| seeds_complete[route_change_recoverable] | PASS | 20 seeds present |
| block_row_count[route_change_recoverable] | PASS | 20 rows |
| seeds_complete[duration_increase_recoverable] | PASS | 20 seeds present |
| block_row_count[duration_increase_recoverable] | PASS | 20 rows |
| seeds_complete[slot_increase_recoverable] | PASS | 20 seeds present |
| block_row_count[slot_increase_recoverable] | PASS | 20 rows |
| seeds_complete[fidelity_ceiling_unrecoverable] | PASS | 20 seeds present |
| block_row_count[fidelity_ceiling_unrecoverable] | PASS | 20 rows |
| seeds_complete[severe_loss_attempt] | PASS | 20 seeds present |
| block_row_count[severe_loss_attempt] | PASS | 20 rows |
| commit_consistency | WARN | no per-row project_git_commit column (ad-hoc script - see docs/results_provenance.md known gap) |

## F06_overhead - WARN

| Check | Status | Detail |
|---|---|---|
| trials_csv_exists | PASS | 60 rows |
| manifest_exists | PASS | F06_overhead.json |
| manifest_arithmetic | PASS | 60 == 60+0+0 |
| row_count_matches_manifest | PASS | 60 rows == completed_trials |
| key_uniqueness | PASS | 0 duplicates on ['condition', 'seed'] |
| seeds_complete[diamond_heterogeneous] | PASS | 20 seeds present |
| block_row_count[diamond_heterogeneous] | PASS | 60 rows |
| commit_consistency | WARN | no per-row project_git_commit column (ad-hoc script - see docs/results_provenance.md known gap) |

## F07_estimators - PASS

| Check | Status | Detail |
|---|---|---|
| trials_csv_exists | PASS | 120 rows |
| manifest_exists | PASS | F07_estimators.json |
| manifest_arithmetic | PASS | 120 == 120+0+0 |
| row_count_matches_manifest | PASS | 120 rows == completed_trials |
| key_uniqueness | PASS | 0 duplicates on ['trial_id'] |
| seeds_complete[diamond_heterogeneous] | PASS | 20 seeds present |
| block_row_count[diamond_heterogeneous] | PASS | 120 rows |
| grid_combinations_complete[diamond_heterogeneous] | PASS | 6 combinations x 20 seeds |
| commit_consistency | PASS | single commit: ['f4343c314e5de5e01ee6970aaa14b5974c1b49ea'] |

## F08_resource_semantics - PASS

| Check | Status | Detail |
|---|---|---|
| trials_csv_exists | PASS | 80 rows |
| manifest_exists | PASS | F08_resource_semantics.json |
| manifest_arithmetic | PASS | 80 == 80+0+0 |
| row_count_matches_manifest | PASS | 80 rows == completed_trials |
| key_uniqueness | PASS | 0 duplicates on ['trial_id'] |
| seeds_complete[three_node] | PASS | 20 seeds present |
| block_row_count[three_node] | PASS | 80 rows |
| grid_combinations_complete[three_node] | PASS | 4 combinations x 20 seeds |
| commit_consistency | PASS | single commit: ['f4343c314e5de5e01ee6970aaa14b5974c1b49ea'] |

## Cross-campaign checks

| Check | Status | Detail |
|---|---|---|
| f04_derives_from_f02_f03 | PASS | 600 rows == 120 (F02) + 480 (F03), trial_id sets match |
| final_figures_have_sources_json | PASS | 17 entries |
| every_figure_has_pdf_and_png | PASS | 17 figures |
| every_figure_has_identifiable_source | PASS | all figures listed in sources.json |
