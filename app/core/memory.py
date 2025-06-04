from sqlalchemy import create_engine, Column, Integer, String, JSON, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os
from typing import Optional, Dict, Any

# Initialize SQLAlchemy
Base = declarative_base()

class ProcessingRecord(Base):
    """Model for storing processing records"""
    __tablename__ = "processing_records"

    id = Column(Integer, primary_key=True)
    process_id = Column(String(36), unique=True, index=True)
    input_type = Column(String(50))  # email, json, pdf
    input_metadata = Column(JSON)
    classification = Column(JSON)
    agent_output = Column(JSON)
    actions_triggered = Column(JSON)
    status = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    error = Column(Text, nullable=True)

class MemoryManager:
    """Manages shared memory operations"""
    
    def __init__(self):
        # Use SQLite for development, can be changed to PostgreSQL for production
        db_url = os.getenv("DATABASE_URL", "sqlite:///./flowbit.db")
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def create_record(self, process_id: str, input_type: str, metadata: Dict[str, Any]) -> ProcessingRecord:
        """Create a new processing record"""
        session = self.Session()
        try:
            record = ProcessingRecord(
                process_id=process_id,
                input_type=input_type,
                input_metadata=metadata,
                status="pending"
            )
            session.add(record)
            session.commit()
            return record
        finally:
            session.close()

    def update_record(self, process_id: str, updates: Dict[str, Any]) -> Optional[ProcessingRecord]:
        """Update an existing processing record"""
        session = self.Session()
        try:
            record = session.query(ProcessingRecord).filter_by(process_id=process_id).first()
            if record:
                for key, value in updates.items():
                    setattr(record, key, value)
                session.commit()
                return record
            return None
        finally:
            session.close()

    def get_record(self, process_id: str) -> Optional[ProcessingRecord]:
        """Retrieve a processing record by ID"""
        session = self.Session()
        try:
            return session.query(ProcessingRecord).filter_by(process_id=process_id).first()
        finally:
            session.close()

    def get_history(self, limit: int = 100) -> list:
        """Retrieve processing history"""
        session = self.Session()
        try:
            return session.query(ProcessingRecord).order_by(
                ProcessingRecord.created_at.desc()
            ).limit(limit).all()
        finally:
            session.close()

# Initialize memory manager
memory_manager = MemoryManager() 