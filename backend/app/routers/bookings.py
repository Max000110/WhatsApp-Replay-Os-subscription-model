from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth.service import get_current_tenant_id
from app.models.all_models import CalendarBooking, Conversation
from app.schemas.all_schemas import BookingCreate, BookingResponse
from app.services.calendar_service import calendar_service
from uuid import UUID
from typing import List

router = APIRouter(prefix="/bookings", tags=["Google Calendar Booking"])

@router.get("/slots")
def get_slots(date: str, tenant_id: UUID = Depends(get_current_tenant_id)):
    """Lists all available meeting slots for a specific date from Google Calendar"""
    return {
        "date": date,
        "slots": calendar_service.get_available_slots(date)
    }

@router.post("", response_model=BookingResponse)
def create_booking(payload: BookingCreate, tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
    """Creates a new calendar booking, syncing with Google Calendar as source of truth"""
    # 1. Sync with Google Calendar directly
    gcal_res = calendar_service.create_calendar_event(
        email=payload.customer_email,
        phone=payload.customer_phone,
        date_str=payload.booking_date,
        time_str=payload.booking_time
    )

    # 2. Store booking metadata in relational DB
    booking = CalendarBooking(
        tenant_id=tenant_id,
        booking_id=gcal_res["booking_id"],
        calendar_event_id=gcal_res["calendar_event_id"],
        customer_phone=payload.customer_phone,
        customer_email=payload.customer_email,
        booking_date=payload.booking_date,
        booking_time=payload.booking_time,
        status=gcal_res["status"]
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    # 3. If matching conversation exists, save booking references to it
    conv = db.query(Conversation).filter(
        Conversation.tenant_id == tenant_id,
        Conversation.customer_phone == payload.customer_phone
    ).first()
    if conv:
        # Save last booked meeting summary in conversation preferences or metadata
        conv.customer_preferences = f"Booked meeting on {payload.booking_date} at {payload.booking_time}"
        db.commit()

    return booking
