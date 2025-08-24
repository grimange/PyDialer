"""
Basic views for the calls app.

This module contains basic DRF ViewSets for call management functionality.
"""

from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from .models import CallTask, CallDetailRecord, Recording, Disposition
from .serializers import (
    CallTaskSerializer,
    CallDetailRecordSerializer,
    RecordingSerializer,
    DispositionSerializer
)
from agents.permissions import IsSupervisorOrAbove


class CallTaskViewSet(viewsets.ModelViewSet):
    """
    Basic ViewSet for managing call tasks.
    """
    queryset = CallTask.objects.all()
    serializer_class = CallTaskSerializer
    permission_classes = [permissions.IsAuthenticated, IsSupervisorOrAbove]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['campaign', 'state', 'agent']
    ordering_fields = ['scheduled_at', 'created_at', 'priority']
    ordering = ['-created_at']

    def get_queryset(self):
        """
        Filter queryset based on user permissions.
        """
        user = self.request.user
        queryset = CallTask.objects.all()
        
        # Agents can only see their own call tasks
        if user.is_agent() and not user.is_supervisor():
            queryset = queryset.filter(agent=user)
        
        return queryset.select_related('campaign', 'lead', 'agent')


class CallDetailRecordViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only ViewSet for call detail records.
    """
    queryset = CallDetailRecord.objects.all()
    serializer_class = CallDetailRecordSerializer
    permission_classes = [permissions.IsAuthenticated, IsSupervisorOrAbove]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['agent', 'call_result', 'call_date', 'campaign']
    ordering_fields = ['call_date', 'call_time', 'total_duration', 'created_at']
    ordering = ['-call_date', '-call_time']

    def get_queryset(self):
        """
        Filter queryset based on user permissions.
        """
        user = self.request.user
        queryset = CallDetailRecord.objects.all()
        
        # Agents can only see their own CDRs
        if user.is_agent() and not user.is_supervisor():
            queryset = queryset.filter(agent=user)
        
        return queryset.select_related('call_task', 'agent')


class RecordingViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only ViewSet for call recordings.
    """
    queryset = Recording.objects.all()
    serializer_class = RecordingSerializer
    permission_classes = [permissions.IsAuthenticated, IsSupervisorOrAbove]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['storage_type', 'is_encrypted', 'created_at']
    ordering_fields = ['created_at', 'duration', 'file_size']
    ordering = ['-created_at']

    def get_queryset(self):
        """
        Filter queryset based on user permissions.
        """
        user = self.request.user
        queryset = Recording.objects.all()
        
        # Agents can only see recordings for their own calls
        if user.is_agent() and not user.is_supervisor():
            queryset = queryset.filter(cdr__agent=user)
        
        return queryset.select_related('cdr')


class DispositionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing call dispositions with comprehensive filtering and actions.
    """
    queryset = Disposition.objects.all()
    serializer_class = DispositionSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = [
        'category', 'disposition_code', 'agent', 'is_final', 
        'requires_followup', 'schedule_callback', 'requires_supervisor_review',
        'supervisor_reviewed', 'call_task__campaign'
    ]
    search_fields = ['disposition_name', 'notes', 'callback_notes']
    ordering_fields = ['disposition_time', 'callback_date', 'quality_score', 'sale_amount']
    ordering = ['-disposition_time']

    def get_queryset(self):
        """
        Filter queryset based on user permissions.
        """
        user = self.request.user
        queryset = Disposition.objects.all()
        
        # Agents can only see their own dispositions
        if user.is_agent() and not user.is_supervisor():
            queryset = queryset.filter(agent=user)
        
        return queryset.select_related(
            'call_task', 'call_task__campaign', 'call_task__lead', 
            'agent', 'reviewed_by'
        )

    def perform_create(self, serializer):
        """
        Set the agent to current user when creating disposition.
        """
        serializer.save(agent=self.request.user)

    def get_permissions(self):
        """
        Set different permissions based on action.
        """
        if self.action in ['list', 'retrieve']:
            # All authenticated users can view (filtered by get_queryset)
            permission_classes = [permissions.IsAuthenticated]
        elif self.action in ['create', 'update', 'partial_update']:
            # Agents can create/update their own dispositions
            permission_classes = [permissions.IsAuthenticated]
        elif self.action == 'destroy':
            # Only supervisors can delete dispositions
            permission_classes = [permissions.IsAuthenticated, IsSupervisorOrAbove]
        else:
            permission_classes = [permissions.IsAuthenticated]
        
        return [permission() for permission in permission_classes]

    @action(detail=True, methods=['post'], permission_classes=[IsSupervisorOrAbove])
    def supervisor_review(self, request, pk=None):
        """
        Mark disposition as reviewed by supervisor.
        """
        disposition = self.get_object()
        disposition.mark_supervisor_reviewed(request.user)
        
        return Response({
            'status': 'reviewed',
            'reviewed_by': request.user.get_full_name(),
            'reviewed_at': disposition.reviewed_at
        })

    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """
        Get disposition statistics for the current user or filtered dataset.
        """
        queryset = self.filter_queryset(self.get_queryset())
        
        # Get campaign filter if provided
        campaign_id = request.query_params.get('campaign')
        if campaign_id:
            queryset = queryset.filter(call_task__campaign_id=campaign_id)
        
        # Get date range filter if provided
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        if start_date and end_date:
            queryset = queryset.filter(
                disposition_time__date__range=[start_date, end_date]
            )
        
        # Calculate statistics
        stats = Disposition.get_disposition_statistics(
            campaign_id=campaign_id if campaign_id else None,
            agent=self.request.user if self.request.user.is_agent() and not self.request.user.is_supervisor() else None,
            date_range=[start_date, end_date] if start_date and end_date else None
        )
        
        return Response(stats)

    @action(detail=False, methods=['get'])
    def callbacks_due(self, request):
        """
        Get dispositions with callbacks due today or overdue.
        """
        from django.utils import timezone
        today = timezone.now().date()
        
        queryset = self.get_queryset().filter(
            schedule_callback=True,
            callback_date__lte=today
        ).order_by('callback_date', 'callback_time')
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[IsSupervisorOrAbove])
    def pending_review(self, request):
        """
        Get dispositions that require supervisor review.
        """
        queryset = self.get_queryset().filter(
            requires_supervisor_review=True,
            supervisor_reviewed=False
        ).order_by('-disposition_time')
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
