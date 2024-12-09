# src/core/database/models.py
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func

Base = declarative_base()


class ExampleModel(Base):
    __tablename__ = "example_model"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    created_at = Column(DateTime, server_default=func.now())
