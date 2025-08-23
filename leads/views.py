"""
Basic views for the leads app.

This module contains basic DRF ViewSets for lead management functionality.
"""

from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django_filters.rest_framework import DjangoFilterBackend
from django.db import models
import csv
import io

from .models import Lead, Disposition, DispositionCode, LeadNote, LeadImportBatch
from .serializers import (
    LeadSerializer,
    LeadListSerializer,
    DispositionSerializer,
    DispositionCodeSerializer,
    LeadNoteSerializer,
    LeadImportBatchSerializer,
    LeadBulkImportSerializer
)
from agents.permissions import IsSupervisorOrAbove
from campaigns.models import Campaign


class LeadViewSet(viewsets.ModelViewSet):
    """
    Enhanced ViewSet for managing leads with bulk import functionality.
    """
    queryset = Lead.objects.all()
    serializer_class = LeadSerializer
    permission_classes = [permissions.IsAuthenticated, IsSupervisorOrAbove]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['campaign', 'status', 'priority', 'assigned_agent', 'is_dnc']
    search_fields = ['first_name', 'last_name', 'email', 'phone']
    ordering_fields = ['created_at', 'last_attempt_at', 'priority']
    ordering = ['-created_at']
    parser_classes = [MultiPartParser, FormParser]

    def get_serializer_class(self):
        """
        Return appropriate serializer class based on action.
        """
        if self.action == 'list':
            return LeadListSerializer
        elif self.action == 'bulk_import':
            return LeadBulkImportSerializer
        return LeadSerializer

    def get_queryset(self):
        """
        Filter queryset based on user permissions.
        """
        user = self.request.user
        queryset = Lead.objects.all()
        
        # Agents can only see leads assigned to them or unassigned leads in their campaigns
        if user.is_agent() and not user.is_supervisor():
            assigned_campaigns = user.campaignagentassignment_set.filter(
                is_active=True
            ).values_list('campaign_id', flat=True)
            queryset = queryset.filter(
                campaign_id__in=assigned_campaigns
            ).filter(
                models.Q(assigned_agent=user) | models.Q(assigned_agent__isnull=True)
            )
        
        return queryset.select_related('campaign', 'assigned_agent')

    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated, IsSupervisorOrAbove])
    def bulk_import(self, request):
        """
        Bulk import leads from CSV file.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Set campaign queryset based on user permissions
        campaign_queryset = Campaign.objects.all()
        if request.user.is_agent() and not request.user.is_supervisor():
            assigned_campaigns = request.user.campaignagentassignment_set.filter(
                is_active=True
            ).values_list('campaign_id', flat=True)
            campaign_queryset = campaign_queryset.filter(id__in=assigned_campaigns)
        
        serializer.fields['campaign'].queryset = campaign_queryset
        serializer.is_valid(raise_exception=True)
        
        # Process the import
        try:
            result = self._process_bulk_import(
                campaign=serializer.validated_data['campaign'],
                csv_file=serializer.validated_data['file'],
                skip_duplicates=serializer.validated_data['skip_duplicates'],
                update_existing=serializer.validated_data['update_existing'],
                user=request.user
            )
            
            return Response({
                'success': True,
                'message': 'Bulk import completed successfully',
                'import_batch_id': result['import_batch_id'],
                'total_processed': result['total_processed'],
                'successful': result['successful'],
                'failed': result['failed'],
                'errors': result['errors'][:10] if result['errors'] else []  # Limit error display
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response({
                'success': False,
                'message': f'Import failed: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)

    def _process_bulk_import(self, campaign, csv_file, skip_duplicates, update_existing, user):
        """
        Process CSV file and create leads.
        """
        # Create import batch record
        import_batch = LeadImportBatch.objects.create(
            campaign=campaign,
            file_name=csv_file.name,
            file_size=csv_file.size,
            uploaded_by=user
        )
        
        # Read and process CSV
        file_content = csv_file.read().decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(file_content))
        
        total_processed = 0
        successful = 0
        failed = 0
        errors = []
        
        try:
            for row in csv_reader:
                total_processed += 1
                
                try:
                    # Clean and validate row data
                    lead_data = {
                        'campaign': campaign,
                        'first_name': row.get('first_name', '').strip(),
                        'last_name': row.get('last_name', '').strip(),
                        'email': row.get('email', '').strip(),
                        'phone': row.get('phone', '').strip(),
                        'alt_phone': row.get('alt_phone', '').strip(),
                        'address': row.get('address', '').strip(),
                        'city': row.get('city', '').strip(),
                        'state': row.get('state', '').strip(),
                        'zip_code': row.get('zip_code', '').strip(),
                        'country': row.get('country', 'US'),
                        'timezone': row.get('timezone', campaign.timezone or 'America/New_York'),
                        'priority': int(row.get('priority', 1)) if row.get('priority', '').isdigit() else 1,
                    }
                    
                    # Check for required fields
                    if not lead_data['phone']:
                        errors.append(f"Row {total_processed}: Phone number is required")
                        failed += 1
                        continue
                    
                    # Handle duplicates
                    existing_lead = Lead.objects.filter(
                        phone=lead_data['phone'], 
                        campaign=campaign
                    ).first()
                    
                    if existing_lead:
                        if skip_duplicates:
                            continue
                        elif update_existing:
                            for key, value in lead_data.items():
                                if key != 'campaign' and value:
                                    setattr(existing_lead, key, value)
                            existing_lead.save()
                            successful += 1
                            continue
                        else:
                            errors.append(f"Row {total_processed}: Duplicate phone number {lead_data['phone']}")
                            failed += 1
                            continue
                    
                    # Create new lead
                    Lead.objects.create(**lead_data)
                    successful += 1
                    
                except Exception as e:
                    errors.append(f"Row {total_processed}: {str(e)}")
                    failed += 1
            
            # Update import batch
            import_batch.total_records = total_processed
            import_batch.processed_records = total_processed
            import_batch.successful_records = successful
            import_batch.failed_records = failed
            import_batch.status = 'completed'
            if errors:
                import_batch.error_log = '\n'.join(errors[:100])  # Store first 100 errors
            import_batch.save()
            
            return {
                'import_batch_id': import_batch.id,
                'total_processed': total_processed,
                'successful': successful,
                'failed': failed,
                'errors': errors
            }
            
        except Exception as e:
            import_batch.status = 'failed'
            import_batch.error_log = str(e)
            import_batch.save()
            raise e


class DispositionCodeViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only ViewSet for disposition codes.
    """
    queryset = DispositionCode.objects.filter(is_active=True)
    serializer_class = DispositionCodeSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['category', 'is_contact', 'is_sale', 'requires_callback']
    ordering_fields = ['order', 'name']
    ordering = ['order', 'name']


class DispositionViewSet(viewsets.ModelViewSet):
    """
    Basic ViewSet for managing dispositions.
    """
    queryset = Disposition.objects.all()
    serializer_class = DispositionSerializer
    permission_classes = [permissions.IsAuthenticated, IsSupervisorOrAbove]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['lead', 'agent', 'disposition_code']
    ordering_fields = ['created_at', 'callback_datetime']
    ordering = ['-created_at']

    def get_queryset(self):
        """
        Filter queryset based on user permissions.
        """
        user = self.request.user
        queryset = Disposition.objects.all()
        
        # Agents can only see their own dispositions
        if user.is_agent() and not user.is_supervisor():
            queryset = queryset.filter(agent=user)
        
        return queryset.select_related('lead', 'agent', 'disposition_code')

    def perform_create(self, serializer):
        """
        Set agent field automatically.
        """
        serializer.save(agent=self.request.user)


class LeadNoteViewSet(viewsets.ModelViewSet):
    """
    Basic ViewSet for managing lead notes.
    """
    queryset = LeadNote.objects.all()
    serializer_class = LeadNoteSerializer
    permission_classes = [permissions.IsAuthenticated, IsSupervisorOrAbove]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['lead', 'agent']
    ordering_fields = ['created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        """
        Filter queryset based on user permissions.
        """
        user = self.request.user
        queryset = LeadNote.objects.all()
        
        # Agents can only see notes for leads they can access
        if user.is_agent() and not user.is_supervisor():
            assigned_campaigns = user.campaignagentassignment_set.filter(
                is_active=True
            ).values_list('campaign_id', flat=True)
            queryset = queryset.filter(lead__campaign_id__in=assigned_campaigns)
        
        return queryset.select_related('lead', 'agent')

    def perform_create(self, serializer):
        """
        Set agent field automatically.
        """
        serializer.save(agent=self.request.user)


class LeadImportBatchViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for managing lead import batches.
    Read-only to track import history and status.
    """
    queryset = LeadImportBatch.objects.all()
    serializer_class = LeadImportBatchSerializer
    permission_classes = [permissions.IsAuthenticated, IsSupervisorOrAbove]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['campaign', 'status', 'uploaded_by']
    ordering_fields = ['uploaded_at', 'completed_at', 'total_records']
    ordering = ['-uploaded_at']

    def get_queryset(self):
        """
        Filter queryset based on user permissions.
        """
        user = self.request.user
        queryset = LeadImportBatch.objects.all()
        
        # Agents can only see imports for campaigns they have access to
        if user.is_agent() and not user.is_supervisor():
            assigned_campaigns = user.campaignagentassignment_set.filter(
                is_active=True
            ).values_list('campaign_id', flat=True)
            queryset = queryset.filter(campaign_id__in=assigned_campaigns)
        
        return queryset.select_related('campaign', 'uploaded_by')

    @action(detail=True, methods=['get'])
    def download_errors(self, request, pk=None):
        """
        Download error log for a specific import batch.
        """
        import_batch = self.get_object()
        
        if not import_batch.error_log:
            return Response({
                'success': False,
                'message': 'No errors found for this import batch'
            }, status=status.HTTP_404_NOT_FOUND)
        
        return Response({
            'success': True,
            'import_batch_id': import_batch.id,
            'file_name': import_batch.file_name,
            'error_log': import_batch.error_log,
            'failed_records': import_batch.failed_records,
            'total_records': import_batch.total_records
        })

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """
        Get summary statistics of all import batches.
        """
        queryset = self.get_queryset()
        
        summary_data = {
            'total_batches': queryset.count(),
            'successful_batches': queryset.filter(status='completed', failed_records=0).count(),
            'partial_success_batches': queryset.filter(
                status='completed', 
                failed_records__gt=0,
                successful_records__gt=0
            ).count(),
            'failed_batches': queryset.filter(status='failed').count(),
            'total_leads_imported': queryset.aggregate(
                total=models.Sum('successful_records')
            )['total'] or 0,
            'total_failed_records': queryset.aggregate(
                total=models.Sum('failed_records')
            )['total'] or 0,
        }
        
        return Response({
            'success': True,
            'summary': summary_data
        })
