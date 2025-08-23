"""
Views for the campaigns app.

This module contains DRF ViewSets for campaign management functionality.
"""

from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q
from django.utils import timezone

from .models import (
    Campaign, 
    CampaignAgentAssignment, 
    CampaignSchedule, 
    CampaignStatistics
)
from .serializers import (
    CampaignSerializer,
    CampaignListSerializer,
    CampaignAgentAssignmentSerializer,
    CampaignScheduleSerializer,
    CampaignStatisticsSerializer
)
from agents.permissions import IsSupervisorOrAbove, IsManagerOrAbove


class CampaignViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing campaigns with full CRUD operations.
    
    Provides standard REST endpoints for campaigns with filtering,
    searching, and custom actions for campaign management.
    """
    queryset = Campaign.objects.all()
    permission_classes = [permissions.IsAuthenticated, IsSupervisorOrAbove]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['campaign_type', 'status', 'dial_method', 'is_active']
    search_fields = ['name', 'description', 'caller_id']
    ordering_fields = ['name', 'created_at', 'start_date', 'priority']
    ordering = ['-created_at']

    def get_serializer_class(self):
        """
        Return different serializers based on action.
        """
        if self.action == 'list':
            return CampaignListSerializer
        return CampaignSerializer

    def get_queryset(self):
        """
        Filter queryset based on user permissions.
        """
        user = self.request.user
        queryset = Campaign.objects.all()
        
        # Agents can only see campaigns they're assigned to
        if user.is_agent() and not user.is_supervisor():
            assigned_campaigns = user.campaignagentassignment_set.filter(
                is_active=True
            ).values_list('campaign_id', flat=True)
            queryset = queryset.filter(id__in=assigned_campaigns)
        
        return queryset.select_related('created_by', 'updated_by')

    def perform_create(self, serializer):
        """
        Set created_by and updated_by fields.
        """
        serializer.save(
            created_by=self.request.user,
            updated_by=self.request.user
        )

    def perform_update(self, serializer):
        """
        Set updated_by field.
        """
        serializer.save(updated_by=self.request.user)

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """
        Activate a campaign.
        """
        campaign = self.get_object()
        campaign.is_active = True
        campaign.save()
        return Response({'status': 'Campaign activated'})

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """
        Deactivate a campaign.
        """
        campaign = self.get_object()
        campaign.is_active = False
        campaign.save()
        return Response({'status': 'Campaign deactivated'})

    @action(detail=True, methods=['get'])
    def statistics(self, request, pk=None):
        """
        Get campaign statistics.
        """
        campaign = self.get_object()
        stats = CampaignStatistics.objects.filter(campaign=campaign).order_by('-date')[:30]
        serializer = CampaignStatisticsSerializer(stats, many=True)
        return Response(serializer.data)


class CampaignAgentAssignmentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing campaign agent assignments.
    """
    queryset = CampaignAgentAssignment.objects.all()
    serializer_class = CampaignAgentAssignmentSerializer
    permission_classes = [permissions.IsAuthenticated, IsManagerOrAbove]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['campaign', 'agent', 'is_active']
    ordering_fields = ['assigned_at', 'priority']
    ordering = ['-assigned_at']

    def get_queryset(self):
        """
        Filter queryset based on user permissions and campaign access.
        """
        user = self.request.user
        queryset = CampaignAgentAssignment.objects.all()
        
        # Supervisors can only see assignments for campaigns they supervise
        if user.is_supervisor() and not user.is_manager():
            supervised_agents = user.get_supervised_agents()
            queryset = queryset.filter(agent__in=supervised_agents)
        
        return queryset.select_related('campaign', 'agent', 'assigned_by')

    def perform_create(self, serializer):
        """
        Set assigned_by field.
        """
        serializer.save(assigned_by=self.request.user)

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """
        Activate an agent assignment.
        """
        assignment = self.get_object()
        assignment.is_active = True
        assignment.save()
        return Response({'status': 'Assignment activated'})

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """
        Deactivate an agent assignment.
        """
        assignment = self.get_object()
        assignment.is_active = False
        assignment.save()
        return Response({'status': 'Assignment deactivated'})


class CampaignScheduleViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing campaign schedules.
    """
    queryset = CampaignSchedule.objects.all()
    serializer_class = CampaignScheduleSerializer
    permission_classes = [permissions.IsAuthenticated, IsSupervisorOrAbove]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['campaign', 'day_of_week', 'is_active']
    ordering_fields = ['day_of_week', 'start_time']
    ordering = ['day_of_week', 'start_time']

    def get_queryset(self):
        """
        Filter queryset based on campaign access.
        """
        user = self.request.user
        queryset = CampaignSchedule.objects.all()
        
        # If user is an agent, only show schedules for assigned campaigns
        if user.is_agent() and not user.is_supervisor():
            assigned_campaigns = user.campaignagentassignment_set.filter(
                is_active=True
            ).values_list('campaign_id', flat=True)
            queryset = queryset.filter(campaign_id__in=assigned_campaigns)
        
        return queryset.select_related('campaign')


class CampaignStatisticsViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only ViewSet for campaign statistics.
    
    Statistics are generated automatically and should not be manually modified.
    """
    queryset = CampaignStatistics.objects.all()
    serializer_class = CampaignStatisticsSerializer
    permission_classes = [permissions.IsAuthenticated, IsSupervisorOrAbove]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['campaign', 'date']
    ordering_fields = ['date', 'calls_attempted', 'calls_connected']
    ordering = ['-date']

    def get_queryset(self):
        """
        Filter queryset based on user permissions and campaign access.
        """
        user = self.request.user
        queryset = CampaignStatistics.objects.all()
        
        # Agents can only see statistics for assigned campaigns
        if user.is_agent() and not user.is_supervisor():
            assigned_campaigns = user.campaignagentassignment_set.filter(
                is_active=True
            ).values_list('campaign_id', flat=True)
            queryset = queryset.filter(campaign_id__in=assigned_campaigns)
        
        return queryset.select_related('campaign')

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """
        Get summary statistics across all accessible campaigns.
        """
        queryset = self.filter_queryset(self.get_queryset())
        
        # Calculate summary statistics
        from django.db.models import Sum, Avg
        summary = queryset.aggregate(
            total_calls_attempted=Sum('calls_attempted'),
            total_calls_connected=Sum('calls_connected'),
            total_calls_dropped=Sum('calls_dropped'),
            total_calls_answered=Sum('calls_answered'),
            avg_talk_time=Avg('average_talk_time'),
            total_leads_contacted=Sum('leads_contacted'),
            total_appointments=Sum('appointments_set'),
            total_sales=Sum('sales_made')
        )
        
        return Response(summary)
