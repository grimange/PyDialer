import React from 'react'
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { Box, Container, AppBar, Toolbar, Typography, Button } from '@mui/material'
import PhoneIcon from '@mui/icons-material/Phone'
import DashboardIcon from '@mui/icons-material/Dashboard'
import PeopleIcon from '@mui/icons-material/People'
import './App.css'

// Placeholder components for initial setup
const Dashboard = () => (
  <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
    <Typography variant="h4" component="h1" gutterBottom>
      Dashboard
    </Typography>
    <Typography variant="body1">
      Welcome to PyDialer - Django Channels-based Predictive Dialer System
    </Typography>
  </Container>
)

const Agents = () => (
  <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
    <Typography variant="h4" component="h1" gutterBottom>
      Agents
    </Typography>
    <Typography variant="body1">
      Agent management and status monitoring
    </Typography>
  </Container>
)

const Campaigns = () => (
  <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
    <Typography variant="h4" component="h1" gutterBottom>
      Campaigns
    </Typography>
    <Typography variant="body1">
      Campaign management and predictive dialing configuration
    </Typography>
  </Container>
)

function App() {
  return (
    <Router>
      <Box sx={{ flexGrow: 1 }}>
        <AppBar position="static">
          <Toolbar>
            <PhoneIcon sx={{ mr: 2 }} />
            <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
              PyDialer
            </Typography>
            <Button
              color="inherit"
              startIcon={<DashboardIcon />}
              href="/"
            >
              Dashboard
            </Button>
            <Button
              color="inherit"
              startIcon={<PeopleIcon />}
              href="/agents"
            >
              Agents
            </Button>
            <Button
              color="inherit"
              startIcon={<PhoneIcon />}
              href="/campaigns"
            >
              Campaigns
            </Button>
          </Toolbar>
        </AppBar>

        <main>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/agents" element={<Agents />} />
            <Route path="/campaigns" element={<Campaigns />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </Box>
    </Router>
  )
}

export default App
