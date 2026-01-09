from sqlalchemy import Column, Integer, JSON, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class SyncConfig(Base):
    __tablename__ = "sync_configs"
    
    id = Column(Integer, primary_key=True, index=True)
    index_id = Column(Integer, ForeignKey("indexes.id"), unique=True, nullable=False)
    confluence_spaces = Column(JSON)
    confluence_labels = Column(JSON)
    include_attachments = Column(Boolean, default=True)
    include_comments = Column(Boolean, default=False)
    interval_minutes = Column(Integer, default=60)
    enabled = Column(Boolean, default=True)

    index = relationship("Index", back_populates="sync_config")