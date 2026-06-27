"""
Scheduler for periodic tasks
- Daily trading summaries at 8:00, 12:00, 18:00, 21:00 (configurable timezone)
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable, Dict, Any
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

logger = logging.getLogger(__name__)

# Default timezone - Beijing (UTC+8)
DEFAULT_TIMEZONE = 'Asia/Shanghai'


class TradingScheduler:
    """
    Scheduler for periodic trading tasks
    Supports configurable timezone (default: Beijing UTC+8)
    """
    
    def __init__(self, timezone_str: str = DEFAULT_TIMEZONE):
        self.timezone_str = timezone_str
        self.tz = pytz.timezone(timezone_str)
        self.scheduler = AsyncIOScheduler(timezone=self.tz)
        self._summary_callback: Optional[Callable] = None
        self._get_states_callback: Optional[Callable] = None
        
        # Schedule times (in local timezone)
        self.schedule_times = [
            (8, 0, "Morning report"),
            (12, 0, "Midday report"),
            (18, 0, "Evening report"),
            (21, 0, "Night report"),
        ]
    
    def set_callbacks(self, summary_callback: Callable, get_states_callback: Callable):
        """Set the callbacks for sending summaries"""
        self._summary_callback = summary_callback
        self._get_states_callback = get_states_callback
    
    def set_timezone(self, timezone_str: str) -> bool:
        """Change the timezone for scheduled tasks"""
        try:
            self.tz = pytz.timezone(timezone_str)
            self.timezone_str = timezone_str
            
            # Restart scheduler with new timezone
            if self.scheduler.running:
                self.stop()
                self.scheduler = AsyncIOScheduler(timezone=self.tz)
                self.start()
            
            logger.info(f"Timezone changed to {timezone_str}")
            return True
        except Exception as e:
            logger.error(f"Invalid timezone: {e}")
            return False
    
    async def _send_scheduled_summary(self):
        """Send scheduled trading summary"""
        if not self._summary_callback or not self._get_states_callback:
            logger.warning("Scheduler callbacks not set")
            return
        
        try:
            now = datetime.now(self.tz)
            logger.info(f"Sending scheduled summary at {now.strftime('%H:%M %Z')}")
            
            # Get current states
            states = self._get_states_callback()
            
            # Send summary with timezone info
            await self._summary_callback(states, self.timezone_str)
            
            logger.info("Scheduled summary sent successfully")
        except Exception as e:
            logger.error(f"Failed to send scheduled summary: {e}")
    
    def start(self):
        """Start the scheduler with daily summary jobs"""
        # Clear existing jobs
        self.scheduler.remove_all_jobs()
        
        # Schedule summaries at configured times in local timezone
        for hour, minute, description in self.schedule_times:
            self.scheduler.add_job(
                self._send_scheduled_summary,
                CronTrigger(hour=hour, minute=minute, timezone=self.tz),
                id=f'summary_{hour:02d}{minute:02d}',
                replace_existing=True
            )
            logger.info(f"Scheduled '{description}' at {hour:02d}:{minute:02d} {self.timezone_str}")
        
        if not self.scheduler.running:
            self.scheduler.start()
        logger.info(f"Trading scheduler started (timezone: {self.timezone_str})")
    
    def stop(self):
        """Stop the scheduler"""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Trading scheduler stopped")
    
    def get_next_run_times(self) -> list:
        """Get next scheduled run times"""
        jobs = self.scheduler.get_jobs()
        result = []
        for job in jobs:
            if job.next_run_time:
                # Convert to local timezone for display
                local_time = job.next_run_time.astimezone(self.tz)
                utc_time = job.next_run_time.astimezone(pytz.UTC)
                result.append({
                    "job_id": job.id,
                    "next_run_local": local_time.strftime("%Y-%m-%d %H:%M:%S %Z"),
                    "next_run_utc": utc_time.strftime("%Y-%m-%d %H:%M:%S UTC")
                })
        return result
    
    def get_schedule_info(self) -> Dict[str, Any]:
        """Get full schedule information"""
        now_local = datetime.now(self.tz)
        now_utc = datetime.now(pytz.UTC)
        
        return {
            "timezone": self.timezone_str,
            "current_time_local": now_local.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "current_time_utc": now_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "schedule": [
                {
                    "time_local": f"{hour:02d}:{minute:02d}",
                    "description": description
                }
                for hour, minute, description in self.schedule_times
            ],
            "next_runs": self.get_next_run_times()
        }


# Global instance with Beijing timezone
trading_scheduler = TradingScheduler(DEFAULT_TIMEZONE)
