import React, { useState, useEffect } from 'react'
import { useSelector } from 'react-redux'
import {
  Box,
  Grid,
  Card,
  CardContent,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  LinearProgress,
  Button,
  IconButton,
  Menu,
  MenuItem,
  Badge,
  Alert,
  Tabs,
  Tab,
  Avatar,
  Divider,
} from '@mui/material'
import {
  Dashboard as DashboardIcon,
  People as PeopleIcon,
  Phone as PhoneIcon,
  Campaign as CampaignIcon,
  TrendingUp as TrendingUpIcon,
  TrendingDown as TrendingDownIcon,
  MoreVert as MoreVertIcon,
  Refresh as RefreshIcon,
  Visibility as VisibilityIcon,
  VolumeUp as VolumeUpIcon,
  BarChart as BarChartIcon,
  Timeline as TimelineIcon,
} from '@mui/icons-material'
import { selectUser, selectIsSupervisor } from '../../store/slices/authSlice'
import {
  useDashboardUpdates,
  useCampaignStats,
  useWebSocket,
} from '../../hooks/useWebSocket'
import {
  useGetCampaignsQuery,
  useGetDashboardStatsQuery,
} from '../../store/api/apiSlice'

const SupervisorDashboard = () => {
  const user = useSelector(selectUser)
  const isSupervisor = useSelector(selectIsSupervisor)

  // WebSocket hooks
  const { isConnected, error: wsError, subscribeToStats, unsubscribeFromStats } = useWebSocket()
  const { dashboardData } = useDashboardUpdates()
  const { campaignStats } = useCampaignStats()

  // API hooks
  const { data: campaigns = [], refetch: refetchCampaigns } = useGetCampaignsQuery()
  const { data: dashboardStats = {}, refetch: refetchStats } = useGetDashboardStatsQuery(
    {},
    { pollingInterval: 30000 } // Poll every 30 seconds
  )

  // Local state
  const [currentTab, setCurrentTab] = useState(0)
  const [selectedAgent, setSelectedAgent] = useState(null)
  const [agentMenuAnchor, setAgentMenuAnchor] = useState(null)
  const [autoRefresh, setAutoRefresh] = useState(true)

  // Subscribe to real-time stats on mount
  useEffect(() => {
    if (isConnected) {
      subscribeToStats()
      return () => unsubscribeFromStats()
    }
  }, [isConnected, subscribeToStats, unsubscribeFromStats])

  // Auto refresh data
  useEffect(() => {
    if (autoRefresh) {
      const interval = setInterval(() => {
        refetchStats()
        refetchCampaigns()
      }, 60000) // Refresh every minute
      return () => clearInterval(interval)
    }
  }, [autoRefresh, refetchStats, refetchCampaigns])

  const handleAgentMenuOpen = (event, agent) => {
    setSelectedAgent(agent)
    setAgentMenuAnchor(event.currentTarget)
  }

  const handleAgentMenuClose = () => {
    setSelectedAgent(null)
    setAgentMenuAnchor(null)
  }

  const getStatusColor = (status) => {
    switch (status) {
      case 'available': return 'success'
      case 'on_call': return 'info'
      case 'wrap_up': return 'warning'
      case 'not_ready': return 'error'
      case 'offline': return 'default'
      default: return 'default'
    }
  }

  const formatDuration = (seconds) => {
    const hours = Math.floor(seconds / 3600)
    const mins = Math.floor((seconds % 3600) / 60)
    const secs = seconds % 60
    if (hours > 0) {
      return `${hours}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
    }
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }

  const formatPercentage = (value, total) => {
    if (!total || total === 0) return '0%'
    return `${Math.round((value / total) * 100)}%`
  }

  if (!isSupervisor) {
    return (
      <Box p={3}>
        <Alert severity="error">
          This dashboard is only available for supervisors and administrators.
        </Alert>
      </Box>
    )
  }

  const agents = dashboardData.agents || []
  const activeCalls = dashboardData.calls || []
  const systemStats = dashboardStats.system || {}

  return (
    <Box sx={{ p: 3 }}>
      {/* Header */}
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h4" component="h1">
          <DashboardIcon sx={{ mr: 1, verticalAlign: 'middle' }} />
          Supervisor Dashboard
        </Typography>
        <Box display="flex" gap={1}>
          <Button
            variant="outlined"
            startIcon={<RefreshIcon />}
            onClick={() => {
              refetchStats()
              refetchCampaigns()
            }}
          >
            Refresh
          </Button>
          <Button
            variant={autoRefresh ? 'contained' : 'outlined'}
            onClick={() => setAutoRefresh(!autoRefresh)}
          >
            Auto Refresh: {autoRefresh ? 'ON' : 'OFF'}
          </Button>
        </Box>
      </Box>

      {/* Connection Status */}
      {!isConnected && (
        <Alert severity="warning" sx={{ mb: 3 }}>
          WebSocket connection lost. Real-time updates may be delayed.
        </Alert>
      )}

      {wsError && (
        <Alert severity="error" sx={{ mb: 3 }}>
          WebSocket error: {wsError}
        </Alert>
      )}

      {/* Key Metrics Cards */}
      <Grid container spacing={3} mb={4}>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="space-between">
                <Box>
                  <Typography color="textSecondary" gutterBottom variant="h6">
                    Total Agents
                  </Typography>
                  <Typography variant="h4">
                    {agents.length}
                  </Typography>
                </Box>
                <PeopleIcon sx={{ fontSize: 40, color: 'primary.main' }} />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="space-between">
                <Box>
                  <Typography color="textSecondary" gutterBottom variant="h6">
                    Active Calls
                  </Typography>
                  <Typography variant="h4">
                    {activeCalls.length}
                  </Typography>
                </Box>
                <PhoneIcon sx={{ fontSize: 40, color: 'success.main' }} />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="space-between">
                <Box>
                  <Typography color="textSecondary" gutterBottom variant="h6">
                    Available Agents
                  </Typography>
                  <Typography variant="h4">
                    {agents.filter(a => a.status === 'available').length}
                  </Typography>
                </Box>
                <TrendingUpIcon sx={{ fontSize: 40, color: 'success.main' }} />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="space-between">
                <Box>
                  <Typography color="textSecondary" gutterBottom variant="h6">
                    Answer Rate
                  </Typography>
                  <Typography variant="h4">
                    {formatPercentage(systemStats.answered_calls, systemStats.total_calls)}
                  </Typography>
                </Box>
                <BarChartIcon sx={{ fontSize: 40, color: 'info.main' }} />
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Main Content Tabs */}
      <Card>
        <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
          <Tabs value={currentTab} onChange={(e, newValue) => setCurrentTab(newValue)}>
            <Tab label="Agents" />
            <Tab label="Campaigns" />
            <Tab label="Active Calls" />
            <Tab label="Analytics" />
          </Tabs>
        </Box>

        {/* Agents Tab */}
        {currentTab === 0 && (
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Agent Status Overview
            </Typography>
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Agent</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Current Call</TableCell>
                    <TableCell>Call Duration</TableCell>
                    <TableCell>Today's Stats</TableCell>
                    <TableCell>Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {agents.map((agent) => (
                    <TableRow key={agent.id}>
                      <TableCell>
                        <Box display="flex" alignItems="center">
                          <Avatar sx={{ mr: 2, width: 32, height: 32 }}>
                            {agent.username?.charAt(0).toUpperCase()}
                          </Avatar>
                          <Box>
                            <Typography variant="body2" fontWeight="bold">
                              {agent.username}
                            </Typography>
                            <Typography variant="caption" color="textSecondary">
                              {agent.department}
                            </Typography>
                          </Box>
                        </Box>
                      </TableCell>
                      <TableCell>
                        <Chip
                          label={agent.status}
                          color={getStatusColor(agent.status)}
                          variant="filled"
                          size="small"
                        />
                      </TableCell>
                      <TableCell>
                        {agent.current_call ? (
                          <Box>
                            <Typography variant="body2">
                              {agent.current_call.phone_number}
                            </Typography>
                            <Typography variant="caption" color="textSecondary">
                              {agent.current_call.campaign}
                            </Typography>
                          </Box>
                        ) : (
                          <Typography variant="body2" color="textSecondary">
                            No active call
                          </Typography>
                        )}
                      </TableCell>
                      <TableCell>
                        {agent.current_call ? (
                          formatDuration(agent.current_call.duration || 0)
                        ) : (
                          '-'
                        )}
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2">
                          Calls: {agent.stats?.calls_today || 0}
                        </Typography>
                        <Typography variant="caption" color="textSecondary">
                          Talk Time: {formatDuration(agent.stats?.talk_time_today || 0)}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <IconButton
                          size="small"
                          onClick={(e) => handleAgentMenuOpen(e, agent)}
                        >
                          <MoreVertIcon />
                        </IconButton>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>

            {/* Agent Actions Menu */}
            <Menu
              anchorEl={agentMenuAnchor}
              open={Boolean(agentMenuAnchor)}
              onClose={handleAgentMenuClose}
            >
              <MenuItem onClick={handleAgentMenuClose}>
                <VisibilityIcon sx={{ mr: 1 }} /> View Details
              </MenuItem>
              <MenuItem onClick={handleAgentMenuClose}>
                <VolumeUpIcon sx={{ mr: 1 }} /> Monitor Call
              </MenuItem>
            </Menu>
          </CardContent>
        )}

        {/* Campaigns Tab */}
        {currentTab === 1 && (
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Campaign Performance
            </Typography>
            <Grid container spacing={2}>
              {campaigns.map((campaign) => {
                const stats = campaignStats[campaign.id] || {}
                return (
                  <Grid item xs={12} md={6} lg={4} key={campaign.id}>
                    <Card variant="outlined">
                      <CardContent>
                        <Typography variant="h6" gutterBottom>
                          {campaign.name}
                        </Typography>
                        <Box mb={2}>
                          <Typography variant="body2" color="textSecondary">
                            Status: {campaign.status}
                          </Typography>
                          <Typography variant="body2" color="textSecondary">
                            Active Agents: {stats.active_agents || 0}
                          </Typography>
                        </Box>
                        <Divider sx={{ my: 1 }} />
                        <Grid container spacing={1}>
                          <Grid item xs={6}>
                            <Typography variant="body2">
                              Calls Made: {stats.calls_made || 0}
                            </Typography>
                          </Grid>
                          <Grid item xs={6}>
                            <Typography variant="body2">
                              Answered: {stats.answered || 0}
                            </Typography>
                          </Grid>
                          <Grid item xs={6}>
                            <Typography variant="body2">
                              Answer Rate: {formatPercentage(stats.answered, stats.calls_made)}
                            </Typography>
                          </Grid>
                          <Grid item xs={6}>
                            <Typography variant="body2">
                              Leads Left: {stats.leads_remaining || 0}
                            </Typography>
                          </Grid>
                        </Grid>
                        {stats.calls_made > 0 && (
                          <Box mt={1}>
                            <Typography variant="caption" color="textSecondary">
                              Progress
                            </Typography>
                            <LinearProgress
                              variant="determinate"
                              value={Math.min((stats.calls_made / (stats.calls_made + stats.leads_remaining)) * 100, 100)}
                              sx={{ mt: 0.5 }}
                            />
                          </Box>
                        )}
                      </CardContent>
                    </Card>
                  </Grid>
                )
              })}
            </Grid>
          </CardContent>
        )}

        {/* Active Calls Tab */}
        {currentTab === 2 && (
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Live Call Monitoring
            </Typography>
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Agent</TableCell>
                    <TableCell>Phone Number</TableCell>
                    <TableCell>Campaign</TableCell>
                    <TableCell>Duration</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {activeCalls.map((call) => (
                    <TableRow key={call.id}>
                      <TableCell>{call.agent_username}</TableCell>
                      <TableCell>{call.phone_number}</TableCell>
                      <TableCell>{call.campaign_name}</TableCell>
                      <TableCell>{formatDuration(call.duration || 0)}</TableCell>
                      <TableCell>
                        <Chip
                          label={call.status}
                          color={call.status === 'connected' ? 'success' : 'info'}
                          variant="filled"
                          size="small"
                        />
                      </TableCell>
                      <TableCell>
                        <Button size="small" startIcon={<VolumeUpIcon />}>
                          Monitor
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                  {activeCalls.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={6} align="center">
                        <Typography variant="body2" color="textSecondary">
                          No active calls at the moment
                        </Typography>
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </TableContainer>
          </CardContent>
        )}

        {/* Analytics Tab */}
        {currentTab === 3 && (
          <CardContent>
            <Typography variant="h6" gutterBottom>
              System Analytics
            </Typography>
            <Grid container spacing={3}>
              <Grid item xs={12} md={6}>
                <Card variant="outlined">
                  <CardContent>
                    <Typography variant="h6" gutterBottom>
                      Today's Performance
                    </Typography>
                    <Box display="flex" justifyContent="space-between" mb={1}>
                      <Typography>Total Calls:</Typography>
                      <Typography fontWeight="bold">
                        {systemStats.total_calls || 0}
                      </Typography>
                    </Box>
                    <Box display="flex" justifyContent="space-between" mb={1}>
                      <Typography>Answered:</Typography>
                      <Typography fontWeight="bold" color="success.main">
                        {systemStats.answered_calls || 0}
                      </Typography>
                    </Box>
                    <Box display="flex" justifyContent="space-between" mb={1}>
                      <Typography>No Answer:</Typography>
                      <Typography fontWeight="bold" color="warning.main">
                        {systemStats.no_answer_calls || 0}
                      </Typography>
                    </Box>
                    <Box display="flex" justifyContent="space-between" mb={1}>
                      <Typography>Busy:</Typography>
                      <Typography fontWeight="bold" color="error.main">
                        {systemStats.busy_calls || 0}
                      </Typography>
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} md={6}>
                <Card variant="outlined">
                  <CardContent>
                    <Typography variant="h6" gutterBottom>
                      Agent Utilization
                    </Typography>
                    <Box mb={2}>
                      <Typography variant="body2" gutterBottom>
                        Available: {agents.filter(a => a.status === 'available').length}
                      </Typography>
                      <LinearProgress
                        variant="determinate"
                        value={(agents.filter(a => a.status === 'available').length / Math.max(agents.length, 1)) * 100}
                        color="success"
                        sx={{ mb: 1 }}
                      />
                    </Box>
                    <Box mb={2}>
                      <Typography variant="body2" gutterBottom>
                        On Call: {agents.filter(a => a.status === 'on_call').length}
                      </Typography>
                      <LinearProgress
                        variant="determinate"
                        value={(agents.filter(a => a.status === 'on_call').length / Math.max(agents.length, 1)) * 100}
                        color="info"
                        sx={{ mb: 1 }}
                      />
                    </Box>
                    <Box>
                      <Typography variant="body2" gutterBottom>
                        Not Ready: {agents.filter(a => a.status === 'not_ready').length}
                      </Typography>
                      <LinearProgress
                        variant="determinate"
                        value={(agents.filter(a => a.status === 'not_ready').length / Math.max(agents.length, 1)) * 100}
                        color="error"
                      />
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </CardContent>
        )}
      </Card>
    </Box>
  )
}

export default SupervisorDashboard
