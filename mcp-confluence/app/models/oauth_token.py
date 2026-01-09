from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class ConfluenceOAuthToken(Base):
    __tablename__ = "confluence_oauth_tokens"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    access_token = Column(String, nullable=False)
    refresh_token = Column(String, nullable=False)
    cloud_id = Column(String, nullable=True)
    expires_at = Column(DateTime)
    scopes = Column(String)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    user = relationship("User", back_populates="oauth_token")