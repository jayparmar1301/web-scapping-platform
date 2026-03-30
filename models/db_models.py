import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, JSON
from core.database import Base

class DBDeal(Base):
    __tablename__ = "deals"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    brand = Column(String, index=True, nullable=True)
    discountType = Column(String, nullable=True)
    discountPercent = Column(Float, index=True, nullable=True)
    price = Column(Float, index=True, nullable=True)
    originalPrice = Column(Float, nullable=True)
    category = Column(String, index=True, nullable=True)
    images = Column(JSON, nullable=True)
    platformName = Column(String, index=True)
    platformLink = Column(String, nullable=True)
    rating = Column(Float, index=True, nullable=True)
    ratingCount = Column(Integer, nullable=True)
    noCostEMI = Column(Boolean, default=False, index=True)
    affiliateUrl = Column(String, nullable=True)
    peopleViewed = Column(Integer, nullable=True)
    timeAgo = Column(String, nullable=True)
    createdAt = Column(DateTime, default=datetime.datetime.utcnow)
    updatedAt = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
