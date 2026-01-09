"""Background scheduler for automatic syncs"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app.database import SessionLocal
from app.models.index import Index
from app.models.sync_config import SyncConfig
from app.models.sync_history import SyncHistory
from app.services.sync_service import sync_index
import logging

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def check_and_sync_indexes():
    """
    Check all enabled indexes and sync if needed based on interval
    """
    db = SessionLocal()
    try:
        # Get all enabled sync configs
        sync_configs = db.query(SyncConfig).filter(
            SyncConfig.enabled == True
        ).all()

        for sync_config in sync_configs:
            try:
                # Get index
                index = db.query(Index).filter(
                    Index.id == sync_config.index_id
                ).first()

                if not index or not index.llamacloud_index_id:
                    continue

                # Check last sync time
                last_sync = db.query(SyncHistory).filter(
                    SyncHistory.index_id == index.id,
                    SyncHistory.status == "completed"
                ).order_by(
                    SyncHistory.completed_at.desc()
                ).first()

                # Determine if sync is needed
                should_sync = False

                if not last_sync:
                    # Never synced before
                    should_sync = True
                else:
                    # Check if enough time has passed
                    time_since_last_sync = datetime.utcnow() - last_sync.completed_at
                    interval_minutes = sync_config.interval_minutes

                    if time_since_last_sync >= timedelta(minutes=interval_minutes):
                        should_sync = True

                # Trigger sync if needed
                if should_sync:
                    logger.info(f"Auto-syncing index {index.id} ({index.name})")
                    try:
                        sync_index(db, index.user_id, index.id)
                        logger.info(f"Successfully synced index {index.id}")
                    except Exception as e:
                        logger.error(f"Failed to sync index {index.id}: {e}")

            except Exception as e:
                logger.error(f"Error processing sync config {sync_config.id}: {e}")
                continue

    finally:
        db.close()


def start_scheduler():
    """
    Start the background scheduler
    Checks for syncs every 5 minutes
    """
    scheduler.add_job(
        check_and_sync_indexes,
        trigger=IntervalTrigger(minutes=5),
        id='sync_checker',
        name='Check and sync indexes',
        replace_existing=True
    )

    scheduler.start()
    logger.info("Scheduler started")


def stop_scheduler():
    """Stop the background scheduler"""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler stopped")