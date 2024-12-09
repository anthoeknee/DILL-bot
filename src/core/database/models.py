# src/core/database/models.py
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, DateTime, Boolean, UniqueConstraint
from sqlalchemy.sql import func

Base = declarative_base()


class ExampleModel(Base):
    __tablename__ = "example_model"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    created_at = Column(DateTime, server_default=func.now())


class BotSetting(Base):
    __tablename__ = "bot_settings"
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, nullable=False)
    value = Column(String, nullable=False)


class ManagedServer(Base):
    __tablename__ = "managed_servers"
    id = Column(Integer, primary_key=True, index=True)
    server_id = Column(String, unique=True, nullable=False)
    forum_channel_id = Column(String, nullable=False)
    spreadsheet_id = Column(String, nullable=False)
    enabled = Column(Boolean, default=True)
    notification_channel_id = Column(String)
    initial_vote_tag_id = Column(String)
    added_to_list_tag_id = Column(String)
    not_in_list_tag_id = Column(String)


class ValidTag(Base):
    __tablename__ = "valid_tags"
    id = Column(Integer, primary_key=True, index=True)
    server_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    tag_type = Column(String, nullable=False)  # 'yes', 'no', or 'status'

    __table_args__ = (
        UniqueConstraint("server_id", "name", name="unique_tag_per_server"),
    )
