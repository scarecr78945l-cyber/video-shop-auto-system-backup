"""M0 基座与数据治理（foundation）。

共享数据基座：workflow_jobs/tasks/logs/app_config/error_codes 五表 +
任务队列 WorkflowQueue（enqueue/claim/complete/fail/租约/幂等/失败隔离）+
调度器 WorkflowScheduler（进程化：断点自愈/节流/熔断）+
风控规则引擎 RiskEngine（S7 预算三重/S1·S3 自动止损/S5 余额/S8 一键全停，与 M5 同口径）。
详见 _management/modules/m0-foundation/。
"""

__all__ = [
    "FoundationConfig",
    "SchedulerConfig",
    "Database",
    "WorkflowQueue",
    "WorkflowScheduler",
    "Worker",
    "LoggingWorker",
    "default_worker_id",
    "WorkflowJob",
    "Task",
    "LogEntry",
    "AppConfigRow",
    "ErrorCode",
    "STAGE_VALUES",
    "JOB_STATUSES",
    "RiskEngine",
    "check_budget_triple",
    "kill_switch_enabled",
    "rule_s1_stop_loss",
    "rule_s3_roi_floor",
    "rule_s5_balance",
    "normalize_diagnosis",
    "RuleVerdict",
    "BudgetVerdict",
    "EngineResult",
]
