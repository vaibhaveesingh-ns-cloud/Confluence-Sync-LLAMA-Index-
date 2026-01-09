from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class SyncedPage(Base):
    __tablename__ = "synced_pages"
    
    id = Column(Integer, primary_key=True)
    index_id = Column(Integer, ForeignKey("indexes.id"), nullable=False)
    confluence_page_id = Column(String, nullable=False)
    confluence_page_title = Column(String)
    confluence_version = Column(Integer, default=0)
    confluence_modified_time = Column(DateTime)
    last_synced_at = Column(DateTime)

    index = relationship("Index", back_populates="synced_pages")