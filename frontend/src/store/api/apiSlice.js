import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react'
import { loginSuccess, logout, refreshTokenSuccess } from '../slices/authSlice'

const baseQuery = fetchBaseQuery({
  baseUrl: '/api/v1/',
  prepareHeaders: (headers, { getState }) => {
    const token = getState().auth.token
    if (token) {
      headers.set('Authorization', `Bearer ${token}`)
    }
    headers.set('Content-Type', 'application/json')
    return headers
  },
})

const baseQueryWithReauth = async (args, api, extraOptions) => {
  let result = await baseQuery(args, api, extraOptions)

  if (result?.error?.status === 401) {
    console.log('Token expired, attempting refresh...')
    
    // Try to refresh the token
    const refreshToken = api.getState().auth.refreshToken
    if (refreshToken) {
      const refreshResult = await baseQuery(
        {
          url: 'auth/token/refresh/',
          method: 'POST',
          body: { refresh: refreshToken },
        },
        api,
        extraOptions
      )

      if (refreshResult?.data) {
        // Store the new token
        api.dispatch(refreshTokenSuccess(refreshResult.data))
        
        // Retry the original query with new token
        result = await baseQuery(args, api, extraOptions)
      } else {
        // Refresh failed, logout user
        api.dispatch(logout())
      }
    } else {
      // No refresh token, logout user
      api.dispatch(logout())
    }
  }

  return result
}

export const apiSlice = createApi({
  reducerPath: 'api',
  baseQuery: baseQueryWithReauth,
  tagTypes: [
    'User',
    'Agent', 
    'Campaign',
    'Lead',
    'Call',
    'Disposition',
    'Team',
    'Department'
  ],
  endpoints: (builder) => ({
    // Authentication endpoints
    login: builder.mutation({
      query: (credentials) => ({
        url: 'auth/login/',
        method: 'POST',
        body: credentials,
      }),
    }),
    logout: builder.mutation({
      query: () => ({
        url: 'auth/logout/',
        method: 'POST',
      }),
    }),
    refreshToken: builder.mutation({
      query: (refreshToken) => ({
        url: 'auth/token/refresh/',
        method: 'POST',
        body: { refresh: refreshToken },
      }),
    }),
    
    // User management endpoints
    getCurrentUser: builder.query({
      query: () => 'auth/user/',
      providesTags: ['User'],
    }),
    updateUserProfile: builder.mutation({
      query: ({ id, ...patch }) => ({
        url: `auth/users/${id}/`,
        method: 'PATCH',
        body: patch,
      }),
      invalidatesTags: ['User'],
    }),
    changePassword: builder.mutation({
      query: (passwordData) => ({
        url: 'auth/change-password/',
        method: 'POST',
        body: passwordData,
      }),
    }),
    
    // Agent status endpoints
    updateAgentStatus: builder.mutation({
      query: (statusData) => ({
        url: 'agents/status/',
        method: 'POST',
        body: statusData,
      }),
      invalidatesTags: ['Agent'],
    }),
    getAgentStatus: builder.query({
      query: () => 'agents/status/',
      providesTags: ['Agent'],
    }),
    
    // Campaign endpoints
    getCampaigns: builder.query({
      query: (params = {}) => ({
        url: 'campaigns/',
        params,
      }),
      providesTags: ['Campaign'],
    }),
    getCampaign: builder.query({
      query: (id) => `campaigns/${id}/`,
      providesTags: (result, error, id) => [{ type: 'Campaign', id }],
    }),
    createCampaign: builder.mutation({
      query: (campaignData) => ({
        url: 'campaigns/',
        method: 'POST',
        body: campaignData,
      }),
      invalidatesTags: ['Campaign'],
    }),
    updateCampaign: builder.mutation({
      query: ({ id, ...patch }) => ({
        url: `campaigns/${id}/`,
        method: 'PATCH',
        body: patch,
      }),
      invalidatesTags: (result, error, { id }) => [{ type: 'Campaign', id }],
    }),
    
    // Lead endpoints
    getLeads: builder.query({
      query: (params = {}) => ({
        url: 'leads/',
        params,
      }),
      providesTags: ['Lead'],
    }),
    getLead: builder.query({
      query: (id) => `leads/${id}/`,
      providesTags: (result, error, id) => [{ type: 'Lead', id }],
    }),
    createLead: builder.mutation({
      query: (leadData) => ({
        url: 'leads/',
        method: 'POST',
        body: leadData,
      }),
      invalidatesTags: ['Lead'],
    }),
    updateLead: builder.mutation({
      query: ({ id, ...patch }) => ({
        url: `leads/${id}/`,
        method: 'PATCH',
        body: patch,
      }),
      invalidatesTags: (result, error, { id }) => [{ type: 'Lead', id }],
    }),
    
    // Call endpoints
    getCalls: builder.query({
      query: (params = {}) => ({
        url: 'calls/',
        params,
      }),
      providesTags: ['Call'],
    }),
    getCall: builder.query({
      query: (id) => `calls/${id}/`,
      providesTags: (result, error, id) => [{ type: 'Call', id }],
    }),
    createCall: builder.mutation({
      query: (callData) => ({
        url: 'calls/',
        method: 'POST',
        body: callData,
      }),
      invalidatesTags: ['Call'],
    }),
    
    // Disposition endpoints
    getDispositions: builder.query({
      query: () => 'calls/dispositions/',
      providesTags: ['Disposition'],
    }),
    createDisposition: builder.mutation({
      query: (dispositionData) => ({
        url: 'calls/dispositions/',
        method: 'POST',
        body: dispositionData,
      }),
      invalidatesTags: ['Disposition', 'Call'],
    }),
    
    // Dashboard/Statistics endpoints
    getDashboardStats: builder.query({
      query: (params = {}) => ({
        url: 'dashboard/stats/',
        params,
      }),
    }),
    getCampaignStats: builder.query({
      query: (campaignId) => `campaigns/${campaignId}/stats/`,
    }),
    getAgentStats: builder.query({
      query: (agentId) => `agents/${agentId}/stats/`,
    }),
  }),
})

// Export hooks for usage in components
export const {
  // Auth hooks
  useLoginMutation,
  useLogoutMutation,
  useRefreshTokenMutation,
  useGetCurrentUserQuery,
  useUpdateUserProfileMutation,
  useChangePasswordMutation,
  
  // Agent hooks
  useUpdateAgentStatusMutation,
  useGetAgentStatusQuery,
  
  // Campaign hooks
  useGetCampaignsQuery,
  useGetCampaignQuery,
  useCreateCampaignMutation,
  useUpdateCampaignMutation,
  
  // Lead hooks
  useGetLeadsQuery,
  useGetLeadQuery,
  useCreateLeadMutation,
  useUpdateLeadMutation,
  
  // Call hooks
  useGetCallsQuery,
  useGetCallQuery,
  useCreateCallMutation,
  
  // Disposition hooks
  useGetDispositionsQuery,
  useCreateDispositionMutation,
  
  // Dashboard hooks
  useGetDashboardStatsQuery,
  useGetCampaignStatsQuery,
  useGetAgentStatsQuery,
} = apiSlice
