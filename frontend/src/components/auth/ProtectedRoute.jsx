import React from 'react'
import { useSelector } from 'react-redux'
import { Navigate, useLocation } from 'react-router-dom'
import { Box, CircularProgress, Typography } from '@mui/material'
import {
  selectIsAuthenticated,
  selectAuthLoading,
  selectUserRole,
  selectUser,
  selectIsAgent,
  selectIsSupervisor,
  selectIsAdmin,
} from '../../store/slices/authSlice'

/**
 * ProtectedRoute component that handles authentication and role-based access control
 * @param {Object} props
 * @param {React.ReactNode} props.children - The component to render if authorized
 * @param {Array<string>} props.allowedRoles - Array of roles that can access this route (e.g., ['agent', 'supervisor', 'admin'])
 * @param {boolean} props.requireAuth - Whether authentication is required (default: true)
 * @param {string} props.redirectTo - Where to redirect unauthorized users (default: '/login')
 */
const ProtectedRoute = ({
  children,
  allowedRoles = null, // null means all authenticated users can access
  requireAuth = true,
  redirectTo = '/login',
}) => {
  const location = useLocation()
  
  const isAuthenticated = useSelector(selectIsAuthenticated)
  const loading = useSelector(selectAuthLoading)
  const user = useSelector(selectUser)
  const userRole = useSelector(selectUserRole)
  const isAgent = useSelector(selectIsAgent)
  const isSupervisor = useSelector(selectIsSupervisor)
  const isAdmin = useSelector(selectIsAdmin)

  // Show loading spinner while checking authentication
  if (loading) {
    return (
      <Box
        sx={{
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          alignItems: 'center',
          minHeight: '100vh',
          gap: 2,
        }}
      >
        <CircularProgress size={40} />
        <Typography variant="body2" color="textSecondary">
          Checking authentication...
        </Typography>
      </Box>
    )
  }

  // Redirect to login if authentication is required but user is not authenticated
  if (requireAuth && !isAuthenticated) {
    return (
      <Navigate 
        to={redirectTo} 
        state={{ from: location }} 
        replace 
      />
    )
  }

  // Check role-based access if allowedRoles is specified
  if (isAuthenticated && allowedRoles && allowedRoles.length > 0) {
    const hasRequiredRole = checkUserRole(userRole, allowedRoles, {
      isAgent,
      isSupervisor,
      isAdmin,
    })

    if (!hasRequiredRole) {
      return (
        <Box
          sx={{
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
            alignItems: 'center',
            minHeight: '100vh',
            textAlign: 'center',
            px: 3,
          }}
        >
          <Typography variant="h4" color="error" gutterBottom>
            Access Denied
          </Typography>
          <Typography variant="body1" color="textSecondary" paragraph>
            You don't have permission to access this page.
          </Typography>
          <Typography variant="body2" color="textSecondary">
            Required role(s): {allowedRoles.join(', ')}
          </Typography>
          {userRole && (
            <Typography variant="body2" color="textSecondary">
              Your role: {typeof userRole === 'object' ? userRole.name : userRole}
            </Typography>
          )}
        </Box>
      )
    }
  }

  // User is authenticated and authorized, render the protected content
  return children
}

/**
 * Helper function to check if user has required role
 * @param {Object|string} userRole - User's role object or string
 * @param {Array<string>} allowedRoles - Array of allowed role names
 * @param {Object} roleHelpers - Helper booleans for role checking
 */
const checkUserRole = (userRole, allowedRoles, { isAgent, isSupervisor, isAdmin }) => {
  if (!userRole || !allowedRoles || allowedRoles.length === 0) {
    return false
  }

  // Handle different role formats
  const roleName = typeof userRole === 'object' ? userRole.name : userRole

  // Direct role name check
  if (allowedRoles.includes(roleName)) {
    return true
  }

  // Use helper selectors for additional flexibility
  for (const role of allowedRoles) {
    switch (role.toLowerCase()) {
      case 'agent':
        if (isAgent) return true
        break
      case 'supervisor':
        if (isSupervisor) return true
        break
      case 'admin':
        if (isAdmin) return true
        break
      default:
        // Handle custom roles
        if (roleName === role) return true
        break
    }
  }

  return false
}

// Convenience components for common role-based routes
export const AgentRoute = ({ children, ...props }) => (
  <ProtectedRoute allowedRoles={['agent', 'supervisor', 'admin']} {...props}>
    {children}
  </ProtectedRoute>
)

export const SupervisorRoute = ({ children, ...props }) => (
  <ProtectedRoute allowedRoles={['supervisor', 'admin']} {...props}>
    {children}
  </ProtectedRoute>
)

export const AdminRoute = ({ children, ...props }) => (
  <ProtectedRoute allowedRoles={['admin']} {...props}>
    {children}
  </ProtectedRoute>
)

// Component for role-based conditional rendering within components
export const RoleBasedComponent = ({ 
  allowedRoles, 
  children, 
  fallback = null 
}) => {
  const userRole = useSelector(selectUserRole)
  const isAgent = useSelector(selectIsAgent)
  const isSupervisor = useSelector(selectIsSupervisor)
  const isAdmin = useSelector(selectIsAdmin)

  const hasRequiredRole = checkUserRole(userRole, allowedRoles, {
    isAgent,
    isSupervisor,
    isAdmin,
  })

  return hasRequiredRole ? children : fallback
}

export default ProtectedRoute
