import datetime
import base64
import requests
import os
from email.mime.text import MIMEText
from dotenv import load_dotenv

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

# Load environment variables from .env
load_dotenv()

# Google API scopes
SCOPES = [
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/gmail.send'
]

# List of calendar IDs to check
calendar_ids = [
    'primary',
    'c_classroomfff3bb29@group.calendar.google.com',
    'c_classroom50f524f6@group.calendar.google.com',
    'c_classroom2ac34bde@group.calendar.google.com',
    'c_classroomb4ccd34f@group.calendar.google.com',
    'c_classroomfa95f889@group.calendar.google.com',
    'c_classroomf30bce24@group.calendar.google.com',
    'c_classroom4c680fa3@group.calendar.google.com',
    'c_classroom7c53127b@group.calendar.google.com',
    'c_classroomd47ef506@group.calendar.google.com',
    'c_classroomab130d98@group.calendar.google.com',
    'c_classroom6dd30c61@group.calendar.google.com',
    'khurramriazf23@nutech.edu.pk'
]

def authenticate_google_services():
    creds = None
    try:
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    except Exception:
        pass

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token_file:
            token_file.write(creds.to_json())
    return creds

def get_calendar_name(service, calendar_id):
    try:
        if calendar_id == 'primary':
            return "Personal Calendar"
        calendar = service.calendars().get(calendarId=calendar_id).execute()
        return calendar.get('summary', calendar_id)
    except Exception:
        return calendar_id

def get_events(service, calendar_id, time_min, time_max):
    events_result = service.events().list(
        calendarId=calendar_id,
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    return events_result.get('items', [])

def create_summary(events_per_calendar):
    if not any(events_per_calendar.values()):
        return "No upcoming events found in the next 3 days."

    all_events = []
    for cal_info, events in events_per_calendar.items():
        calendar_name, calendar_id = cal_info
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            try:
                if 'T' in start:
                    start_dt = datetime.datetime.fromisoformat(start.replace('Z', '+00:00'))
                    start_str = start_dt.strftime('%Y-%m-%d %H:%M')
                else:
                    date_obj = datetime.datetime.strptime(start, '%Y-%m-%d')
                    start_dt = date_obj.replace(tzinfo=datetime.timezone.utc)
                    start_str = start_dt.strftime('%Y-%m-%d 00:00')

                all_events.append({
                    'datetime': start_dt,
                    'start_str': start_str,
                    'title': event.get('summary', 'No Title'),
                    'calendar_name': calendar_name
                })
            except Exception as e:
                fallback_dt = datetime.datetime.now(datetime.timezone.utc)
                all_events.append({
                    'datetime': fallback_dt,
                    'start_str': start,
                    'title': event.get('summary', 'No Title'),
                    'calendar_name': calendar_name
                })

    all_events.sort(key=lambda x: x['datetime'])

    summary_lines = []
    current_date = None
    for event in all_events:
        event_date = event['datetime'].strftime('%Y-%m-%d')
        if event_date != current_date:
            if current_date is not None:
                summary_lines.append('')
            summary_lines.append(f"Date: {event_date}")
            current_date = event_date
        summary_lines.append(f" - {event['start_str']}: {event['title']} (from {event['calendar_name']})")
    
    return '\n'.join(summary_lines)

def send_email(service, subject, body_text, to_email):
    message = MIMEText(body_text)
    message['to'] = to_email
    message['subject'] = subject

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
    body = {'raw': raw_message}
    service.users().messages().send(userId='me', body=body).execute()

def format_summary_with_gemini(summary):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is missing in .env")

    api_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

    prompt = (
        "Rewrite the following calendar events summary into a professional, clear, "
        "and nicely formatted email using PLAIN TEXT ONLY (no markdown formatting). "
        "The events are already sorted chronologically. "
        "Please format it with:\n"
        "- A friendly greeting\n"
        "- Clear date headers using simple text\n"
        "- Bullet points using simple dashes or asterisks\n"
        "- Professional and helpful tone\n"
        "- A closing signature placeholder\n"
        "- NO bold, italic, or any markdown formatting\n"
        "- Use only plain text that will display well in any email client\n\n"
        "Calendar Events Summary:\n" + summary
    )

    headers = {
        "Content-Type": "application/json"
    }

    data = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }

    response = requests.post(f"{api_url}?key={api_key}", json=data, headers=headers)
    response.raise_for_status()
    result = response.json()
    return result['candidates'][0]['content']['parts'][0]['text']

def main():
    creds = authenticate_google_services()
    calendar_service = build('calendar', 'v3', credentials=creds)
    gmail_service = build('gmail', 'v1', credentials=creds)

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    three_days_later = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=3)).isoformat()

    events_per_calendar = {}
    for cal_id in calendar_ids:
        calendar_name = get_calendar_name(calendar_service, cal_id)
        events = get_events(calendar_service, cal_id, now, three_days_later)
        events_per_calendar[(calendar_name, cal_id)] = events

    raw_summary = create_summary(events_per_calendar)
    formatted_summary = format_summary_with_gemini(raw_summary)

    to_email = os.getenv("TARGET_EMAIL")
    send_email(gmail_service, "Your 3-Day Google Calendar Summary", formatted_summary, to_email)

if __name__ == '__main__':
    main()
