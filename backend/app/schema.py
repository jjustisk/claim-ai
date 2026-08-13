from sqlalchemy import (
    Column, Integer, String, DateTime, Float, Boolean, 
    ForeignKey, Text, Numeric
)
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
import enum


class Customer(Base):
    __tablename__ = "customer"

    customer_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)   
    phone = Column(String(20))
    address = Column(Text)


    claims = relationship("Claim", back_populates="customer")
    notifications = relationship("Notification", back_populates="customer")


class Assessor(Base):
    __tablename__ = "assessor"

    assessor_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)   
    role = Column(String(50))

    reviews = relationship("Review", back_populates="assessor")
    notifications = relationship("Notification", back_populates="assessor")


class Policy(Base):
    __tablename__ = "policy"

    policy_id = Column(Integer, primary_key=True, index=True)
    policy_number = Column(String(50), unique=True, nullable=False)
    coverage_type = Column(String(100))
    start_date = Column(DateTime)
    end_date = Column(DateTime)

    claims = relationship("Claim", back_populates="policy")
    pds_documents = relationship("PDSDocument", back_populates="policy")


class PDSDocument(Base):
    __tablename__ = "pds_document"

    pds_id = Column(Integer, primary_key=True, index=True)
    policy_id = Column(Integer, ForeignKey("policy.policy_id"), nullable=False)
    version = Column(String(20))
    file_url = Column(Text)
    effective_date = Column(DateTime)

    policy = relationship("Policy", back_populates="pds_documents")

class ClaimStatus(str, enum.Enum):
    """ Allowed values for the status. """
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    CLOSED = "closed"


class Claim(Base):
    __tablename__ = "claim"

    claim_id = Column(Integer, primary_key=True, index=True)
    claim_reference = Column(String(20), unique=True, nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customer.customer_id"), nullable=False)
    policy_id = Column(Integer, ForeignKey("policy.policy_id"), nullable=False)
    submission_date = Column(DateTime, default=datetime.utcnow)
    status = Column(String(50), default=ClaimStatus.SUBMITTED.value, nullable=False)
    priority_level = Column(Integer, default=0)
    fraud_risk_score = Column(Float, default=0.0)
    cost = Column(Numeric(12, 2))
    outcome_date = Column(DateTime)

    customer = relationship("Customer", back_populates="claims")
    policy = relationship("Policy", back_populates="claims")
    documents = relationship("ClaimDocument", back_populates="claim")
    ai_decisions = relationship("AIDecision", back_populates="claim")
    reviews = relationship("Review", back_populates="claim")
    notifications = relationship("Notification", back_populates="claim")


class ClaimDocument(Base):
    __tablename__ = "claim_document"

    doc_id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claim.claim_id"), nullable=False)
    file_type = Column(String(50))
    file_url = Column(Text)
    upload_date = Column(DateTime, default=datetime.utcnow)

    claim = relationship("Claim", back_populates="documents")


class AIDecision(Base):
    __tablename__ = "ai_decision"

    decision_id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claim.claim_id"), nullable=False)
    decision = Column(String(50))
    confidence_score = Column(Float)
    reason_summary = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    claim = relationship("Claim", back_populates="ai_decisions")
    audit_logs = relationship("AuditLog", back_populates="ai_decision")
    notifications = relationship("Notification", back_populates="ai_decision")


class AuditLog(Base):
    __tablename__ = "audit_log"

    log_id = Column(Integer, primary_key=True, index=True)
    decision_id = Column(Integer, ForeignKey("ai_decision.decision_id"), nullable=False)
    action_type = Column(String(50))
    description = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)

    ai_decision = relationship("AIDecision", back_populates="audit_logs")


class Review(Base):
    __tablename__ = "reviews"

    assessor_id = Column(Integer, ForeignKey("assessor.assessor_id"), primary_key=True)
    claim_id = Column(Integer, ForeignKey("claim.claim_id"), primary_key=True)
    review_date = Column(DateTime, default=datetime.utcnow)
    decision_override = Column(Boolean, default=False)
    override_reason = Column(Text)
    outcome = Column(String(50))

    assessor = relationship("Assessor", back_populates="reviews")
    claim = relationship("Claim", back_populates="reviews")


class Notification(Base):
    __tablename__ = "notification"

    notif_id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claim.claim_id"), nullable=False)
    customer_id = Column(Integer, ForeignKey("customer.customer_id"), nullable=True)
    assessor_id = Column(Integer, ForeignKey("assessor.assessor_id"), nullable=True)
    decision_id = Column(Integer, ForeignKey("ai_decision.decision_id"), nullable=True)
    type = Column(String(20))
    message = Column(Text)
    sent_at = Column(DateTime, default=datetime.utcnow)
    trigger_source = Column(String(50))

    claim = relationship("Claim", back_populates="notifications")
    customer = relationship("Customer", back_populates="notifications")
    assessor = relationship("Assessor", back_populates="notifications")
    ai_decision = relationship("AIDecision", back_populates="notifications")