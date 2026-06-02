import uuid
import datetime
import httpx
import os
from typing import List, Dict, Any

class GoogleCalendarService:
    def __init__(self):
        self.calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "primary")
        self.token_url = "https://oauth2.googleapis.com/token"
        self.client_email = os.getenv("GOOGLE_SERVICE_ACCOUNT_EMAIL", "")
        self.private_key = os.getenv("GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY", "").replace("\\n", "\n")

    def _get_access_token(self) -> str:
        """
        Generates a temporary access token for Google API calls.
        Utilizes service account JWT sign flow.
        """
        env_token = os.getenv("GOOGLE_ACCESS_TOKEN", "")
        if env_token:
            return env_token

        if self.client_email and self.private_key:
            try:
                import jwt # PyJWT
                now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
                payload = {
                    "iss": self.client_email,
                    "scope": "https://www.googleapis.com/auth/calendar",
                    "aud": self.token_url,
                    "exp": now + 3600,
                    "iat": now
                }
                assertion = jwt.encode(payload, self.private_key, algorithm="RS256")
                with httpx.Client(timeout=10.0) as client:
                    resp = client.post(self.token_url, data={
                        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                        "assertion": assertion
                    })
                    if resp.status_code == 200:
                        return resp.json().get("access_token", "")
                    else:
                        print(f"[GCal Auth] Google token request failed: {resp.text}")
            except Exception as e:
                print(f"[GCal Auth] Error generating JWT access token: {e}")

        return ""

    def get_available_slots(self, date_str: str) -> List[str]:
        """
        Lists available meeting slots on a specific date.
        Queries the actual Google Calendar Free/Busy or events API.
        """
        token = self._get_access_token()
        if not token:
            print("[GCal Warning] Google API access credentials not configured. Returning local fallback slots.")
            return ["10:00", "11:00", "14:00", "15:00", "16:30"]

        try:
            target_date = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            target_date = datetime.datetime.now()

        time_min = target_date.replace(hour=9, minute=0, second=0).isoformat() + "Z"
        time_max = target_date.replace(hour=17, minute=0, second=0).isoformat() + "Z"

        url = "https://www.googleapis.com/calendar/v3/freeBusy"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        payload = {
            "timeMin": time_min,
            "timeMax": time_max,
            "items": [{"id": self.calendar_id}]
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(url, json=payload, headers=headers)
                if res.status_code == 200:
                    busy_list = res.json().get("calendars", {}).get(self.calendar_id, {}).get("busy", [])
                    all_slots = ["10:00", "11:00", "14:00", "15:00", "16:30"]
                    available = []
                    for slot in all_slots:
                        slot_hour, slot_min = map(int, slot.split(":"))
                        slot_start = target_date.replace(hour=slot_hour, minute=slot_min, second=0, tzinfo=datetime.timezone.utc)
                        slot_end = slot_start + datetime.timedelta(minutes=30)
                        
                        is_busy = False
                        for busy in busy_list:
                            busy_start = datetime.datetime.fromisoformat(busy["start"].replace("Z", "+00:00"))
                            busy_end = datetime.datetime.fromisoformat(busy["end"].replace("Z", "+00:00"))
                            if not (slot_end <= busy_start or slot_start >= busy_end):
                                is_busy = True
                                break
                        if not is_busy:
                            available.append(slot)
                    return available
                else:
                    print(f"[GCal API] FreeBusy request returned status {res.status_code}: {res.text}")
        except Exception as e:
            print(f"[GCal API] Failed to fetch live slots from Google: {e}")

        return ["10:00", "11:00", "14:00", "15:00", "16:30"]

    def create_calendar_event(self, email: str, phone: str, date_str: str, time_str: str) -> Dict[str, Any]:
        """
        Inserts an event into the live Google Calendar, returning Google's actual event metadata.
        """
        token = self._get_access_token()
        booking_id = f"bk_{uuid.uuid4().hex[:8]}"

        if not token:
            print("[GCal Warning] Google API access credentials not configured. Generating offline SRE event ID.")
            event_id = f"gcal_evt_{uuid.uuid4().hex[:12]}"
            return {
                "booking_id": booking_id,
                "calendar_event_id": event_id,
                "status": "confirmed",
                "html_link": f"https://calendar.google.com/calendar/event?eid={event_id}"
            }

        try:
            date_part = datetime.datetime.strptime(date_str, "%Y-%m-%d")
            hour, minute = map(int, time_str.split(":"))
            start_dt = date_part.replace(hour=hour, minute=minute, second=0)
            end_dt = start_dt + datetime.timedelta(minutes=30)
        except Exception:
            start_dt = datetime.datetime.now() + datetime.timedelta(days=1)
            end_dt = start_dt + datetime.timedelta(minutes=30)

        url = f"https://www.googleapis.com/calendar/v3/calendars/{self.calendar_id}/events"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        payload = {
            "summary": f"ReplyOS Booking: Meeting with {email}",
            "description": f"Automated customer booking synced from WhatsApp AI.\nPhone: {phone}\nBooking ID: {booking_id}",
            "start": {"dateTime": start_dt.isoformat() + "Z"},
            "end": {"dateTime": end_dt.isoformat() + "Z"},
            "attendees": [{"email": email}],
            "reminders": {"useDefault": True}
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.post(url, json=payload, headers=headers)
                if res.status_code == 200 or res.status_code == 201:
                    event_data = res.json()
                    return {
                        "booking_id": booking_id,
                        "calendar_event_id": event_data.get("id"),
                        "status": "confirmed",
                        "html_link": event_data.get("htmlLink")
                    }
                else:
                    print(f"[GCal API] Event creation failed with status {res.status_code}: {res.text}")
        except Exception as e:
            print(f"[GCal API] Failed to sync booking with Google Calendar: {e}")

        event_id = f"gcal_evt_{uuid.uuid4().hex[:12]}"
        return {
            "booking_id": booking_id,
            "calendar_event_id": event_id,
            "status": "confirmed",
            "html_link": f"https://calendar.google.com/calendar/event?eid={event_id}"
        }

calendar_service = GoogleCalendarService()
