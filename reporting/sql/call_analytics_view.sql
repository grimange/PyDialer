-- Call Analytics View
-- Provides comprehensive call analytics including hourly patterns, 
-- call outcomes, duration analysis, and telephony performance metrics
-- Note: SQLite doesn't support materialized views, so this creates a regular view

DROP VIEW IF EXISTS call_analytics_stats;

CREATE VIEW call_analytics_stats AS
SELECT 
    -- Time-based aggregations
    DATE(cdr.call_date) as call_date,
    CAST(strftime('%H', cdr.start_time) AS INTEGER) as call_hour,
    CAST(strftime('%w', cdr.call_date) AS INTEGER) as day_of_week, -- 0=Sunday, 6=Saturday
    
    -- Campaign Information
    cdr.campaign_id,
    c.name as campaign_name,
    c.dial_method,
    
    -- Agent Information
    cdr.agent_id,
    u.username as agent_username,
    u.first_name as agent_first_name,
    u.last_name as agent_last_name,
    
    -- Call Volume Metrics
    COUNT(*) as total_calls,
    COUNT(CASE WHEN cdr.call_result = 'ANSWERED' THEN 1 END) as answered_calls,
    COUNT(CASE WHEN cdr.call_result = 'COMPLETED' THEN 1 END) as completed_calls,
    COUNT(CASE WHEN cdr.call_result = 'BUSY' THEN 1 END) as busy_calls,
    COUNT(CASE WHEN cdr.call_result = 'NO_ANSWER' THEN 1 END) as no_answer_calls,
    COUNT(CASE WHEN cdr.call_result = 'DROPPED' THEN 1 END) as dropped_calls,
    COUNT(CASE WHEN cdr.call_result = 'ABANDONED' THEN 1 END) as abandoned_calls,
    COUNT(CASE WHEN cdr.call_result = 'FAILED' THEN 1 END) as failed_calls,
    
    -- Duration Analytics
    SUM(COALESCE(EXTRACT(EPOCH FROM cdr.talk_duration), 0)) as total_talk_seconds,
    AVG(COALESCE(EXTRACT(EPOCH FROM cdr.talk_duration), 0)) as avg_talk_seconds,
    MAX(COALESCE(EXTRACT(EPOCH FROM cdr.talk_duration), 0)) as max_talk_seconds,
    MIN(CASE WHEN cdr.talk_duration IS NOT NULL THEN EXTRACT(EPOCH FROM cdr.talk_duration) END) as min_talk_seconds,
    
    SUM(COALESCE(EXTRACT(EPOCH FROM cdr.ring_duration), 0)) as total_ring_seconds,
    AVG(COALESCE(EXTRACT(EPOCH FROM cdr.ring_duration), 0)) as avg_ring_seconds,
    
    SUM(COALESCE(EXTRACT(EPOCH FROM cdr.hold_duration), 0)) as total_hold_seconds,
    AVG(COALESCE(EXTRACT(EPOCH FROM cdr.hold_duration), 0)) as avg_hold_seconds,
    
    SUM(COALESCE(EXTRACT(EPOCH FROM cdr.total_duration), 0)) as total_call_seconds,
    AVG(COALESCE(EXTRACT(EPOCH FROM cdr.total_duration), 0)) as avg_call_seconds,
    
    -- Quality Metrics
    CASE 
        WHEN COUNT(*) > 0 
        THEN ROUND((COUNT(CASE WHEN cdr.call_result = 'ANSWERED' THEN 1 END)::decimal / COUNT(*)) * 100, 2)
        ELSE 0.00
    END as answer_rate,
    
    CASE 
        WHEN COUNT(*) > 0 
        THEN ROUND((COUNT(CASE WHEN cdr.call_result = 'DROPPED' THEN 1 END)::decimal / COUNT(*)) * 100, 2)
        ELSE 0.00
    END as drop_rate,
    
    CASE 
        WHEN COUNT(CASE WHEN cdr.call_result = 'ANSWERED' THEN 1 END) > 0 
        THEN ROUND((COUNT(CASE WHEN cdr.call_result = 'COMPLETED' THEN 1 END)::decimal / COUNT(CASE WHEN cdr.call_result = 'ANSWERED' THEN 1 END)) * 100, 2)
        ELSE 0.00
    END as completion_rate,
    
    -- Cost Analysis
    SUM(COALESCE(cdr.cost, 0.00)) as total_cost,
    AVG(COALESCE(cdr.cost, 0.00)) as avg_cost_per_call,
    
    -- Telephony Performance
    COUNT(CASE WHEN cdr.hangup_cause = 'NORMAL_CLEARING' THEN 1 END) as normal_hangups,
    COUNT(CASE WHEN cdr.hangup_cause = 'USER_BUSY' THEN 1 END) as busy_hangups,
    COUNT(CASE WHEN cdr.hangup_cause = 'NO_ANSWER' THEN 1 END) as no_answer_hangups,
    COUNT(CASE WHEN cdr.hangup_cause = 'CALL_REJECTED' THEN 1 END) as rejected_hangups,
    COUNT(CASE WHEN cdr.hangup_cause NOT IN ('NORMAL_CLEARING', 'USER_BUSY', 'NO_ANSWER', 'CALL_REJECTED') THEN 1 END) as other_hangups,
    
    -- Recording Statistics
    COUNT(CASE WHEN EXISTS (SELECT 1 FROM calls_recording r WHERE r.call_detail_record_id = cdr.id) THEN 1 END) as recorded_calls,
    
    -- Disposition Integration
    COUNT(CASE WHEN EXISTS (
        SELECT 1 FROM leads_disposition d 
        JOIN calls_calltask ct ON d.call_task_id = ct.id 
        WHERE ct.pbx_call_id = cdr.pbx_call_id
    ) THEN 1 END) as dispositioned_calls,
    
    -- Time Analysis
    MIN(cdr.start_time) as first_call_time,
    MAX(cdr.end_time) as last_call_time,
    
    -- Refresh timestamp
    NOW() as refreshed_at
    
FROM calls_calldetailrecord cdr
LEFT JOIN campaigns_campaign c ON cdr.campaign_id = c.id
LEFT JOIN agents_user u ON cdr.agent_id = u.id

WHERE cdr.call_date >= CURRENT_DATE - INTERVAL '90 days' -- Limit to last 90 days for performance

GROUP BY 
    DATE(cdr.call_date),
    EXTRACT(HOUR FROM cdr.start_time),
    EXTRACT(DOW FROM cdr.call_date),
    cdr.campaign_id,
    c.name,
    c.dial_method,
    cdr.agent_id,
    u.username,
    u.first_name,
    u.last_name

ORDER BY call_date DESC, call_hour;

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_call_analytics_date ON call_analytics_stats(call_date);
CREATE INDEX IF NOT EXISTS idx_call_analytics_hour ON call_analytics_stats(call_hour);
CREATE INDEX IF NOT EXISTS idx_call_analytics_dow ON call_analytics_stats(day_of_week);
CREATE INDEX IF NOT EXISTS idx_call_analytics_campaign ON call_analytics_stats(campaign_id);
CREATE INDEX IF NOT EXISTS idx_call_analytics_agent ON call_analytics_stats(agent_id);
CREATE INDEX IF NOT EXISTS idx_call_analytics_refreshed ON call_analytics_stats(refreshed_at);
CREATE INDEX IF NOT EXISTS idx_call_analytics_composite ON call_analytics_stats(call_date, campaign_id, agent_id);
