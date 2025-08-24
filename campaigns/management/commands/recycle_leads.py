from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from campaigns.models import Campaign
from campaigns.services import LeadRecyclingService


class Command(BaseCommand):
    help = 'Recycle leads based on campaign recycling rules'

    def add_arguments(self, parser):
        parser.add_argument(
            '--campaign-id',
            type=int,
            help='Process only the specified campaign ID',
        )
        parser.add_argument(
            '--campaign-name',
            type=str,
            help='Process only the specified campaign name',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be recycled without making changes',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Number of leads to process per status (default: 100)',
        )
        parser.add_argument(
            '--stats-only',
            action='store_true',
            help='Show recycling statistics without processing',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output',
        )

    def handle(self, *args, **options):
        campaign_id = options.get('campaign_id')
        campaign_name = options.get('campaign_name')
        dry_run = options.get('dry_run')
        batch_size = options.get('batch_size')
        stats_only = options.get('stats_only')
        verbose = options.get('verbose')

        try:
            # Get campaigns to process
            campaigns = self.get_campaigns(campaign_id, campaign_name)
            
            if not campaigns.exists():
                self.stdout.write(
                    self.style.WARNING('No campaigns found matching the criteria.')
                )
                return

            total_recycled = 0
            campaigns_processed = 0

            for campaign in campaigns:
                self.stdout.write(f"\nProcessing campaign: {campaign.name}")
                
                recycling_service = LeadRecyclingService(campaign)
                
                # Show statistics
                if stats_only or verbose:
                    stats = recycling_service.get_recycling_stats()
                    self.show_campaign_stats(campaign, stats)
                    
                if stats_only:
                    continue
                
                # Check if recycling can proceed
                if not recycling_service.can_recycle_now():
                    reasons = []
                    if not campaign.recycle_inactive_leads:
                        reasons.append("recycling disabled")
                    if campaign.status != 'active':
                        reasons.append("campaign not active")
                    if campaign.recycle_only_business_hours and not campaign.is_in_time_window():
                        reasons.append("outside business hours")
                    
                    self.stdout.write(
                        self.style.WARNING(
                            f"  Skipping: {', '.join(reasons)}"
                        )
                    )
                    continue
                
                # Process recycling
                if dry_run:
                    self.simulate_recycling(recycling_service, batch_size)
                else:
                    results = recycling_service.process_campaign_recycling(batch_size)
                    campaign_total = sum(results.values())
                    total_recycled += campaign_total
                    campaigns_processed += 1
                    
                    self.show_recycling_results(campaign, results, campaign_total)

            # Summary
            if not stats_only:
                if dry_run:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"\nDry run completed. {len(campaigns)} campaigns would be processed."
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"\nLead recycling completed. "
                            f"Total recycled: {total_recycled} across {campaigns_processed} campaigns."
                        )
                    )

        except Exception as e:
            raise CommandError(f'Error during lead recycling: {str(e)}')

    def get_campaigns(self, campaign_id, campaign_name):
        """Get campaigns based on command arguments."""
        if campaign_id:
            return Campaign.objects.filter(id=campaign_id)
        elif campaign_name:
            return Campaign.objects.filter(name=campaign_name)
        else:
            return Campaign.objects.filter(status='active', recycle_inactive_leads=True)

    def show_campaign_stats(self, campaign, stats):
        """Display campaign recycling statistics."""
        self.stdout.write("  Recycling Statistics:")
        for status, count in stats.items():
            if count > 0:
                self.stdout.write(f"    {status}: {count} leads")
        
        total = sum(stats.values())
        if total == 0:
            self.stdout.write("    No leads available for recycling")

    def simulate_recycling(self, recycling_service, batch_size):
        """Simulate recycling without making changes."""
        recycle_rules = {
            'no_answer': recycling_service.campaign.recycle_no_answer_days,
            'busy': recycling_service.campaign.recycle_busy_days,
            'disconnected': recycling_service.campaign.recycle_disconnected_days,
        }
        
        total_would_recycle = 0
        self.stdout.write("  Would recycle:")
        
        for status, days_threshold in recycle_rules.items():
            leads = recycling_service.get_recyclable_leads(status, days_threshold, batch_size)
            count = len(leads)
            total_would_recycle += count
            
            if count > 0:
                self.stdout.write(f"    {status}: {count} leads")
        
        if total_would_recycle == 0:
            self.stdout.write("    No leads would be recycled")
        else:
            self.stdout.write(f"  Total: {total_would_recycle} leads")

    def show_recycling_results(self, campaign, results, total):
        """Display recycling results."""
        if total > 0:
            self.stdout.write(
                self.style.SUCCESS(f"  Recycled {total} leads:")
            )
            for status, count in results.items():
                if count > 0:
                    self.stdout.write(f"    {status}: {count}")
        else:
            self.stdout.write("  No leads were recycled")
