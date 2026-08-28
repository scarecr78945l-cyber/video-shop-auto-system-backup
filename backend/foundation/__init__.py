"""M0 基座与数据治理（foundation）。

共享数据基座：workflow_jobs/tasks/logs/app_config/error_codes 五表 +
任务队列 WorkflowQueue（enqueue/claim/complete/fail/租约/幂等/失败隔离）。
详见 _management/modules/m0-foundation/。
"""

__all__ = [
    "FoundationConfig",
    "Database",
    "WorkflowQueue",
    "WorkflowJob",
    "Task",
    "LogEntry",
    "AppConfigRow",
    "ErrorCode",
]
