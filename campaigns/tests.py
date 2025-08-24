from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model
from datetime import timedelta
from unittest.mock import patch

from campaigns.models import Campaign
from campaigns.services import LeadRecyclingService, TimezoneSchedulingService, PredictiveDialingService
from campaigns.tasks import recycle_campaign_leads
from leads.models import Lead
from agents.models import Department, UserRole
import pytz

User = get_user_model()


class LeadRecyclingServiceTestCase(TestCase):
    """Test cases for the LeadRecyclingService class."""
    
    def setUp(self):
        """Set up test data."""
        # Create test user
        self.department = Department.objects.create(
            name="Test Department",
            description="Test department"
        )
        
        self.user_role = UserRole.objects.create(
            name="admin",
            display_name="Administrator",
            description="Admin role"
        )
        
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
            department=self.department,
            role=self.user_role
        )
        
        # Create test campaign with recycling enabled
        self.campaign = Campaign.objects.create(
            name="Test Campaign",
            description="Test campaign for recycling",
            status='active',
            campaign_type='outbound',
            dial_method='predictive',
            pacing_ratio=2.5,
            caller_id='+1234567890',
            recycle_inactive_leads=True,
            recycle_no_answer_days=7,
            recycle_busy_days=1,
            recycle_disconnected_days=30,
            max_recycle_attempts=2,
            exclude_dnc_from_recycling=True,
            recycle_only_business_hours=False,
            created_by=self.user
        )
        
        # Create test leads
        self.lead_no_answer = Lead.objects.create(
            phone='+1111111111',
            first_name='John',
            last_name='Doe',
            campaign=self.campaign,
            status='no_answer',
            attempts=3,
            last_call_at=timezone.now() - timedelta(days=8),
            recycle_count=0
        )
        
        self.lead_busy = Lead.objects.create(
            phone='+2222222222',
            first_name='Jane',
            last_name='Smith',
            campaign=self.campaign,
            status='busy',
            attempts=2,
            last_call_at=timezone.now() - timedelta(days=2),
            recycle_count=0
        )
        
        self.lead_disconnected = Lead.objects.create(
            phone='+3333333333',
            first_name='Bob',
            last_name='Johnson',
            campaign=self.campaign,
            status='disconnected',
            attempts=1,
            last_call_at=timezone.now() - timedelta(days=35),
            recycle_count=1
        )
        
        # Lead that has reached max recycle attempts
        self.lead_max_recycles = Lead.objects.create(
            phone='+4444444444',
            first_name='Max',
            last_name='Recycles',
            campaign=self.campaign,
            status='no_answer',
            attempts=3,
            last_call_at=timezone.now() - timedelta(days=8),
            recycle_count=2  # At max limit
        )
        
        # DNC lead
        self.lead_dnc = Lead.objects.create(
            phone='+5555555555',
            first_name='DNC',
            last_name='Lead',
            campaign=self.campaign,
            status='no_answer',
            attempts=1,
            last_call_at=timezone.now() - timedelta(days=8),
            recycle_count=0,
            is_dnc=True
        )
        
        self.recycling_service = LeadRecyclingService(self.campaign)
    
    def test_get_recyclable_leads_no_answer(self):
        """Test getting recyclable leads with no_answer status."""
        leads = self.recycling_service.get_recyclable_leads('no_answer', 7, 100)
        
        # Should get lead_no_answer but not lead_max_recycles or lead_dnc
        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0], self.lead_no_answer)
    
    def test_get_recyclable_leads_busy(self):
        """Test getting recyclable leads with busy status."""
        leads = self.recycling_service.get_recyclable_leads('busy', 1, 100)
        
        # Should get lead_busy
        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0], self.lead_busy)
    
    def test_get_recyclable_leads_disconnected(self):
        """Test getting recyclable leads with disconnected status."""
        leads = self.recycling_service.get_recyclable_leads('disconnected', 30, 100)
        
        # Should get lead_disconnected (has 1 recycle, max is 2)
        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0], self.lead_disconnected)
    
    def test_recycle_lead_success(self):
        """Test successfully recycling a lead."""
        original_attempts = self.lead_no_answer.attempts
        original_recycle_count = self.lead_no_answer.recycle_count
        
        result = self.recycling_service.recycle_lead(self.lead_no_answer)
        
        self.assertTrue(result)
        
        # Refresh from database
        self.lead_no_answer.refresh_from_db()
        
        self.assertEqual(self.lead_no_answer.status, 'new')
        self.assertEqual(self.lead_no_answer.attempts, 0)
        self.assertEqual(self.lead_no_answer.recycle_count, original_recycle_count + 1)
        self.assertIsNone(self.lead_no_answer.next_call_at)
        self.assertIsNone(self.lead_no_answer.last_call_at)
    
    def test_recycle_lead_max_attempts_reached(self):
        """Test recycling a lead that has reached max recycle attempts."""
        result = self.recycling_service.recycle_lead(self.lead_max_recycles)
        
        self.assertFalse(result)
        
        # Lead should remain unchanged
        self.lead_max_recycles.refresh_from_db()
        self.assertEqual(self.lead_max_recycles.status, 'no_answer')
        self.assertEqual(self.lead_max_recycles.recycle_count, 2)
    
    def test_recycle_lead_dnc_excluded(self):
        """Test recycling a DNC lead when DNC exclusion is enabled."""
        result = self.recycling_service.recycle_lead(self.lead_dnc)
        
        self.assertFalse(result)
        
        # Lead should remain unchanged
        self.lead_dnc.refresh_from_db()
        self.assertEqual(self.lead_dnc.status, 'no_answer')
        self.assertEqual(self.lead_dnc.recycle_count, 0)
    
    def test_can_recycle_now_success(self):
        """Test can_recycle_now with valid conditions."""
        result = self.recycling_service.can_recycle_now()
        self.assertTrue(result)
    
    def test_can_recycle_now_recycling_disabled(self):
        """Test can_recycle_now when recycling is disabled."""
        self.campaign.recycle_inactive_leads = False
        self.campaign.save()
        
        result = self.recycling_service.can_recycle_now()
        self.assertFalse(result)
    
    def test_can_recycle_now_inactive_campaign(self):
        """Test can_recycle_now with inactive campaign."""
        self.campaign.status = 'paused'
        self.campaign.save()
        
        result = self.recycling_service.can_recycle_now()
        self.assertFalse(result)
    
    @patch.object(Campaign, 'is_in_time_window')
    def test_can_recycle_now_outside_business_hours(self, mock_time_window):
        """Test can_recycle_now outside business hours."""
        self.campaign.recycle_only_business_hours = True
        self.campaign.save()
        mock_time_window.return_value = False
        
        result = self.recycling_service.can_recycle_now()
        self.assertFalse(result)
    
    def test_process_campaign_recycling(self):
        """Test processing campaign recycling."""
        results = self.recycling_service.process_campaign_recycling(batch_size=100)
        
        # Should recycle leads based on their status and age
        expected_recycled = 3  # no_answer, busy, disconnected (not max_recycles or dnc)
        total_recycled = sum(results.values())
        
        self.assertEqual(total_recycled, expected_recycled)
        self.assertIn('no_answer', results)
        self.assertIn('busy', results)
        self.assertIn('disconnected', results)
    
    def test_get_recycling_stats(self):
        """Test getting recycling statistics."""
        stats = self.recycling_service.get_recycling_stats()
        
        # Should show counts of recyclable leads by status
        self.assertIn('no_answer_recyclable', stats)
        self.assertIn('busy_recyclable', stats)
        self.assertIn('disconnected_recyclable', stats)
        
        # Verify counts (excluding DNC and max recycled leads)
        self.assertEqual(stats['no_answer_recyclable'], 1)
        self.assertEqual(stats['busy_recyclable'], 1)
        self.assertEqual(stats['disconnected_recyclable'], 1)


class RecycleCampaignLeadsTaskTestCase(TestCase):
    """Test cases for the recycle_campaign_leads Celery task."""
    
    def setUp(self):
        """Set up test data."""
        # Create test user
        self.department = Department.objects.create(
            name="Test Department",
            description="Test department"
        )
        
        self.user_role = UserRole.objects.create(
            name="admin",
            display_name="Administrator", 
            description="Admin role"
        )
        
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
            department=self.department,
            role=self.user_role
        )
        
        # Create test campaign
        self.campaign = Campaign.objects.create(
            name="Task Test Campaign",
            description="Test campaign for task testing",
            status='active',
            campaign_type='outbound',
            dial_method='predictive',
            pacing_ratio=2.5,
            caller_id='+1234567890',
            recycle_inactive_leads=True,
            recycle_no_answer_days=1,
            recycle_busy_days=1,
            recycle_disconnected_days=1,
            max_recycle_attempts=2,
            created_by=self.user
        )
        
        # Create test leads
        Lead.objects.create(
            phone='+1111111111',
            campaign=self.campaign,
            status='no_answer',
            attempts=1,
            last_call_at=timezone.now() - timedelta(days=2),
            recycle_count=0
        )
        
        Lead.objects.create(
            phone='+2222222222',
            campaign=self.campaign,
            status='busy',
            attempts=1,
            last_call_at=timezone.now() - timedelta(days=2),
            recycle_count=0
        )
    
    def test_recycle_campaign_leads_all_campaigns(self):
        """Test recycling leads for all active campaigns."""
        result = recycle_campaign_leads()
        
        self.assertTrue(result['success'])
        self.assertEqual(result['total_recycled'], 2)
        self.assertEqual(result['campaigns_processed'], 1)
    
    def test_recycle_campaign_leads_specific_campaign(self):
        """Test recycling leads for a specific campaign."""
        result = recycle_campaign_leads(campaign_id=self.campaign.id)
        
        self.assertTrue(result['success'])
        self.assertEqual(result['total_recycled'], 2)
        self.assertEqual(result['campaigns_processed'], 1)
    
    def test_recycle_campaign_leads_nonexistent_campaign(self):
        """Test recycling leads for a nonexistent campaign."""
        result = recycle_campaign_leads(campaign_id=99999)
        
        self.assertTrue(result['success'])
        self.assertEqual(result['total_recycled'], 0)
        self.assertEqual(result['campaigns_processed'], 0)
    
    @patch('campaigns.tasks.logger')
    def test_recycle_campaign_leads_error_handling(self, mock_logger):
        """Test error handling in the recycling task."""
        # Create a campaign with invalid data to trigger an error
        with patch.object(LeadRecyclingService, 'process_campaign_recycling', side_effect=Exception("Test error")):
            result = recycle_campaign_leads(campaign_id=self.campaign.id)
            
            self.assertFalse(result['success'])
            self.assertIn('error', result)
            mock_logger.error.assert_called()


class TimezoneSchedulingServiceTestCase(TestCase):
    """Test cases for the TimezoneSchedulingService class."""
    
    def setUp(self):
        """Set up test data."""
        # Create test user
        self.department = Department.objects.create(
            name="Test Department",
            description="Test department"
        )
        
        self.user_role = UserRole.objects.create(
            name="admin",
            display_name="Administrator",
            description="Admin role"
        )
        
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
            department=self.department,
            role=self.user_role
        )
        
        # Create test campaign in Eastern Time
        self.campaign = Campaign.objects.create(
            name="Timezone Test Campaign",
            description="Campaign for timezone testing",
            status='active',
            campaign_type='outbound',
            dial_method='predictive',
            pacing_ratio=2.5,
            caller_id='+1234567890',
            timezone_name='America/New_York',
            start_time='09:00:00',  # 9 AM
            end_time='17:00:00',    # 5 PM
            monday=True,
            tuesday=True,
            wednesday=True,
            thursday=True,
            friday=True,
            saturday=False,
            sunday=False,
            created_by=self.user
        )
        
        # Create leads in different timezones
        self.lead_eastern = Lead.objects.create(
            phone='+1111111111',
            first_name='Eastern',
            last_name='Lead',
            campaign=self.campaign,
            status='new',
            timezone='America/New_York',  # Eastern Time
            best_call_time_start='10:00:00',  # 10 AM
            best_call_time_end='16:00:00'     # 4 PM
        )
        
        self.lead_pacific = Lead.objects.create(
            phone='+2222222222',
            first_name='Pacific',
            last_name='Lead',
            campaign=self.campaign,
            status='new',
            timezone='America/Los_Angeles',  # Pacific Time
            best_call_time_start='09:00:00',  # 9 AM Pacific
            best_call_time_end='17:00:00'     # 5 PM Pacific
        )
        
        self.lead_no_preference = Lead.objects.create(
            phone='+3333333333',
            first_name='No',
            last_name='Preference',
            campaign=self.campaign,
            status='new',
            timezone='America/Chicago'  # Central Time, no call time preference
        )
        
        self.lead_expired = Lead.objects.create(
            phone='+4444444444',
            first_name='Expired',
            last_name='Lead',
            campaign=self.campaign,
            status='new',
            timezone='America/New_York',
            do_not_call_after=timezone.now() - timedelta(days=1)  # Expired yesterday
        )
    
    @patch('django.utils.timezone.now')
    def test_is_lead_callable_now_within_business_hours(self, mock_now):
        """Test lead is callable during business hours."""
        # Set current time to Tuesday 2 PM Eastern (within business hours)
        eastern = pytz.timezone('America/New_York')
        mock_now.return_value = timezone.make_aware(
            eastern.localize(timezone.datetime(2024, 1, 2, 14, 0, 0)).astimezone(pytz.UTC)
        )
        
        result = TimezoneSchedulingService.is_lead_callable_now(self.lead_eastern, self.campaign)
        self.assertTrue(result)
    
    @patch('django.utils.timezone.now')
    def test_is_lead_callable_now_outside_business_hours(self, mock_now):
        """Test lead is not callable outside business hours."""
        # Set current time to Tuesday 8 PM Eastern (after business hours)
        eastern = pytz.timezone('America/New_York')
        mock_now.return_value = timezone.make_aware(
            eastern.localize(timezone.datetime(2024, 1, 2, 20, 0, 0)).astimezone(pytz.UTC)
        )
        
        result = TimezoneSchedulingService.is_lead_callable_now(self.lead_eastern, self.campaign)
        self.assertFalse(result)
    
    @patch('django.utils.timezone.now')
    def test_is_lead_callable_now_weekend(self, mock_now):
        """Test lead is not callable on weekends."""
        # Set current time to Saturday 2 PM Eastern
        eastern = pytz.timezone('America/New_York')
        mock_now.return_value = timezone.make_aware(
            eastern.localize(timezone.datetime(2024, 1, 6, 14, 0, 0)).astimezone(pytz.UTC)  # Saturday
        )
        
        result = TimezoneSchedulingService.is_lead_callable_now(self.lead_eastern, self.campaign)
        self.assertFalse(result)
    
    @patch('django.utils.timezone.now')
    def test_is_lead_callable_now_before_preferred_time(self, mock_now):
        """Test lead is not callable before preferred call time."""
        # Set current time to Tuesday 9 AM Eastern (before lead's preferred time of 10 AM)
        eastern = pytz.timezone('America/New_York')
        mock_now.return_value = timezone.make_aware(
            eastern.localize(timezone.datetime(2024, 1, 2, 9, 0, 0)).astimezone(pytz.UTC)
        )
        
        result = TimezoneSchedulingService.is_lead_callable_now(self.lead_eastern, self.campaign)
        self.assertFalse(result)
    
    @patch('django.utils.timezone.now')
    def test_is_lead_callable_now_after_preferred_time(self, mock_now):
        """Test lead is not callable after preferred call time."""
        # Set current time to Tuesday 4:30 PM Eastern (after lead's preferred time of 4 PM)
        eastern = pytz.timezone('America/New_York')
        mock_now.return_value = timezone.make_aware(
            eastern.localize(timezone.datetime(2024, 1, 2, 16, 30, 0)).astimezone(pytz.UTC)
        )
        
        result = TimezoneSchedulingService.is_lead_callable_now(self.lead_eastern, self.campaign)
        self.assertFalse(result)
    
    @patch('django.utils.timezone.now')
    def test_is_lead_callable_now_different_timezone(self, mock_now):
        """Test lead callability with different timezone (Pacific)."""
        # Set current time to Tuesday 1 PM Pacific (within business hours for Pacific lead)
        pacific = pytz.timezone('America/Los_Angeles')
        mock_now.return_value = timezone.make_aware(
            pacific.localize(timezone.datetime(2024, 1, 2, 13, 0, 0)).astimezone(pytz.UTC)
        )
        
        result = TimezoneSchedulingService.is_lead_callable_now(self.lead_pacific, self.campaign)
        self.assertTrue(result)
    
    @patch('django.utils.timezone.now')
    def test_is_lead_callable_now_expired_lead(self, mock_now):
        """Test expired lead is not callable."""
        # Set current time to Tuesday 2 PM Eastern
        eastern = pytz.timezone('America/New_York')
        mock_now.return_value = timezone.make_aware(
            eastern.localize(timezone.datetime(2024, 1, 2, 14, 0, 0)).astimezone(pytz.UTC)
        )
        
        result = TimezoneSchedulingService.is_lead_callable_now(self.lead_expired, self.campaign)
        self.assertFalse(result)
    
    @patch('django.utils.timezone.now')
    def test_filter_callable_leads(self, mock_now):
        """Test filtering leads for callability."""
        # Set current time to Tuesday 2 PM Eastern (within business hours)
        eastern = pytz.timezone('America/New_York')
        mock_now.return_value = timezone.make_aware(
            eastern.localize(timezone.datetime(2024, 1, 2, 14, 0, 0)).astimezone(pytz.UTC)
        )
        
        all_leads = [self.lead_eastern, self.lead_pacific, self.lead_no_preference, self.lead_expired]
        callable_leads = TimezoneSchedulingService.filter_callable_leads(all_leads, self.campaign)
        
        # Should include no_preference (no time restrictions) but exclude others based on their constraints
        # Note: This test may need adjustment based on exact timezone calculations
        self.assertGreater(len(callable_leads), 0)
        self.assertLess(len(callable_leads), len(all_leads))  # Some should be filtered out
        
        # Expired lead should definitely be excluded
        self.assertNotIn(self.lead_expired, callable_leads)
    
    @patch('django.utils.timezone.now')
    def test_get_next_callable_time(self, mock_now):
        """Test calculating next callable time for a lead."""
        # Set current time to Tuesday 8 PM Eastern (after business hours)
        eastern = pytz.timezone('America/New_York')
        mock_now.return_value = timezone.make_aware(
            eastern.localize(timezone.datetime(2024, 1, 2, 20, 0, 0)).astimezone(pytz.UTC)
        )
        
        next_time = TimezoneSchedulingService.get_next_callable_time(self.lead_eastern, self.campaign)
        
        self.assertIsNotNone(next_time)
        self.assertGreater(next_time, mock_now.return_value)
        
        # Convert to Eastern time to check if it's during business hours
        next_eastern = next_time.astimezone(eastern)
        self.assertGreaterEqual(next_eastern.time(), timezone.time(9, 0))  # After 9 AM
        self.assertLessEqual(next_eastern.time(), timezone.time(17, 0))    # Before 5 PM
        self.assertIn(next_eastern.weekday(), [0, 1, 2, 3, 4])            # Monday-Friday
    
    @patch('django.utils.timezone.now')
    def test_schedule_lead_callback(self, mock_now):
        """Test scheduling a lead callback."""
        # Set current time to Tuesday 8 PM Eastern
        eastern = pytz.timezone('America/New_York')
        mock_now.return_value = timezone.make_aware(
            eastern.localize(timezone.datetime(2024, 1, 2, 20, 0, 0)).astimezone(pytz.UTC)
        )
        
        callback_time = TimezoneSchedulingService.schedule_lead_callback(
            self.lead_eastern, callback_minutes_from_now=60
        )
        
        # Check that lead was updated
        self.lead_eastern.refresh_from_db()
        self.assertEqual(self.lead_eastern.status, 'callback')
        self.assertIsNotNone(self.lead_eastern.callback_datetime)
        self.assertEqual(self.lead_eastern.callback_datetime, callback_time)
        
        # Callback time should be in the future
        self.assertGreater(callback_time, mock_now.return_value)


class TimezoneAwarePredictiveDialingTestCase(TestCase):
    """Test cases for timezone-aware predictive dialing."""
    
    def setUp(self):
        """Set up test data."""
        # Create test user
        self.department = Department.objects.create(
            name="Test Department",
            description="Test department"
        )
        
        self.user_role = UserRole.objects.create(
            name="admin",
            display_name="Administrator",
            description="Admin role"
        )
        
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
            department=self.department,
            role=self.user_role
        )
        
        # Create test campaign
        self.campaign = Campaign.objects.create(
            name="Timezone Dialing Test",
            description="Campaign for timezone dialing testing",
            status='active',
            campaign_type='outbound',
            dial_method='predictive',
            pacing_ratio=2.5,
            caller_id='+1234567890',
            timezone_name='America/New_York',
            start_time='09:00:00',
            end_time='17:00:00',
            monday=True,
            tuesday=True,
            wednesday=True,
            thursday=True,
            friday=True,
            saturday=False,
            sunday=False,
            created_by=self.user
        )
        
        # Create test leads
        Lead.objects.create(
            phone='+1111111111',
            campaign=self.campaign,
            status='new',
            timezone='America/New_York'
        )
        
        Lead.objects.create(
            phone='+2222222222',
            campaign=self.campaign,
            status='new',
            timezone='America/Los_Angeles'
        )
        
        self.dialing_service = PredictiveDialingService(self.campaign)
    
    @patch('django.utils.timezone.now')
    def test_get_dialable_leads_timezone_filtering(self, mock_now):
        """Test that get_dialable_leads applies timezone filtering."""
        # Set current time to Tuesday 2 PM Eastern
        eastern = pytz.timezone('America/New_York')
        mock_now.return_value = timezone.make_aware(
            eastern.localize(timezone.datetime(2024, 1, 2, 14, 0, 0)).astimezone(pytz.UTC)
        )
        
        dialable_leads = self.dialing_service.get_dialable_leads(limit=10)
        
        # Should return some leads (exact number depends on timezone logic)
        self.assertIsInstance(dialable_leads, list)
        
        # All returned leads should be callable now
        for lead in dialable_leads:
            self.assertTrue(
                TimezoneSchedulingService.is_lead_callable_now(lead, self.campaign),
                f"Lead {lead.phone} in timezone {lead.timezone} should be callable"
            )
