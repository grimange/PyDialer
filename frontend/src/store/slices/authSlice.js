import { createSlice } from '@reduxjs/toolkit'

const initialState = {
  user: null,
  token: localStorage.getItem('token'),
  refreshToken: localStorage.getItem('refreshToken'),
  isAuthenticated: false,
  loading: false,
  error: null,
  role: null,
  permissions: [],
  department: null,
  team: null,
  agentStatus: 'offline', // offline, available, on_call, wrap_up, not_ready
}

const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    loginStart: (state) => {
      state.loading = true
      state.error = null
    },
    loginSuccess: (state, action) => {
      state.loading = false
      state.isAuthenticated = true
      state.user = action.payload.user
      state.token = action.payload.access
      state.refreshToken = action.payload.refresh
      state.role = action.payload.user.role
      state.permissions = action.payload.user.permissions || []
      state.department = action.payload.user.department
      state.team = action.payload.user.team
      state.error = null
      
      // Store tokens in localStorage
      localStorage.setItem('token', action.payload.access)
      localStorage.setItem('refreshToken', action.payload.refresh)
    },
    loginFailure: (state, action) => {
      state.loading = false
      state.isAuthenticated = false
      state.user = null
      state.token = null
      state.refreshToken = null
      state.role = null
      state.permissions = []
      state.department = null
      state.team = null
      state.agentStatus = 'offline'
      state.error = action.payload
      
      // Clear tokens from localStorage
      localStorage.removeItem('token')
      localStorage.removeItem('refreshToken')
    },
    logout: (state) => {
      state.isAuthenticated = false
      state.user = null
      state.token = null
      state.refreshToken = null
      state.role = null
      state.permissions = []
      state.department = null
      state.team = null
      state.agentStatus = 'offline'
      state.error = null
      
      // Clear tokens from localStorage
      localStorage.removeItem('token')
      localStorage.removeItem('refreshToken')
    },
    refreshTokenSuccess: (state, action) => {
      state.token = action.payload.access
      localStorage.setItem('token', action.payload.access)
    },
    updateAgentStatus: (state, action) => {
      state.agentStatus = action.payload
    },
    updateUserProfile: (state, action) => {
      state.user = { ...state.user, ...action.payload }
    },
    clearError: (state) => {
      state.error = null
    },
    setLoading: (state, action) => {
      state.loading = action.payload
    },
  },
})

export const {
  loginStart,
  loginSuccess,
  loginFailure,
  logout,
  refreshTokenSuccess,
  updateAgentStatus,
  updateUserProfile,
  clearError,
  setLoading,
} = authSlice.actions

// Selectors
export const selectAuth = (state) => state.auth
export const selectIsAuthenticated = (state) => state.auth.isAuthenticated
export const selectUser = (state) => state.auth.user
export const selectUserRole = (state) => state.auth.role
export const selectUserPermissions = (state) => state.auth.permissions
export const selectAgentStatus = (state) => state.auth.agentStatus
export const selectAuthLoading = (state) => state.auth.loading
export const selectAuthError = (state) => state.auth.error

// Helper selectors for role-based access
export const selectIsAgent = (state) => 
  state.auth.role?.name === 'agent' || state.auth.role === 'agent'
export const selectIsSupervisor = (state) => 
  state.auth.role?.name === 'supervisor' || state.auth.role === 'supervisor'
export const selectIsAdmin = (state) => 
  state.auth.role?.name === 'admin' || state.auth.role === 'admin'

export default authSlice.reducer
