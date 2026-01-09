from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base

class Index(Base):
    __tablename__ = "indexes"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    llamacloud_index_id = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    user = relationship("User", back_populates="indexes")
    sync_config = relationship("SyncConfig", back_populates="index", uselist=False, cascade="all, delete-orphan")
    sync_history = relationship("SyncHistory", back_populates="index", cascade="all, delete-orphan")
    synced_pages = relationship("SyncedPage", back_populates="index", cascade="all, delete-orphan")