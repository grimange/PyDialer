"""
Basic views for the calls app.

This module contains basic DRF ViewSets for call management functionality.
"""

from rest_framework import viewsets, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend

from .models import CallTask, CallDetailRecord, Recording
from .serializers import (
    CallTaskSerializer,
    CallDetailRecordSerializer,
    RecordingSerializer
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
    filterset_fields = ['agent', 'disposition', 'call_start']
    ordering_fields = ['call_start', 'duration', 'created_at']
    ordering = ['-call_start']

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
