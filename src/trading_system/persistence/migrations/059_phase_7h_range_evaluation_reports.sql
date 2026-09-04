CREATE TABLE IF NOT EXISTS range_evaluation_reports (
    report_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES range_experiment_plans(plan_id),
    assignment_root TEXT NOT NULL,
    summary_root TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE (plan_id, assignment_root, summary_root)
);

CREATE INDEX IF NOT EXISTS idx_range_evaluation_reports_plan
ON range_evaluation_reports(plan_id, report_id);
