-- Agent Performance Statistics Materialized View
-- Aggregates key performance metrics for agents including call statistics,
-- talk time, conversion rates, and productivity KPIs

DROP MATERIALIZED VIEW IF EXISTS agent_performance_stats;

CREATE MATERIALIZED VIEW agent_performance_stats AS
SELECT 
    u.id as agent_id,
    u.username,
    u.first_name,
    u.last_name,
    u.email,
    u.employee_id,
    u.department_id,
    u.team_id,
    d.name as department_name,
    t.name as team_name,
    ur.name as role_name,
    
    -- Current Status Information
    ast.status as current_status,
    ast.login_time,
    ast.total_login_duration,
    ast.calls_handled_today,
    ast.average_call_duration,
    
    -- Daily Call Statistics (from CDR)
    COALESCE(daily_stats.total_calls, 0) as total_calls_today,
    COALESCE(daily_stats.answered_calls, 0) as answered_calls_today,
    COALESCE(daily_stats.completed_calls, 0) as completed_calls_today,
    COALESCE(daily_stats.total_talk_time, INTERVAL '0') as total_talk_time_today,
    COALESCE(daily_stats.average_talk_time, INTERVAL '0') as avg_talk_time_today,
    COALESCE(daily_stats.total_hold_time, INTERVAL '0') as total_hold_time_today,
    
    -- Weekly Call Statistics
    COALESCE(weekly_stats.total_calls, 0) as total_calls_week,
    COALESCE(weekly_stats.answered_calls, 0) as answered_calls_week,
    COALESCE(weekly_stats.total_talk_time, INTERVAL '0') as total_talk_time_week,
    
    -- Monthly Call Statistics
    COALESCE(monthly_stats.total_calls, 0) as total_calls_month,
    COALESCE(monthly_stats.answered_calls, 0) as answered_calls_month,
    COALESCE(monthly_stats.total_talk_time, INTERVAL '0') as total_talk_time_month,
    
    -- Disposition Statistics (Daily)
    COALESCE(disp_stats.total_dispositions, 0) as total_dispositions_today,
    COALESCE(disp_stats.sales_made, 0) as sales_made_today,
    COALESCE(disp_stats.callbacks_scheduled, 0) as callbacks_scheduled_today,
    COALESCE(disp_stats.total_sale_amount, 0.00) as total_sale_amount_today,
    
    -- Performance Metrics
    CASE 
        WHEN daily_stats.total_calls > 0 
        THEN ROUND((daily_stats.answered_calls::decimal / daily_stats.total_calls) * 100, 2)
        ELSE 0.00
    END as contact_rate_today,
    
    CASE 
        WHEN daily_stats.answered_calls > 0 
        THEN ROUND((disp_stats.sales_made::decimal / daily_stats.answered_calls) * 100, 2)
        ELSE 0.00
    END as conversion_rate_today,
    
    CASE 
        WHEN ast.total_login_duration IS NOT NULL AND ast.total_login_duration > INTERVAL '0'
        THEN ROUND(
            (EXTRACT(EPOCH FROM daily_stats.total_talk_time)::decimal / 
             EXTRACT(EPOCH FROM ast.total_login_duration)) * 100, 2
        )
        ELSE 0.00
    END as utilization_rate_today,
    
    -- Last Activity Timestamps
    daily_stats.last_call_time,
    disp_stats.last_disposition_time,
    
    -- Refresh timestamp
    NOW() as refreshed_at
    
FROM users u
LEFT JOIN agent_status ast ON u.id = ast.agent_id
LEFT JOIN departments d ON u.department_id = d.id
LEFT JOIN teams t ON u.team_id = t.id
LEFT JOIN user_roles ur ON u.role_id = ur.id

-- Daily Statistics Subquery
LEFT JOIN (
    SELECT 
        agent_id,
        COUNT(*) as total_calls,
        COUNT(CASE WHEN answer_time IS NOT NULL THEN 1 END) as answered_calls,
        COUNT(CASE WHEN call_result IN ('ANSWERED', 'COMPLETED') THEN 1 END) as completed_calls,
        SUM(COALESCE(talk_duration, INTERVAL '0')) as total_talk_time,
        AVG(talk_duration) as average_talk_time,
        SUM(COALESCE(hold_duration, INTERVAL '0')) as total_hold_time,
        MAX(end_time) as last_call_time
    FROM call_detail_records
    WHERE call_date = CURRENT_DATE
        AND agent_id IS NOT NULL
    GROUP BY agent_id
) daily_stats ON u.id = daily_stats.agent_id

-- Weekly Statistics Subquery
LEFT JOIN (
    SELECT 
        agent_id,
        COUNT(*) as total_calls,
        COUNT(CASE WHEN answer_time IS NOT NULL THEN 1 END) as answered_calls,
        SUM(COALESCE(talk_duration, INTERVAL '0')) as total_talk_time
    FROM call_detail_records
    WHERE call_date >= CURRENT_DATE - INTERVAL '7 days'
        AND agent_id IS NOT NULL
    GROUP BY agent_id
) weekly_stats ON u.id = weekly_stats.agent_id

-- Monthly Statistics Subquery
LEFT JOIN (
    SELECT 
        agent_id,
        COUNT(*) as total_calls,
        COUNT(CASE WHEN answer_time IS NOT NULL THEN 1 END) as answered_calls,
        SUM(COALESCE(talk_duration, INTERVAL '0')) as total_talk_time
    FROM call_detail_records
    WHERE call_date >= DATE_TRUNC('month', CURRENT_DATE)
        AND agent_id IS NOT NULL
    GROUP BY agent_id
) monthly_stats ON u.id = monthly_stats.agent_id

-- Daily Disposition Statistics Subquery
LEFT JOIN (
    SELECT 
        agent_id,
        COUNT(*) as total_dispositions,
        COUNT(CASE WHEN dc.is_sale = true THEN 1 END) as sales_made,
        COUNT(CASE WHEN dc.requires_callback = true THEN 1 END) as callbacks_scheduled,
        SUM(CASE WHEN dc.is_sale = true THEN COALESCE(d.sale_amount, 0) ELSE 0 END) as total_sale_amount,
        MAX(d.created_at) as last_disposition_time
    FROM dispositions d
    JOIN disposition_codes dc ON d.disposition_code_id = dc.id
    WHERE DATE(d.created_at) = CURRENT_DATE
    GROUP BY agent_id
) disp_stats ON u.id = disp_stats.agent_id

WHERE ur.name IN ('agent', 'supervisor', 'manager')
ORDER BY u.last_name, u.first_name;

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_agent_perf_agent_id ON agent_performance_stats(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_perf_department ON agent_performance_stats(department_id);
CREATE INDEX IF NOT EXISTS idx_agent_perf_team ON agent_performance_stats(team_id);
CREATE INDEX IF NOT EXISTS idx_agent_perf_status ON agent_performance_stats(current_status);
CREATE INDEX IF NOT EXISTS idx_agent_perf_refreshed ON agent_performance_stats(refreshed_at);
