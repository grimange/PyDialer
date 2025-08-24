import React, { useState, useEffect } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { useNavigate, useLocation } from 'react-router-dom'
import {
  Box,
  Card,
  CardContent,
  TextField,
  Button,
  Typography,
  Alert,
  CircularProgress,
  Container,
  InputAdornment,
  IconButton,
} from '@mui/material'
import {
  Visibility,
  VisibilityOff,
  Person as PersonIcon,
  Lock as LockIcon,
  Phone as PhoneIcon,
} from '@mui/icons-material'
import { useLoginMutation } from '../../store/api/apiSlice'
import {
  loginStart,
  loginSuccess,
  loginFailure,
  clearError,
  selectIsAuthenticated,
  selectAuthLoading,
  selectAuthError,
} from '../../store/slices/authSlice'

const Login = () => {
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const location = useLocation()

  const [login, { isLoading: isLoginLoading }] = useLoginMutation()
  
  const isAuthenticated = useSelector(selectIsAuthenticated)
  const loading = useSelector(selectAuthLoading)
  const error = useSelector(selectAuthError)

  const [formData, setFormData] = useState({
    username: '',
    password: '',
  })
  const [showPassword, setShowPassword] = useState(false)
  const [validationErrors, setValidationErrors] = useState({})

  // Redirect if already authenticated
  useEffect(() => {
    if (isAuthenticated) {
      const from = location.state?.from?.pathname || '/'
      navigate(from, { replace: true })
    }
  }, [isAuthenticated, navigate, location])

  // Clear errors when component mounts or form changes
  useEffect(() => {
    dispatch(clearError())
    setValidationErrors({})
  }, [dispatch, formData])

  const handleInputChange = (e) => {
    const { name, value } = e.target
    setFormData(prev => ({
      ...prev,
      [name]: value,
    }))
  }

  const handleTogglePasswordVisibility = () => {
    setShowPassword(prev => !prev)
  }

  const validateForm = () => {
    const errors = {}
    
    if (!formData.username.trim()) {
      errors.username = 'Username is required'
    }
    
    if (!formData.password.trim()) {
      errors.password = 'Password is required'
    } else if (formData.password.length < 6) {
      errors.password = 'Password must be at least 6 characters'
    }

    setValidationErrors(errors)
    return Object.keys(errors).length === 0
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    
    if (!validateForm()) {
      return
    }

    dispatch(loginStart())

    try {
      const result = await login({
        username: formData.username.trim(),
        password: formData.password,
      }).unwrap()

      dispatch(loginSuccess(result))
      
      // Navigate to the intended page or dashboard
      const from = location.state?.from?.pathname || '/'
      navigate(from, { replace: true })
    } catch (err) {
      console.error('Login error:', err)
      
      let errorMessage = 'Login failed. Please try again.'
      
      if (err.status === 401) {
        errorMessage = 'Invalid username or password.'
      } else if (err.status === 400 && err.data) {
        if (err.data.non_field_errors) {
          errorMessage = err.data.non_field_errors[0]
        } else if (err.data.detail) {
          errorMessage = err.data.detail
        }
      } else if (err.status >= 500) {
        errorMessage = 'Server error. Please try again later.'
      }

      dispatch(loginFailure(errorMessage))
    }
  }

  const isSubmitting = loading || isLoginLoading

  return (
    <Container component="main" maxWidth="sm">
      <Box
        sx={{
          minHeight: '100vh',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          alignItems: 'center',
          py: 3,
        }}
      >
        {/* Logo/Header */}
        <Box sx={{ mb: 4, textAlign: 'center' }}>
          <PhoneIcon sx={{ fontSize: 48, color: 'primary.main', mb: 2 }} />
          <Typography variant="h3" component="h1" gutterBottom>
            PyDialer
          </Typography>
          <Typography variant="h6" color="textSecondary">
            Predictive Dialer System
          </Typography>
        </Box>

        {/* Login Card */}
        <Card sx={{ width: '100%', maxWidth: 400 }}>
          <CardContent sx={{ p: 4 }}>
            <Typography variant="h4" component="h2" textAlign="center" mb={3}>
              Sign In
            </Typography>

            {error && (
              <Alert severity="error" sx={{ mb: 3 }}>
                {error}
              </Alert>
            )}

            <Box component="form" onSubmit={handleSubmit}>
              <TextField
                fullWidth
                id="username"
                name="username"
                label="Username"
                variant="outlined"
                value={formData.username}
                onChange={handleInputChange}
                error={!!validationErrors.username}
                helperText={validationErrors.username}
                disabled={isSubmitting}
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <PersonIcon />
                    </InputAdornment>
                  ),
                }}
                sx={{ mb: 2 }}
                autoComplete="username"
                autoFocus
              />

              <TextField
                fullWidth
                id="password"
                name="password"
                label="Password"
                type={showPassword ? 'text' : 'password'}
                variant="outlined"
                value={formData.password}
                onChange={handleInputChange}
                error={!!validationErrors.password}
                helperText={validationErrors.password}
                disabled={isSubmitting}
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <LockIcon />
                    </InputAdornment>
                  ),
                  endAdornment: (
                    <InputAdornment position="end">
                      <IconButton
                        aria-label="toggle password visibility"
                        onClick={handleTogglePasswordVisibility}
                        edge="end"
                        disabled={isSubmitting}
                      >
                        {showPassword ? <VisibilityOff /> : <Visibility />}
                      </IconButton>
                    </InputAdornment>
                  ),
                }}
                sx={{ mb: 3 }}
                autoComplete="current-password"
              />

              <Button
                type="submit"
                fullWidth
                variant="contained"
                size="large"
                disabled={isSubmitting}
                sx={{ mb: 2, py: 1.5 }}
              >
                {isSubmitting ? (
                  <CircularProgress size={24} color="inherit" />
                ) : (
                  'Sign In'
                )}
              </Button>
            </Box>
          </CardContent>
        </Card>

        {/* Footer */}
        <Typography variant="body2" color="textSecondary" sx={{ mt: 4 }}>
          PyDialer v1.0 - Django Channels-based Predictive Dialer
        </Typography>
      </Box>
    </Container>
  )
}

export default Login
