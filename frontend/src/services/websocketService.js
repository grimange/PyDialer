/**
 * WebSocket Service for PyDialer
 * Handles real-time communication with Django Channels backend
 * Supports agent status, call events, and dashboard updates
 */

class WebSocketService {
  constructor() {
    this.ws = null
    this.url = null
    this.token = null
    this.isConnected = false
    this.isConnecting = false
    this.reconnectAttempts = 0
    this.maxReconnectAttempts = 5
    this.reconnectInterval = 1000 // Start with 1 second
    this.maxReconnectInterval = 30000 // Max 30 seconds
    this.reconnectTimer = null
    this.heartbeatTimer = null
    this.heartbeatInterval = 30000 // 30 seconds
    
    // Event listeners for different message types
    this.listeners = {
      connect: [],
      disconnect: [],
      error: [],
      agentStatus: [],
      callEvent: [],
      campaignStats: [],
      dashboardUpdate: [],
      notification: [],
      transcript: [], // For AI transcription events
      raw: [], // For raw message handling
    }

    // Message queue for messages sent while disconnected
    this.messageQueue = []
    
    // Bind methods to preserve 'this' context
    this.connect = this.connect.bind(this)
    this.disconnect = this.disconnect.bind(this)
    this.send = this.send.bind(this)
    this.handleMessage = this.handleMessage.bind(this)
    this.handleOpen = this.handleOpen.bind(this)
    this.handleClose = this.handleClose.bind(this)
    this.handleError = this.handleError.bind(this)
    this.startHeartbeat = this.startHeartbeat.bind(this)
    this.stopHeartbeat = this.stopHeartbeat.bind(this)
    this.reconnect = this.reconnect.bind(this)
  }

  /**
   * Connect to WebSocket server
   * @param {string} token - JWT token for authentication
   * @param {Object} options - Connection options
   */
  connect(token, options = {}) {
    if (this.isConnected || this.isConnecting) {
      console.log('WebSocket: Already connected or connecting')
      return Promise.resolve()
    }

    this.token = token
    this.isConnecting = true

    // Build WebSocket URL
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = options.host || window.location.host
    const baseUrl = `${protocol}//${host}/ws/`
    
    // Add token as query parameter for authentication
    this.url = `${baseUrl}?token=${encodeURIComponent(token)}`

    console.log('WebSocket: Connecting to', this.url.replace(token, '***'))

    return new Promise((resolve, reject) => {
      try {
        this.ws = new WebSocket(this.url)
        
        this.ws.onopen = (event) => {
          this.handleOpen(event)
          resolve()
        }
        
        this.ws.onmessage = this.handleMessage
        this.ws.onclose = this.handleClose
        this.ws.onerror = (error) => {
          this.handleError(error)
          reject(error)
        }

        // Connection timeout
        setTimeout(() => {
          if (this.isConnecting) {
            this.isConnecting = false
            this.ws?.close()
            reject(new Error('WebSocket connection timeout'))
          }
        }, 10000) // 10 second timeout
        
      } catch (error) {
        this.isConnecting = false
        console.error('WebSocket: Connection error', error)
        reject(error)
      }
    })
  }

  /**
   * Disconnect from WebSocket server
   */
  disconnect() {
    console.log('WebSocket: Disconnecting...')
    
    this.stopHeartbeat()
    this.stopReconnect()
    
    if (this.ws) {
      this.ws.onopen = null
      this.ws.onmessage = null
      this.ws.onclose = null
      this.ws.onerror = null
      
      if (this.ws.readyState === WebSocket.OPEN) {
        this.ws.close(1000, 'Client disconnecting')
      }
      
      this.ws = null
    }
    
    this.isConnected = false
    this.isConnecting = false
    this.reconnectAttempts = 0
    
    this.emit('disconnect')
  }

  /**
   * Send message to WebSocket server
   * @param {string} type - Message type
   * @param {Object} data - Message data
   */
  send(type, data = {}) {
    const message = {
      type,
      data,
      timestamp: new Date().toISOString(),
    }

    if (this.isConnected && this.ws?.readyState === WebSocket.OPEN) {
      try {
        this.ws.send(JSON.stringify(message))
        console.log('WebSocket: Sent message', { type, data })
      } catch (error) {
        console.error('WebSocket: Send error', error)
        this.messageQueue.push(message)
      }
    } else {
      console.log('WebSocket: Queuing message while disconnected', { type, data })
      this.messageQueue.push(message)
    }
  }

  /**
   * Handle WebSocket open event
   */
  handleOpen(event) {
    console.log('WebSocket: Connected successfully')
    
    this.isConnected = true
    this.isConnecting = false
    this.reconnectAttempts = 0
    this.reconnectInterval = 1000 // Reset reconnect interval
    
    this.startHeartbeat()
    this.emit('connect', event)
    
    // Send queued messages
    if (this.messageQueue.length > 0) {
      console.log(`WebSocket: Sending ${this.messageQueue.length} queued messages`)
      const queue = [...this.messageQueue]
      this.messageQueue = []
      
      queue.forEach(message => {
        this.ws.send(JSON.stringify(message))
      })
    }

    // Send initial presence/status message
    this.send('agent_status', { status: 'online' })
  }

  /**
   * Handle WebSocket close event
   */
  handleClose(event) {
    console.log('WebSocket: Connection closed', { code: event.code, reason: event.reason })
    
    this.isConnected = false
    this.isConnecting = false
    this.stopHeartbeat()
    
    this.emit('disconnect', event)
    
    // Attempt reconnection unless explicitly closed by client
    if (event.code !== 1000) {
      this.scheduleReconnect()
    }
  }

  /**
   * Handle WebSocket error event
   */
  handleError(error) {
    console.error('WebSocket: Error occurred', error)
    this.emit('error', error)
  }

  /**
   * Handle incoming WebSocket messages
   */
  handleMessage(event) {
    try {
      const message = JSON.parse(event.data)
      console.log('WebSocket: Received message', message)

      // Emit raw message for any listeners
      this.emit('raw', message)

      // Route message based on type
      switch (message.type) {
        case 'agent_status':
          this.emit('agentStatus', message.data)
          break
        
        case 'call_event':
          this.emit('callEvent', message.data)
          break
        
        case 'campaign_stats':
          this.emit('campaignStats', message.data)
          break
        
        case 'dashboard_update':
          this.emit('dashboardUpdate', message.data)
          break
        
        case 'notification':
          this.emit('notification', message.data)
          break
          
        case 'transcript':
          this.emit('transcript', message.data)
          break
        
        case 'pong':
          // Heartbeat response
          console.log('WebSocket: Heartbeat pong received')
          break
        
        default:
          console.warn('WebSocket: Unknown message type', message.type)
          break
      }
    } catch (error) {
      console.error('WebSocket: Message parsing error', error, event.data)
    }
  }

  /**
   * Start heartbeat to keep connection alive
   */
  startHeartbeat() {
    this.heartbeatTimer = setInterval(() => {
      if (this.isConnected) {
        this.send('ping')
      }
    }, this.heartbeatInterval)
  }

  /**
   * Stop heartbeat
   */
  stopHeartbeat() {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer)
      this.heartbeatTimer = null
    }
  }

  /**
   * Schedule reconnection attempt
   */
  scheduleReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('WebSocket: Max reconnection attempts reached')
      return
    }

    this.reconnectAttempts++
    
    console.log(`WebSocket: Scheduling reconnect attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts} in ${this.reconnectInterval}ms`)
    
    this.reconnectTimer = setTimeout(() => {
      this.reconnect()
    }, this.reconnectInterval)
    
    // Exponential backoff with jitter
    this.reconnectInterval = Math.min(
      this.reconnectInterval * 2 + Math.random() * 1000,
      this.maxReconnectInterval
    )
  }

  /**
   * Stop reconnection attempts
   */
  stopReconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
  }

  /**
   * Attempt to reconnect
   */
  async reconnect() {
    if (this.isConnected || this.isConnecting) {
      return
    }

    console.log('WebSocket: Attempting to reconnect...')
    
    try {
      await this.connect(this.token)
      console.log('WebSocket: Reconnection successful')
    } catch (error) {
      console.error('WebSocket: Reconnection failed', error)
      this.scheduleReconnect()
    }
  }

  /**
   * Add event listener
   * @param {string} event - Event type
   * @param {Function} listener - Event listener function
   */
  on(event, listener) {
    if (this.listeners[event]) {
      this.listeners[event].push(listener)
    } else {
      console.warn(`WebSocket: Unknown event type: ${event}`)
    }
  }

  /**
   * Remove event listener
   * @param {string} event - Event type
   * @param {Function} listener - Event listener function
   */
  off(event, listener) {
    if (this.listeners[event]) {
      const index = this.listeners[event].indexOf(listener)
      if (index !== -1) {
        this.listeners[event].splice(index, 1)
      }
    }
  }

  /**
   * Emit event to all listeners
   * @param {string} event - Event type
   * @param {*} data - Event data
   */
  emit(event, data) {
    if (this.listeners[event]) {
      this.listeners[event].forEach(listener => {
        try {
          listener(data)
        } catch (error) {
          console.error(`WebSocket: Listener error for event ${event}:`, error)
        }
      })
    }
  }

  /**
   * Get connection status
   */
  getStatus() {
    return {
      isConnected: this.isConnected,
      isConnecting: this.isConnecting,
      reconnectAttempts: this.reconnectAttempts,
      readyState: this.ws?.readyState,
      url: this.url,
    }
  }

  // Convenience methods for common operations
  updateAgentStatus(status) {
    this.send('agent_status', { status })
  }

  joinCampaign(campaignId) {
    this.send('join_campaign', { campaign_id: campaignId })
  }

  leaveCampaign(campaignId) {
    this.send('leave_campaign', { campaign_id: campaignId })
  }

  subscribeToStats() {
    this.send('subscribe_stats')
  }

  unsubscribeFromStats() {
    this.send('unsubscribe_stats')
  }
}

// Create singleton instance
const websocketService = new WebSocketService()

export default websocketService
