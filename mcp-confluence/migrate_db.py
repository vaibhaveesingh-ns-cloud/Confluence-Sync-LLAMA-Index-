"""Database migration script to add agent_id to indexes table"""

from sqlalchemy import create_engine, text
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate_database():
    """Add agent_id column to indexes table if it doesn't exist"""
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./confluence_sync.db")
    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as conn:
        try:
            # Check if agent_id column exists
            result = conn.execute(text("PRAGMA table_info(indexes)"))
            columns = [row[1] for row in result]
            
            if 'agent_id' not in columns:
                logger.info("Adding agent_id column to indexes table...")
                conn.execute(text("ALTER TABLE indexes ADD COLUMN agent_id VARCHAR"))
                conn.execute(text("CREATE INDEX ix_indexes_agent_id ON indexes (agent_id)"))
                conn.commit()
                logger.info("Successfully added agent_id column")
            else:
                logger.info("agent_id column already exists")
                
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            raise


if __name__ == "__main__":
    migrate_database()
