import { useState, useEffect, useCallback, useRef } from 'react'
import { useSelector } from 'react-redux'
import { selectIsAuthenticated, selectAuth } from '../store/slices/authSlice'
import websocketService from '../services/websocketService'

/**
 * Custom hook for WebSocket connection management
 * Provides easy integration with React components
 * @param {Object} options - Configuration options
 * @param {boolean} options.autoConnect - Auto connect when authenticated (default: true)
 * @param {Array<string>} options.events - Events to subscribe to
 * @param {Object} options.eventHandlers - Event handler functions
 */
export const useWebSocket = (options = {}) => {
  const {
    autoConnect = true,
    events = [],
    eventHandlers = {},
  } = options

  const isAuthenticated = useSelector(selectIsAuthenticated)
  const auth = useSelector(selectAuth)
  const token = auth.token

  const [connectionStatus, setConnectionStatus] = useState({
    isConnected: false,
    isConnecting: false,
    error: null,
    reconnectAttempts: 0,
  })

  const eventHandlersRef = useRef(eventHandlers)
  const cleanupFunctionsRef = useRef([])

  // Update event handlers ref when they change
  useEffect(() => {
    eventHandlersRef.current = eventHandlers
  }, [eventHandlers])

  // Connection status updater
  const updateConnectionStatus = useCallback(() => {
    const status = websocketService.getStatus()
    setConnectionStatus({
      isConnected: status.isConnected,
      isConnecting: status.isConnecting,
      error: null,
      reconnectAttempts: status.reconnectAttempts,
    })
  }, [])

  // Connect to WebSocket
  const connect = useCallback(async () => {
    if (!token) {
      console.warn('useWebSocket: No token available for connection')
      return
    }

    try {
      await websocketService.connect(token)
      updateConnectionStatus()
    } catch (error) {
      console.error('useWebSocket: Connection failed', error)
      setConnectionStatus(prev => ({
        ...prev,
        error: error.message,
        isConnecting: false,
      }))
    }
  }, [token, updateConnectionStatus])

  // Disconnect from WebSocket
  const disconnect = useCallback(() => {
    websocketService.disconnect()
    updateConnectionStatus()
  }, [updateConnectionStatus])

  // Send message through WebSocket
  const sendMessage = useCallback((type, data) => {
    websocketService.send(type, data)
  }, [])

  // Setup event listeners
  useEffect(() => {
    const setupEventListeners = () => {
      // Clear previous cleanup functions
      cleanupFunctionsRef.current.forEach(cleanup => cleanup())
      cleanupFunctionsRef.current = []

      // Connection status events
      const onConnect = () => {
        updateConnectionStatus()
        eventHandlersRef.current.onConnect?.()
      }

      const onDisconnect = () => {
        updateConnectionStatus()
        eventHandlersRef.current.onDisconnect?.()
      }

      const onError = (error) => {
        setConnectionStatus(prev => ({
          ...prev,
          error: error.message || 'WebSocket error',
        }))
        eventHandlersRef.current.onError?.(error)
      }

      // Register connection event listeners
      websocketService.on('connect', onConnect)
      websocketService.on('disconnect', onDisconnect)
      websocketService.on('error', onError)

      // Add cleanup functions
      cleanupFunctionsRef.current.push(() => {
        websocketService.off('connect', onConnect)
        websocketService.off('disconnect', onDisconnect)
        websocketService.off('error', onError)
      })

      // Register custom event listeners
      events.forEach(eventType => {
        const handler = (data) => {
          eventHandlersRef.current[eventType]?.(data)
        }

        websocketService.on(eventType, handler)
        cleanupFunctionsRef.current.push(() => {
          websocketService.off(eventType, handler)
        })
      })
    }

    setupEventListeners()

    // Cleanup on unmount
    return () => {
      cleanupFunctionsRef.current.forEach(cleanup => cleanup())
      cleanupFunctionsRef.current = []
    }
  }, [events, updateConnectionStatus])

  // Auto connect when authenticated
  useEffect(() => {
    if (autoConnect && isAuthenticated && token && !websocketService.isConnected && !websocketService.isConnecting) {
      connect()
    } else if (!isAuthenticated && websocketService.isConnected) {
      disconnect()
    }
  }, [autoConnect, isAuthenticated, token, connect, disconnect])

  // Update connection status on mount
  useEffect(() => {
    updateConnectionStatus()
  }, [updateConnectionStatus])

  return {
    ...connectionStatus,
    connect,
    disconnect,
    sendMessage,
    // Convenience methods
    updateAgentStatus: websocketService.updateAgentStatus.bind(websocketService),
    joinCampaign: websocketService.joinCampaign.bind(websocketService),
    leaveCampaign: websocketService.leaveCampaign.bind(websocketService),
    subscribeToStats: websocketService.subscribeToStats.bind(websocketService),
    unsubscribeFromStats: websocketService.unsubscribeFromStats.bind(websocketService),
  }
}

/**
 * Hook for agent status management
 */
export const useAgentStatus = () => {
  const [agentStatus, setAgentStatus] = useState(null)
  const [statusHistory, setStatusHistory] = useState([])

  const { sendMessage } = useWebSocket({
    events: ['agentStatus'],
    eventHandlers: {
      agentStatus: (data) => {
        setAgentStatus(data)
        setStatusHistory(prev => [...prev.slice(-9), data]) // Keep last 10 status changes
      },
    },
  })

  const updateStatus = useCallback((status) => {
    sendMessage('agent_status', { status })
  }, [sendMessage])

  const goAvailable = useCallback(() => updateStatus('available'), [updateStatus])
  const goUnavailable = useCallback(() => updateStatus('not_ready'), [updateStatus])
  const goOnCall = useCallback(() => updateStatus('on_call'), [updateStatus])
  const goWrapUp = useCallback(() => updateStatus('wrap_up'), [updateStatus])

  return {
    agentStatus,
    statusHistory,
    updateStatus,
    goAvailable,
    goUnavailable,
    goOnCall,
    goWrapUp,
  }
}

/**
 * Hook for campaign statistics
 */
export const useCampaignStats = () => {
  const [campaignStats, setCampaignStats] = useState({})

  useWebSocket({
    events: ['campaignStats'],
    eventHandlers: {
      campaignStats: (data) => {
        setCampaignStats(prev => ({
          ...prev,
          [data.campaign_id]: data,
        }))
      },
    },
  })

  return { campaignStats }
}

/**
 * Hook for call events
 */
export const useCallEvents = () => {
  const [currentCall, setCurrentCall] = useState(null)
  const [callHistory, setCallHistory] = useState([])

  useWebSocket({
    events: ['callEvent'],
    eventHandlers: {
      callEvent: (data) => {
        if (data.event === 'call_started' || data.event === 'call_answered') {
          setCurrentCall(data)
        } else if (data.event === 'call_ended') {
          setCurrentCall(null)
          setCallHistory(prev => [data, ...prev.slice(0, 49)]) // Keep last 50 calls
        } else {
          // Update current call with event data
          setCurrentCall(prev => prev ? { ...prev, ...data } : data)
        }
      },
    },
  })

  return {
    currentCall,
    callHistory,
  }
}

/**
 * Hook for dashboard updates (supervisor use)
 */
export const useDashboardUpdates = () => {
  const [dashboardData, setDashboardData] = useState({
    agents: [],
    campaigns: [],
    calls: [],
    stats: {},
  })

  useWebSocket({
    events: ['dashboardUpdate'],
    eventHandlers: {
      dashboardUpdate: (data) => {
        setDashboardData(prev => ({
          ...prev,
          ...data,
        }))
      },
    },
  })

  return { dashboardData }
}

/**
 * Hook for notifications
 */
export const useNotifications = () => {
  const [notifications, setNotifications] = useState([])

  useWebSocket({
    events: ['notification'],
    eventHandlers: {
      notification: (data) => {
        const notification = {
          ...data,
          id: Date.now(),
          timestamp: new Date(),
        }
        setNotifications(prev => [notification, ...prev.slice(0, 49)]) // Keep last 50 notifications
      },
    },
  })

  const clearNotification = useCallback((id) => {
    setNotifications(prev => prev.filter(n => n.id !== id))
  }, [])

  const clearAllNotifications = useCallback(() => {
    setNotifications([])
  }, [])

  return {
    notifications,
    clearNotification,
    clearAllNotifications,
  }
}

/**
 * Hook for AI transcription events
 */
export const useTranscripts = () => {
  const [transcripts, setTranscripts] = useState({})
  const [currentTranscript, setCurrentTranscript] = useState(null)

  useWebSocket({
    events: ['transcript'],
    eventHandlers: {
      transcript: (data) => {
        const { call_id, transcript, is_final, timestamp } = data
        
        setTranscripts(prev => ({
          ...prev,
          [call_id]: {
            ...prev[call_id],
            segments: [
              ...(prev[call_id]?.segments || []),
              { transcript, is_final, timestamp },
            ],
            last_updated: timestamp,
          },
        }))

        // Update current transcript if this is for the active call
        if (data.is_current) {
          setCurrentTranscript({ call_id, transcript, is_final, timestamp })
        }
      },
    },
  })

  const clearTranscript = useCallback((callId) => {
    setTranscripts(prev => {
      const updated = { ...prev }
      delete updated[callId]
      return updated
    })
  }, [])

  return {
    transcripts,
    currentTranscript,
    clearTranscript,
  }
}

export default useWebSocket
