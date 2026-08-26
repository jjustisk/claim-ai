from sqlalchemy import (
    Column, Integer, String, DateTime, Date, Float, Boolean,
    ForeignKey, Text, Numeric
)
from sqlalchemy.orm import relationship
from datetime import datetime
from app.connectors.db import Base
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
    policies = relationship("Policy", back_populates="customer")
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
    customer_id = Column(Integer, ForeignKey("customer.customer_id"), nullable=False, index=True)
    policy_number = Column(String(50), unique=True, nullable=False)
    coverage_type = Column(String(100))
    start_date = Column(DateTime)
    end_date = Column(DateTime)

    customer = relationship("Customer", back_populates="policies")
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
    DRAFT = "draft"
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

    claim_type = Column(String(50))
    insurance_type = Column(String(20))
    incident_date = Column(Date)
    incident_time = Column(String(8))
    incident_location = Column(Text)
    incident_description = Column(Text)
    loss_description = Column(Text)
    estimated_value = Column(Numeric(12, 2))
    property_damaged = Column(Boolean)
    claimant_name = Column(String(100))
    claimant_email = Column(String(100))
    claimant_phone = Column(String(20))
    others_involved = Column(Boolean)
    other_party_name = Column(String(100))
    other_party_phone = Column(String(20))
    other_party_email = Column(String(100))
    other_party_address = Column(Text)
    other_party_vehicle_reg = Column(String(20))
    other_party_insurer = Column(String(100))
    police_involved = Column(Boolean)
    police_report_number = Column(String(50))
    police_station = Column(String(100))
    additional_comments = Column(Text)
    declaration_accepted = Column(Boolean, default=False)
    declaration_name = Column(String(100))
    declaration_date = Column(Date)

    holder_title = Column(String(20))
    holder_first_name = Column(String(100))
    holder_last_name = Column(String(100))
    holder_company = Column(String(150))
    holder_unit = Column(String(20))
    holder_street_number = Column(String(20))
    holder_street_name = Column(String(150))
    holder_suburb = Column(String(100))
    holder_state = Column(String(10))
    holder_postcode = Column(String(10))
    preferred_contact_method = Column(String(20))
    alternate_phone = Column(String(20))
    gst_registered = Column(Boolean)
    abn = Column(String(20))
    gst_itc_percent = Column(String(20))
    eft_account_name = Column(String(150))
    eft_bsb = Column(String(10))
    eft_account_number = Column(String(20))
    incident_street = Column(String(150))
    incident_cross_street = Column(String(150))
    incident_suburb = Column(String(100))
    incident_state = Column(String(10))
    incident_postcode = Column(String(10))
    is_policyholder = Column(Boolean)
    relationship_to_holder = Column(String(50))
    reporter_reason = Column(Text)
    witnesses_present = Column(Boolean)
    police_reported_date = Column(Date)
    charges_laid = Column(Boolean)
    charges_details = Column(Text)
    declaration_position = Column(String(100))

    customer = relationship("Customer", back_populates="claims")
    policy = relationship("Policy", back_populates="claims")
    documents = relationship("ClaimDocument", back_populates="claim")
    ai_decisions = relationship("AIDecision", back_populates="claim")
    reviews = relationship("Review", back_populates="claim")
    notifications = relationship("Notification", back_populates="claim")
    motor_detail = relationship(
        "MotorClaim", back_populates="claim", uselist=False, cascade="all, delete-orphan"
    )
    property_detail = relationship(
        "PropertyClaim", back_populates="claim", uselist=False, cascade="all, delete-orphan"
    )
    witnesses = relationship("ClaimWitness", back_populates="claim", cascade="all, delete-orphan")
    other_parties = relationship(
        "ClaimOtherParty", back_populates="claim", cascade="all, delete-orphan"
    )
    contents_items = relationship(
        "PropertyContentsItem", back_populates="claim", cascade="all, delete-orphan"
    )


class ClaimDocument(Base):
    __tablename__ = "claim_document"

    doc_id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claim.claim_id"), nullable=False)
    file_type = Column(String(50))
    file_url = Column(Text)
    upload_date = Column(DateTime, default=datetime.utcnow)

    claim = relationship("Claim", back_populates="documents")


class MotorClaim(Base):
    __tablename__ = "motor_claim"

    claim_id = Column(Integer, ForeignKey("claim.claim_id", ondelete="CASCADE"), primary_key=True)
    person_injured = Column(Boolean)
    vehicle_driven = Column(Boolean)
    policyholder_was_driver = Column(Boolean)
    driver_title = Column(String(20))
    driver_first_name = Column(String(100))
    driver_last_name = Column(String(100))
    driver_dob = Column(Date)
    driver_phone = Column(String(20))
    driver_email = Column(String(100))
    driver_licence_number = Column(String(50))
    driver_licence_years = Column(String(20))
    driver_unit = Column(String(20))
    driver_street_number = Column(String(20))
    driver_street_name = Column(String(150))
    driver_suburb = Column(String(100))
    driver_state = Column(String(10))
    driver_postcode = Column(String(10))
    alcohol_or_drugs = Column(Boolean)
    alcohol_details = Column(Text)
    vehicle_registration = Column(String(20))
    vehicle_year = Column(String(4))
    vehicle_make = Column(String(50))
    vehicle_model = Column(String(50))
    vehicle_type = Column(String(30))
    vehicle_damage_areas = Column(Text)
    vehicle_towed = Column(Boolean)
    vehicle_now_location = Column(Text)
    airbags_deployed = Column(Boolean)
    speed_over_40 = Column(Boolean)
    other_vehicle_involved = Column(Boolean)
    other_property_damaged = Column(Boolean)
    licence_cancelled_3yrs = Column(Boolean)
    cancelled_fine_defaults = Column(Boolean)
    convicted_alcohol_crime_3yrs = Column(Boolean)
    insurance_declined_5yrs = Column(Boolean)

    claim = relationship("Claim", back_populates="motor_detail")


class PropertyClaim(Base):
    __tablename__ = "property_claim"

    claim_id = Column(Integer, ForeignKey("claim.claim_id", ondelete="CASCADE"), primary_key=True)
    postal_same_as_insured = Column(Boolean)
    incident_at_insured_address = Column(Boolean)
    broker_name = Column(String(150))
    broker_phone = Column(String(20))
    notify_policyholder = Column(Boolean)
    building_damaged = Column(Boolean)
    building_areas = Column(Text)
    bathroom_rooms = Column(String(10))
    bedroom_rooms = Column(String(10))
    lounge_rooms = Column(String(10))
    damage_carpet = Column(Text)
    damage_ceiling = Column(Text)
    damage_floor = Column(Text)
    damage_wall = Column(Text)
    damage_windows = Column(Text)
    damage_other = Column(Text)
    property_secure = Column(Boolean)
    repairs_done = Column(Boolean)
    property_habitable = Column(Boolean)
    contents_affected = Column(Boolean)
    contents_total_value = Column(Numeric(12, 2))
    other_person_responsible = Column(Boolean)
    convicted_crime_5yrs = Column(Boolean)
    insurance_declined_5yrs = Column(Boolean)

    claim = relationship("Claim", back_populates="property_detail")


class ClaimWitness(Base):
    __tablename__ = "claim_witness"

    witness_id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claim.claim_id", ondelete="CASCADE"), nullable=False, index=True)
    sequence = Column(Integer, nullable=False, default=1)
    title = Column(String(20))
    first_name = Column(String(100))
    last_name = Column(String(100))
    unit = Column(String(20))
    street_number = Column(String(20))
    street_name = Column(String(150))
    suburb = Column(String(100))
    state = Column(String(10))
    postcode = Column(String(10))
    phone = Column(String(20))
    email = Column(String(100))

    claim = relationship("Claim", back_populates="witnesses")


class ClaimOtherParty(Base):
    __tablename__ = "claim_other_party"

    party_id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claim.claim_id", ondelete="CASCADE"), nullable=False, index=True)
    sequence = Column(Integer, nullable=False, default=1)
    title = Column(String(20))
    first_name = Column(String(100))
    last_name = Column(String(100))
    company_name = Column(String(150))
    unit = Column(String(20))
    street_number = Column(String(20))
    street_name = Column(String(150))
    suburb = Column(String(100))
    state = Column(String(10))
    postcode = Column(String(10))
    phone = Column(String(20))
    email = Column(String(100))
    insurance_company = Column(String(100))
    insurance_policy_number = Column(String(50))
    insurance_claim_number = Column(String(50))
    licence_number = Column(String(50))
    vehicle_registration = Column(String(20))
    vehicle_year = Column(String(4))
    vehicle_make = Column(String(50))
    vehicle_model = Column(String(50))
    vehicle_type = Column(String(30))
    vehicle_damage_areas = Column(Text)

    claim = relationship("Claim", back_populates="other_parties")


class PropertyContentsItem(Base):
    __tablename__ = "property_contents_item"

    item_id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claim.claim_id", ondelete="CASCADE"), nullable=False, index=True)
    category = Column(String(50), nullable=False)
    description = Column(Text)
    estimated_value = Column(Numeric(12, 2))

    claim = relationship("Claim", back_populates="contents_items")


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