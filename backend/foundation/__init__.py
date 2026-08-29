"""M0 基座与数据治理（foundation）。

共享数据基座：workflow_jobs/tasks/logs/app_config/error_codes 五表 +
任务队列 WorkflowQueue（enqueue/claim/complete/fail/租约/幂等/失败隔离）+
调度器 WorkflowScheduler（进程化：断点自愈/节流/熔断）。
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
]
