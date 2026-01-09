from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.database import Base

class SyncHistory(Base):
    __tablename__ = "sync_history"
    
    id = Column(Integer, primary_key=True, index=True)
    index_id = Column(Integer, ForeignKey("indexes.id"), nullable=False)
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    status = Column(String, nullable=False, default="running")
    files_found = Column(Integer, default=0)
    files_synced = Column(Integer, default=0)
    error_message = Column(String, nullable=True)
    logs = Column(Text, nullable=True)

    index = relationship("Index", back_populates="sync_history")