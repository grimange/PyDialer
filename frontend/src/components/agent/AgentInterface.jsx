import React, { useState, useEffect } from 'react'
import { useSelector } from 'react-redux'
import {
  Box,
  Grid,
  Card,
  CardContent,
  Typography,
  Button,
  Chip,
  Divider,
  TextField,
  MenuItem,
  FormControl,
  InputLabel,
  Select,
  Paper,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  IconButton,
  Badge,
  Alert,
  LinearProgress,
} from '@mui/material'
import {
  Phone as PhoneIcon,
  PhoneCallback as PhoneCallbackIcon,
  PhoneDisabled as PhoneDisabledIcon,
  AccessTime as AccessTimeIcon,
  Person as PersonIcon,
  Campaign as CampaignIcon,
  Notes as NotesIcon,
  History as HistoryIcon,
  Mic as MicIcon,
  MicOff as MicOffIcon,
  VolumeUp as VolumeUpIcon,
  VolumeOff as VolumeOffIcon,
  Notifications as NotificationsIcon,
} from '@mui/icons-material'
import { selectUser, selectIsAgent } from '../../store/slices/authSlice'
import {
  useAgentStatus,
  useCallEvents,
  useNotifications,
  useTranscripts,
  useWebSocket,
} from '../../hooks/useWebSocket'
import {
  useGetDispositionsQuery,
  useCreateDispositionMutation,
} from '../../store/api/apiSlice'

const AgentInterface = () => {
  const user = useSelector(selectUser)
  const isAgent = useSelector(selectIsAgent)

  // WebSocket hooks
  const { isConnected, error: wsError } = useWebSocket()
  const {
    agentStatus,
    updateStatus,
    goAvailable,
    goUnavailable,
    goOnCall,
    goWrapUp,
  } = useAgentStatus()
  const { currentCall, callHistory } = useCallEvents()
  const { notifications, clearNotification } = useNotifications()
  const { currentTranscript } = useTranscripts()

  // API hooks
  const { data: dispositions = [] } = useGetDispositionsQuery()
  const [createDisposition, { isLoading: isCreatingDisposition }] = useCreateDispositionMutation()

  // Local state
  const [selectedDisposition, setSelectedDisposition] = useState('')
  const [dispositionNotes, setDispositionNotes] = useState('')
  const [wrapUpTimer, setWrapUpTimer] = useState(0)
  const [callTimer, setCallTimer] = useState(0)
  const [isMuted, setIsMuted] = useState(false)
  const [volumeLevel, setVolumeLevel] = useState(80)

  // Timer effects
  useEffect(() => {
    let timer
    if (agentStatus?.status === 'wrap_up' && wrapUpTimer > 0) {
      timer = setInterval(() => {
        setWrapUpTimer(prev => {
          if (prev <= 1) {
            goAvailable()
            return 0
          }
          return prev - 1
        })
      }, 1000)
    }
    return () => clearInterval(timer)
  }, [agentStatus?.status, wrapUpTimer, goAvailable])

  useEffect(() => {
    let timer
    if (currentCall) {
      timer = setInterval(() => {
        setCallTimer(prev => prev + 1)
      }, 1000)
    } else {
      setCallTimer(0)
    }
    return () => clearInterval(timer)
  }, [currentCall])

  // Handle call end and disposition
  const handleCallEnd = () => {
    setWrapUpTimer(30) // 30 second wrap-up period
    goWrapUp()
  }

  const handleDisposition = async () => {
    if (!currentCall || !selectedDisposition) return

    try {
      await createDisposition({
        call_id: currentCall.call_id,
        disposition_code: selectedDisposition,
        notes: dispositionNotes,
      }).unwrap()

      // Reset disposition form
      setSelectedDisposition('')
      setDispositionNotes('')
      
      // End wrap-up and go available
      setWrapUpTimer(0)
      goAvailable()
    } catch (error) {
      console.error('Failed to create disposition:', error)
    }
  }

  const getStatusColor = (status) => {
    switch (status) {
      case 'available': return 'success'
      case 'on_call': return 'info'
      case 'wrap_up': return 'warning'
      case 'not_ready': return 'error'
      default: return 'default'
    }
  }

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
  }

  if (!isAgent) {
    return (
      <Box p={3}>
        <Alert severity="error">
          This interface is only available for agents.
        </Alert>
      </Box>
    )
  }

  return (
    <Box sx={{ p: 2 }}>
      <Grid container spacing={3}>
        {/* Connection Status */}
        {!isConnected && (
          <Grid item xs={12}>
            <Alert severity="warning">
              WebSocket connection lost. Attempting to reconnect...
            </Alert>
          </Grid>
        )}

        {wsError && (
          <Grid item xs={12}>
            <Alert severity="error">
              WebSocket error: {wsError}
            </Alert>
          </Grid>
        )}

        {/* Agent Status Card */}
        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Agent Status
              </Typography>
              
              <Box display="flex" alignItems="center" mb={2}>
                <PersonIcon sx={{ mr: 1 }} />
                <Typography variant="body1">
                  {user?.username || 'Unknown Agent'}
                </Typography>
              </Box>

              <Box display="flex" alignItems="center" mb={2}>
                <Chip
                  label={agentStatus?.status || 'offline'}
                  color={getStatusColor(agentStatus?.status)}
                  variant="filled"
                />
                {agentStatus?.status === 'wrap_up' && wrapUpTimer > 0 && (
                  <Typography variant="body2" sx={{ ml: 2 }}>
                    {formatTime(wrapUpTimer)}
                  </Typography>
                )}
              </Box>

              <Box display="flex" gap={1} flexWrap="wrap">
                <Button
                  variant="contained"
                  color="success"
                  size="small"
                  onClick={goAvailable}
                  disabled={agentStatus?.status === 'available'}
                >
                  Available
                </Button>
                <Button
                  variant="contained"
                  color="error"
                  size="small"
                  onClick={goUnavailable}
                  disabled={agentStatus?.status === 'not_ready'}
                >
                  Not Ready
                </Button>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Current Call Card */}
        <Grid item xs={12} md={8}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Current Call
              </Typography>

              {currentCall ? (
                <Box>
                  <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                    <Typography variant="h4" color="primary">
                      {currentCall.phone_number || 'Unknown Number'}
                    </Typography>
                    <Typography variant="h6" color="textSecondary">
                      {formatTime(callTimer)}
                    </Typography>
                  </Box>

                  <Grid container spacing={2}>
                    <Grid item xs={6}>
                      <Typography variant="body2" color="textSecondary">
                        Lead Name
                      </Typography>
                      <Typography variant="body1">
                        {currentCall.lead_name || 'No Name Available'}
                      </Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography variant="body2" color="textSecondary">
                        Campaign
                      </Typography>
                      <Typography variant="body1">
                        {currentCall.campaign_name || 'Unknown Campaign'}
                      </Typography>
                    </Grid>
                  </Grid>

                  {/* Call Controls */}
                  <Box display="flex" gap={2} mt={3}>
                    <IconButton
                      color={isMuted ? 'error' : 'default'}
                      onClick={() => setIsMuted(!isMuted)}
                    >
                      {isMuted ? <MicOffIcon /> : <MicIcon />}
                    </IconButton>
                    <IconButton
                      color="default"
                      onClick={() => setVolumeLevel(volumeLevel > 0 ? 0 : 80)}
                    >
                      {volumeLevel > 0 ? <VolumeUpIcon /> : <VolumeOffIcon />}
                    </IconButton>
                    <Button
                      variant="contained"
                      color="error"
                      startIcon={<PhoneDisabledIcon />}
                      onClick={handleCallEnd}
                    >
                      End Call
                    </Button>
                  </Box>

                  {/* Live Transcript */}
                  {currentTranscript && (
                    <Box mt={3}>
                      <Typography variant="subtitle2" gutterBottom>
                        Live Transcript
                      </Typography>
                      <Paper sx={{ p: 2, bgcolor: 'grey.50', minHeight: 100 }}>
                        <Typography variant="body2">
                          {currentTranscript.transcript}
                        </Typography>
                      </Paper>
                    </Box>
                  )}
                </Box>
              ) : (
                <Box textAlign="center" py={4}>
                  <PhoneIcon sx={{ fontSize: 64, color: 'text.secondary', mb: 2 }} />
                  <Typography variant="h6" color="textSecondary">
                    No Active Call
                  </Typography>
                  <Typography variant="body2" color="textSecondary">
                    Waiting for incoming call...
                  </Typography>
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Disposition Form */}
        {agentStatus?.status === 'wrap_up' && (
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Call Disposition
                </Typography>

                <FormControl fullWidth margin="normal">
                  <InputLabel>Disposition</InputLabel>
                  <Select
                    value={selectedDisposition}
                    onChange={(e) => setSelectedDisposition(e.target.value)}
                    label="Disposition"
                  >
                    {dispositions.map((disp) => (
                      <MenuItem key={disp.id} value={disp.code}>
                        {disp.name}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>

                <TextField
                  fullWidth
                  multiline
                  rows={3}
                  label="Notes"
                  value={dispositionNotes}
                  onChange={(e) => setDispositionNotes(e.target.value)}
                  margin="normal"
                />

                <Box display="flex" gap={2} mt={2}>
                  <Button
                    variant="contained"
                    color="primary"
                    onClick={handleDisposition}
                    disabled={!selectedDisposition || isCreatingDisposition}
                    fullWidth
                  >
                    {isCreatingDisposition ? 'Saving...' : 'Complete Disposition'}
                  </Button>
                </Box>

                {wrapUpTimer > 0 && (
                  <Box mt={2}>
                    <Typography variant="body2" gutterBottom>
                      Auto-available in: {formatTime(wrapUpTimer)}
                    </Typography>
                    <LinearProgress 
                      variant="determinate" 
                      value={(30 - wrapUpTimer) / 30 * 100} 
                    />
                  </Box>
                )}
              </CardContent>
            </Card>
          </Grid>
        )}

        {/* Notifications */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                <NotificationsIcon sx={{ mr: 1, verticalAlign: 'middle' }} />
                Notifications
                {notifications.length > 0 && (
                  <Badge badgeContent={notifications.length} color="error" sx={{ ml: 1 }} />
                )}
              </Typography>

              {notifications.length > 0 ? (
                <List dense>
                  {notifications.slice(0, 5).map((notification) => (
                    <ListItem
                      key={notification.id}
                      secondaryAction={
                        <IconButton
                          edge="end"
                          size="small"
                          onClick={() => clearNotification(notification.id)}
                        >
                          ×
                        </IconButton>
                      }
                    >
                      <ListItemText
                        primary={notification.message}
                        secondary={notification.timestamp?.toLocaleTimeString()}
                      />
                    </ListItem>
                  ))}
                </List>
              ) : (
                <Typography variant="body2" color="textSecondary">
                  No new notifications
                </Typography>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Call History */}
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                <HistoryIcon sx={{ mr: 1, verticalAlign: 'middle' }} />
                Recent Calls
              </Typography>

              {callHistory.length > 0 ? (
                <List>
                  {callHistory.slice(0, 10).map((call, index) => (
                    <ListItem key={call.call_id || index} divider>
                      <ListItemIcon>
                        <PhoneCallbackIcon />
                      </ListItemIcon>
                      <ListItemText
                        primary={call.phone_number || 'Unknown Number'}
                        secondary={`${call.campaign_name || 'Unknown Campaign'} - ${call.disposition || 'No Disposition'}`}
                      />
                      <Typography variant="body2" color="textSecondary">
                        {call.ended_at ? new Date(call.ended_at).toLocaleTimeString() : 'Unknown Time'}
                      </Typography>
                    </ListItem>
                  ))}
                </List>
              ) : (
                <Typography variant="body2" color="textSecondary">
                  No recent calls
                </Typography>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  )
}

export default AgentInterface
