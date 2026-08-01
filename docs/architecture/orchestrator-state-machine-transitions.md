# Orchestrator State Machine — Transition Table

Machine-readable specification: `orchestrator-state-machine.yaml`
Schema: `.blitzhub/schemas/orchestrator-state-machine.yaml.schema.json`
Tests: `tests/orchestrator_state_machine_test.py`

## States

| ID              | Name              | Kind              | Kanban Column      |
|-----------------|-------------------|-------------------|--------------------|
| inbox           | Inbox             | operational       | Inbox              |
| backlog         | Backlog           | operational       | Backlog            |
| ready           | Ready             | operational       | Ready              |
| in_progress     | In Progress       | operational       | In Progress        |
| pull_request    | Pull Request      | operational       | Pull Request       |
| supervisory_review | Supervisory Review | operational    | Supervisory Review |
| rework          | Rework            | operational       | Rework             |
| ready_to_merge  | Ready to Merge    | operational       | Ready to Merge     |
| done            | Done              | terminal          | Done               |
| blocked         | Blocked           | interruption      | Blocked            |
| deferred        | Deferred          | interruption      | Deferred           |
| external_review | External Review   | terminal_external | Supervisory Review |

## Events

| ID                       | Name                      | Source                |
|--------------------------|---------------------------|-----------------------|
| ev_issue_opened          | issue_opened              | github                |
| ev_issue_updated         | issue_updated             | github                |
| ev_issue_closed          | issue_closed              | github                |
| ev_issue_commented       | issue_commented           | github                |
| ev_pr_opened             | pr_opened                 | github                |
| ev_pr_updated            | pr_updated                | github                |
| ev_pr_checks_completed   | pr_checks_completed       | github                |
| ev_pr_merged             | pr_merged                 | github                |
| ev_pr_closed             | pr_closed                 | github                |
| ev_review_submitted      | review_submitted          | github                |
| ev_supervisory_round     | supervisory_round_completed | supervisory         |
| ev_dependency_resolved   | dependency_resolved       | internal              |
| ev_agent_assigned        | agent_assigned            | agent_runtime         |
| ev_reconciliation_started| reconciliation_cycle_started | internal           |

## Transitions

| ID | From            | To                | On                        | Guards                                              | Actions                                           | Priority |
|----|-----------------|-------------------|---------------------------|-----------------------------------------------------|---------------------------------------------------|----------|
| t01| inbox           | backlog           | ev_issue_opened           | g_no_generic_soul, g_is_internal_agent            | act_create_card                                   |          |
| t02| backlog         | ready             | ev_reconciliation_started | g_definition_of_ready_met, g_agent_active, g_agent_healthy, g_agent_assignable, g_soul_hash_match, g_no_generic_soul, g_dependencies_resolved, g_wip_in_progress_ok | act_move_card                |          |
| t03| ready           | in_progress       | ev_agent_assigned         | g_agent_active, g_agent_healthy, g_agent_assignable, g_soul_hash_match, g_no_generic_soul, g_dependencies_resolved, g_wip_in_progress_ok | act_assign_agent, act_move_card |          |
| t04| in_progress     | pull_request      | ev_pr_opened              | g_pull_request_open                                 | act_move_card                                     |          |
| t05| pull_request    | supervisory_review| ev_pr_checks_completed   | g_required_checks_complete, g_no_failed_mandatory_checks | act_move_card                      |          |
| t06| supervisory_review | ready_to_merge  | ev_supervisory_round      | g_no_required_findings, g_definition_of_done_met, g_no_failed_mandatory_checks | act_move_card     |          |
| t07| ready_to_merge  | done              | ev_pr_merged              | g_definition_of_done_met                            | act_move_card, act_close_issue                    |          |
| t08| supervisory_review | rework          | ev_supervisory_round      | g_has_required_findings                             | act_prioritise_required_findings, act_move_card  | high     |
| t09| pull_request    | rework            | ev_pr_checks_completed     | g_has_failed_checks                                 | act_move_card                                     | high     |
| t10| rework          | supervisory_review| ev_pr_updated              | g_required_checks_complete, g_no_required_findings, g_definition_of_done_met | act_move_card |          |
| t11| backlog         | blocked           | ev_reconciliation_started | (none)                                              | act_block_item                                    |          |
| t12| ready           | blocked           | ev_reconciliation_started | (none)                                              | act_block_item                                    |          |
| t13| in_progress     | blocked           | ev_reconciliation_started | (none)                                              | act_block_item                                    |          |
| t14| blocked         | backlog           | ev_dependency_resolved     | g_dependencies_resolved, g_definition_of_ready_met  | act_move_card                                     |          |
| t15| any             | deferred          | ev_reconciliation_started | g_is_explicitly_deferred                            | act_defer_item                                    |          |
| t16| deferred        | backlog           | ev_reconciliation_started | g_definition_of_ready_met, g_dependencies_resolved  | act_move_card                                     |          |
| t17| inbox           | external_review   | ev_issue_opened           | g_no_generic_soul, g_is_external_role               | act_create_card                                   |          |
| t18| any             | blocked           | ev_reconciliation_started | g_exceeds_retry_threshold                           | act_dead_letter                                   |          |
| t19| backlog         | ready             | ev_dependency_resolved     | g_definition_of_ready_met, g_dependencies_resolved, g_agent_active, g_agent_healthy, g_agent_assignable | act_move_card |          |
| t20| ready           | blocked           | ev_reconciliation_started | g_agent_wave_inactive                               | act_block_item                                    |          |

## Scenario coverage

| Scenario        | Transitions |
|-----------------|-------------|
| Normal flow     | t01, t02, t03, t04, t05, t06, t07 |
| Rework          | t08, t09, t10 |
| Block           | t11, t12, t13 |
| Recovery        | t14 |
| Defer           | t15, t16 |
| External review | t17 |
| Dead-letter     | t18 |
| Dependency gate | t19, g_dependency_issue_3_satisfied |
| Wave gate       | t20, g_agent_wave_inactive |
