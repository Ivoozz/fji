"""Database models for FixJeICT"""
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey, create_engine
from sqlalchemy.orm import relationship, sessionmaker, declarative_base
from datetime import datetime
import os

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=True)
    company = Column(String(255), nullable=True)
    forward_email = Column(String(255), nullable=True)  # Auto-generated Cloudflare alias (e.g., username@fixjeict.nl)
    role = Column(String(50), default="user")  # "user" or "admin"
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    tickets = relationship("Ticket", back_populates="user", cascade="all, delete-orphan")
    magic_links = relationship("MagicLink", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="user", cascade="all, delete-orphan")


class Ticket(Base):
    __tablename__ = "tickets"
    
    id = Column(Integer, primary_key=True, index=True)
    ticket_number = Column(String(50), unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    subject = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String(100), nullable=False)
    priority = Column(String(20), default="medium")
    status = Column(String(20), default="open")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)
    
    user = relationship("User", back_populates="tickets")
    comments = relationship("Comment", back_populates="ticket", cascade="all, delete-orphan")
    attachments = relationship("Attachment", back_populates="ticket", cascade="all, delete-orphan")


class Comment(Base):
    __tablename__ = "comments"
    
    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id"), nullable=False)
    author_type = Column(String(20), nullable=False)
    author_name = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    is_internal = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    ticket = relationship("Ticket", back_populates="comments")


class Attachment(Base):
    __tablename__ = "attachments"
    
    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    
    ticket = relationship("Ticket", back_populates="attachments")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(100), nullable=False)
    target_type = Column(String(50), nullable=True)
    target_id = Column(String(50), nullable=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="audit_logs")


class MagicLink(Base):
    __tablename__ = "magic_links"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String(255), unique=True, index=True, nullable=False)
    used = Column(Boolean, default=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="magic_links")


class AdminSession(Base):
    __tablename__ = "admin_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(255), unique=True, index=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Setting(Base):
    __tablename__ = "settings"
    
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(255), unique=True, index=True, nullable=False)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Database setup
def get_engine():
    database_url = os.getenv("DATABASE_URL", "sqlite:///data/fixjeict.db")
    return create_engine(database_url, connect_args={"check_same_thread": False} if "sqlite" in database_url else {})


def get_session_local():
    engine = get_engine()
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal


def init_db():
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
