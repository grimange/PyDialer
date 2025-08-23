-- Campaign Performance Statistics Materialized View
-- Aggregates key performance metrics for campaigns including call statistics,
-- conversion rates, agent utilization, and overall campaign effectiveness

DROP MATERIALIZED VIEW IF EXISTS campaign_performance_stats;

CREATE MATERIALIZED VIEW campaign_performance_stats AS
SELECT 
    c.id as campaign_id,
    c.name as campaign_name,
    c.description,
    c.status,
    c.dial_method,
    c.pacing_ratio,
    c.drop_sla_threshold,
    c.max_attempts,
    c.is_active,
    c.created_at,
    c.start_date,
    c.end_date,
    
    -- Current Campaign Statistics
    cs.total_attempts,
    cs.total_contacts,
    cs.total_sales,
    cs.total_leads_loaded,
    cs.leads_remaining,
    cs.avg_call_duration,
    cs.drop_rate_today,
    cs.contact_rate_today,
    cs.last_call_time,
    
    -- Daily Call Statistics (from CDR)
    COALESCE(daily_stats.calls_today, 0) as calls_today,
    COALESCE(daily_stats.answered_calls_today, 0) as answered_calls_today,
    COALESCE(daily_stats.completed_calls_today, 0) as completed_calls_today,
    COALESCE(daily_stats.total_talk_time_today, INTERVAL '0') as total_talk_time_today,
    COALESCE(daily_stats.avg_talk_time_today, INTERVAL '0') as avg_talk_time_today,
    COALESCE(daily_stats.dropped_calls_today, 0) as dropped_calls_today,
    
    -- Weekly Call Statistics
    COALESCE(weekly_stats.calls_week, 0) as calls_week,
    COALESCE(weekly_stats.answered_calls_week, 0) as answered_calls_week,
    COALESCE(weekly_stats.total_talk_time_week, INTERVAL '0') as total_talk_time_week,
    
    -- Monthly Call Statistics
    COALESCE(monthly_stats.calls_month, 0) as calls_month,
    COALESCE(monthly_stats.answered_calls_month, 0) as answered_calls_month,
    COALESCE(monthly_stats.total_talk_time_month, INTERVAL '0') as total_talk_time_month,
    
    -- Lead Statistics
    COALESCE(lead_stats.total_leads, 0) as total_leads,
    COALESCE(lead_stats.fresh_leads, 0) as fresh_leads,
    COALESCE(lead_stats.callback_leads, 0) as callback_leads,
    COALESCE(lead_stats.dnc_leads, 0) as dnc_leads,
    COALESCE(lead_stats.max_attempts_reached, 0) as max_attempts_reached,
    
    -- Disposition Statistics (Daily)
    COALESCE(disp_stats.total_dispositions_today, 0) as total_dispositions_today,
    COALESCE(disp_stats.sales_today, 0) as sales_today,
    COALESCE(disp_stats.callbacks_scheduled_today, 0) as callbacks_scheduled_today,
    COALESCE(disp_stats.total_sale_amount_today, 0.00) as total_sale_amount_today,
    
    -- Agent Assignment Statistics
    COALESCE(agent_stats.assigned_agents, 0) as assigned_agents,
    COALESCE(agent_stats.active_agents_today, 0) as active_agents_today,
    
    -- Performance Metrics
    CASE 
        WHEN daily_stats.calls_today > 0 
        THEN ROUND((daily_stats.answered_calls_today::decimal / daily_stats.calls_today) * 100, 2)
        ELSE 0.00
    END as contact_rate_today_calc,
    
    CASE 
        WHEN daily_stats.answered_calls_today > 0 
        THEN ROUND((disp_stats.sales_today::decimal / daily_stats.answered_calls_today) * 100, 2)
        ELSE 0.00
    END as conversion_rate_today,
    
    CASE 
        WHEN daily_stats.calls_today > 0 
        THEN ROUND((daily_stats.dropped_calls_today::decimal / daily_stats.calls_today) * 100, 2)
        ELSE 0.00
    END as drop_rate_today_calc,
    
    CASE 
        WHEN lead_stats.total_leads > 0 
        THEN ROUND(((lead_stats.total_leads - COALESCE(cs.leads_remaining, lead_stats.total_leads))::decimal / lead_stats.total_leads) * 100, 2)
        ELSE 0.00
    END as completion_percentage,
    
    -- Efficiency Metrics
    CASE 
        WHEN agent_stats.assigned_agents > 0 AND daily_stats.calls_today > 0
        THEN ROUND(daily_stats.calls_today::decimal / agent_stats.assigned_agents, 2)
        ELSE 0.00
    END as calls_per_agent_today,
    
    CASE 
        WHEN disp_stats.sales_today > 0 AND agent_stats.active_agents_today > 0
        THEN ROUND(disp_stats.sales_today::decimal / agent_stats.active_agents_today, 2)
        ELSE 0.00
    END as sales_per_agent_today,
    
    -- Refresh timestamp
    NOW() as refreshed_at
    
FROM campaigns_campaign c
LEFT JOIN campaigns_campaignstatistics cs ON c.id = cs.campaign_id

-- Daily Statistics Subquery
LEFT JOIN (
    SELECT 
        campaign_id,
        COUNT(*) as calls_today,
        COUNT(CASE WHEN answer_time IS NOT NULL THEN 1 END) as answered_calls_today,
        COUNT(CASE WHEN call_result IN ('ANSWERED', 'COMPLETED') THEN 1 END) as completed_calls_today,
        COUNT(CASE WHEN call_result = 'DROPPED' OR call_result = 'ABANDONED' THEN 1 END) as dropped_calls_today,
        SUM(COALESCE(talk_duration, INTERVAL '0')) as total_talk_time_today,
        AVG(talk_duration) as avg_talk_time_today
    FROM calls_calldetailrecord
    WHERE call_date = CURRENT_DATE
        AND campaign_id IS NOT NULL
    GROUP BY campaign_id
) daily_stats ON c.id = daily_stats.campaign_id

-- Weekly Statistics Subquery
LEFT JOIN (
    SELECT 
        campaign_id,
        COUNT(*) as calls_week,
        COUNT(CASE WHEN answer_time IS NOT NULL THEN 1 END) as answered_calls_week,
        SUM(COALESCE(talk_duration, INTERVAL '0')) as total_talk_time_week
    FROM calls_calldetailrecord
    WHERE call_date >= CURRENT_DATE - INTERVAL '7 days'
        AND campaign_id IS NOT NULL
    GROUP BY campaign_id
) weekly_stats ON c.id = weekly_stats.campaign_id

-- Monthly Statistics Subquery
LEFT JOIN (
    SELECT 
        campaign_id,
        COUNT(*) as calls_month,
        COUNT(CASE WHEN answer_time IS NOT NULL THEN 1 END) as answered_calls_month,
        SUM(COALESCE(talk_duration, INTERVAL '0')) as total_talk_time_month
    FROM calls_calldetailrecord
    WHERE call_date >= DATE_TRUNC('month', CURRENT_DATE)
        AND campaign_id IS NOT NULL
    GROUP BY campaign_id
) monthly_stats ON c.id = monthly_stats.campaign_id

-- Lead Statistics Subquery
LEFT JOIN (
    SELECT 
        campaign_id,
        COUNT(*) as total_leads,
        COUNT(CASE WHEN status = 'NEW' AND call_attempts = 0 THEN 1 END) as fresh_leads,
        COUNT(CASE WHEN status = 'CALLBACK' THEN 1 END) as callback_leads,
        COUNT(CASE WHEN status = 'DNC' THEN 1 END) as dnc_leads,
        COUNT(CASE WHEN call_attempts >= c.max_attempts THEN 1 END) as max_attempts_reached
    FROM leads_lead l
    JOIN campaigns_campaign c ON l.campaign_id = c.id
    GROUP BY campaign_id
) lead_stats ON c.id = lead_stats.campaign_id

-- Daily Disposition Statistics Subquery
LEFT JOIN (
    SELECT 
        l.campaign_id,
        COUNT(d.id) as total_dispositions_today,
        COUNT(CASE WHEN dc.is_sale = true THEN 1 END) as sales_today,
        COUNT(CASE WHEN dc.requires_callback = true THEN 1 END) as callbacks_scheduled_today,
        SUM(CASE WHEN dc.is_sale = true THEN COALESCE(d.sale_amount, 0) ELSE 0 END) as total_sale_amount_today
    FROM leads_disposition d
    JOIN leads_dispositioncode dc ON d.disposition_code_id = dc.id
    JOIN leads_lead l ON d.lead_id = l.id
    WHERE DATE(d.created_at) = CURRENT_DATE
    GROUP BY l.campaign_id
) disp_stats ON c.id = disp_stats.campaign_id

-- Agent Assignment Statistics Subquery
LEFT JOIN (
    SELECT 
        ca.campaign_id,
        COUNT(ca.agent_id) as assigned_agents,
        COUNT(CASE 
            WHEN EXISTS (
                SELECT 1 FROM calls_calldetailrecord cdr 
                WHERE cdr.agent_id = ca.agent_id 
                AND cdr.campaign_id = ca.campaign_id 
                AND cdr.call_date = CURRENT_DATE
            ) THEN 1 
        END) as active_agents_today
    FROM campaigns_campaignagentassignment ca
    WHERE ca.is_active = true
    GROUP BY ca.campaign_id
) agent_stats ON c.id = agent_stats.campaign_id

WHERE c.is_active = true OR c.status != 'ARCHIVED'
ORDER BY c.name;

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_campaign_perf_campaign_id ON campaign_performance_stats(campaign_id);
CREATE INDEX IF NOT EXISTS idx_campaign_perf_status ON campaign_performance_stats(status);
CREATE INDEX IF NOT EXISTS idx_campaign_perf_method ON campaign_performance_stats(dial_method);
CREATE INDEX IF NOT EXISTS idx_campaign_perf_active ON campaign_performance_stats(is_active);
CREATE INDEX IF NOT EXISTS idx_campaign_perf_refreshed ON campaign_performance_stats(refreshed_at);
