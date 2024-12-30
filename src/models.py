# src/models.py
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    Boolean,
    Text,
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy import event
import json

Base = declarative_base()


class Tag(Base):
    __tablename__ = "tags"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    threads = relationship("ThreadTag", back_populates="tag")


class Thread(Base):
    __tablename__ = "threads"
    id = Column(Integer, primary_key=True)
    thread_id = Column(String, unique=True, nullable=False)
    tags = relationship("ThreadTag", back_populates="thread")


class ThreadTag(Base):
    __tablename__ = "thread_tags"
    id = Column(Integer, primary_key=True)
    thread_id = Column(Integer, ForeignKey("threads.id"))
    tag_id = Column(Integer, ForeignKey("tags.id"))
    thread = relationship("Thread", back_populates="tags")
    tag = relationship("Tag", back_populates="threads")


class ServerConfig(Base):
    __tablename__ = "server_configs"
    id = Column(Integer, primary_key=True)
    server_id = Column(String, unique=True, nullable=False)
    yes_emoji_id = Column(String, nullable=True)
    no_emoji_id = Column(String, nullable=True)
    yes_tag_id = Column(String, nullable=True)
    no_tag_id = Column(String, nullable=True)
    initial_tag_id = Column(String, nullable=True)
    exempt_threads = Column(MutableDict.as_mutable(Text), nullable=True)
    exempt_channels = Column(MutableDict.as_mutable(Text), nullable=True)
    enabled = Column(Boolean, default=True)
    google_credentials = Column(Text, nullable=True)
    spreadsheet_id = Column(String, nullable=True)
    forum_channel_id = Column(String, nullable=True)
    tag_mappings = Column(MutableDict.as_mutable(Text), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def set_google_credentials(self, credentials: dict):
        self.google_credentials = json.dumps(credentials)

    def get_google_credentials(self) -> dict:
        if self.google_credentials:
            return json.loads(self.google_credentials)
        return {}

    @property
    def is_configured(self) -> bool:
        return all([self.server_id, self.forum_channel_id, self.spreadsheet_id])


@event.listens_for(ServerConfig, "before_insert")
@event.listens_for(ServerConfig, "before_update")
def ensure_string_ids(mapper, connection, target):
    target.server_id = str(target.server_id) if target.server_id else None
    target.forum_channel_id = (
        str(target.forum_channel_id) if target.forum_channel_id else None
    )
