from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import logging
import os

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Sample available time slots (uses DD-MM-YYYY format)
available_slots = {
    "27-12-2024": ["10:00 AM", "11:00 AM", "2:00 PM", "3:45 PM"],
    "29-12-2024": ["10:00 AM", "12:00 PM", "4:00 PM"]
}

# Store booked appointments
booked_appointments = []

# Feedback link
FEEDBACK_LINK = "https://feedback-form.example.com"

# Define owner phone numbers
OWNER_PHONE_NUMBERS = ["whatsapp:+918860397260"]

# Initialize APScheduler
scheduler = BackgroundScheduler()
scheduler.start()

def format_available_slots():
    """Format available slots for display."""
    response = "Available slots:\n"
    for date, times in available_slots.items():
        response += f"{date}:\n"
        for time in times:
            response += f"  - {time}\n"
    return response if response.strip() != "Available slots:" else "No slots available."

def format_booked_appointments():
    """Format booked appointments for display."""
    if not booked_appointments:
        return "No appointments booked yet."
    response = f"Total Appointments: {len(booked_appointments)}\nBooked Appointments:\n"
    for appointment in booked_appointments:
        response += f"Date: {appointment['date']}, Time: {appointment['time']}, Phone: {appointment['phone_number']}\n"
    return response

def parse_date(input_date):
    """
    Parse the user's input date into DD-MM-YYYY format.
    Accepts various formats like "28-12-2024", "28/12/2024", "28 Dec 2024".
    """
    try:
        normalized_date = datetime.strptime(input_date.strip(), "%d-%m-%Y")
    except ValueError:
        try:
            normalized_date = datetime.strptime(input_date.strip(), "%d/%m/%Y")
        except ValueError:
            try:
                normalized_date = datetime.strptime(input_date.strip(), "%d %b %Y")
            except ValueError:
                try:
                    normalized_date = datetime.strptime(input_date.strip(), "%d %B %Y")
                except ValueError:
                    return None
    return normalized_date.strftime("%d-%m-%Y")

def send_reminder(phone_number, date, time):
    """Send a reminder message."""
    logging.info(f"Sending reminder to {phone_number} for {date} at {time}.")
    print(f"Reminder sent to {phone_number} for {date} at {time}.")

def send_feedback_link(phone_number):
    """Send a feedback link message."""
    logging.info(f"Sending feedback link to {phone_number}.")
    print(f"Feedback link sent to {phone_number}: {FEEDBACK_LINK}")

def send_owner_notification(date, time, user_phone):
    """Notify the owner about a new booking."""
    for owner in OWNER_PHONE_NUMBERS:
        logging.info(f"Sending booking notification to owner {owner}.")
        # Simulate sending notification to owner
        print(f"Notification sent to {owner}: New booking - Date: {date}, Time: {time}, User: {user_phone}.")

@app.route("/", methods=["GET"])
def home():
    return "WhatsApp Bot is running!", 200

@app.route("/whatsapp", methods=["POST"])
def whatsapp_reply():
    try:
        incoming_msg = request.values.get('Body', '').strip()
        phone_number = request.values.get('From', '').strip()
        is_owner = phone_number in OWNER_PHONE_NUMBERS  # Check if the user is an owner

        resp = MessagingResponse()
        msg = resp.message()

        if "hi" in incoming_msg.lower():
            if is_owner:
                response_text = (
                    "Hello, Admin! Here are your options:\n"
                    "1️⃣ View Booked Appointments\n"
                    "2️⃣ Update Slots\n"
                    "3️⃣ View Remaining Slots\n"
                    "4️⃣ View Report"
                )
            else:
                response_text = (
                    "Hello! Welcome to our bot. How can I assist you?\n\n"
                    "1️⃣ View Available Appointments\n"
                    "2️⃣ Book Appointment\n"
                    "To book an appointment, type 'Book [date] [time]'.\n"
                    "Example: Book 28-12-2024 10:00 AM"
                )
            msg.body(response_text)
            return str(resp)  # Ensure no additional responses are sent

        # Handle customer actions
        if not is_owner:
            # Check if the user already has a booked appointment
            existing_appointment = next((appt for appt in booked_appointments if appt["phone_number"] == phone_number), None)
            if existing_appointment:
                if incoming_msg.lower() == "end":
                    # End the appointment
                    booked_appointments.remove(existing_appointment)
                    send_feedback_link(phone_number)
                    response_text = "Your appointment has been marked as completed. Please provide your feedback using the link sent to you."
                    msg.body(response_text)
                    return str(resp)
                elif incoming_msg.lower() == "cancel":
                    # Cancel the appointment
                    booked_appointments.remove(existing_appointment)
                    response_text = f"Your appointment on {existing_appointment['date']} at {existing_appointment['time']} has been canceled."
                    msg.body(response_text)
                    return str(resp)
                else:
                    response_text = f"You already have an appointment booked on {existing_appointment['date']} at {existing_appointment['time']}. Please complete or cancel it before booking another."
                    msg.body(response_text)
                    return str(resp)

            if incoming_msg.strip() == "1":
                response_text = f"Here are the available slots:\n\n{format_available_slots()}"
                msg.body(response_text)
            elif incoming_msg.lower().startswith("book"):
                try:
                    # Parse date and time
                    parts = incoming_msg.split(maxsplit=2)
                    if len(parts) < 3:
                        raise ValueError("Incomplete booking details.")

                    input_date = parts[1].strip()
                    time = parts[2].strip()

                    # Normalize date and time
                    normalized_date = parse_date(input_date)
                    if not normalized_date:
                        response_text = "Invalid date format. Please use DD-MM-YYYY."
                        msg.body(response_text)
                        return str(resp)

                    time = time.upper().strip()

                    # Validate and confirm appointment
                    if normalized_date in available_slots and time in map(str.upper, available_slots[normalized_date]):
                        available_slots[normalized_date] = [t for t in available_slots[normalized_date] if t.upper().strip() != time]
                        booked_appointments.append({"date": normalized_date, "time": time, "phone_number": phone_number})

                        response_text = f"Your appointment is confirmed for {normalized_date} at {time}. Thank you!"
                        msg.body(response_text)

                        # Notify the owner
                        send_owner_notification(normalized_date, time, phone_number)

                        # Schedule reminder and feedback link
                        appointment_datetime = datetime.strptime(f"{normalized_date} {time}", "%d-%m-%Y %I:%M %p")
                        reminder_time = appointment_datetime - timedelta(minutes=1)
                        feedback_time = appointment_datetime + timedelta(hours=1)

                        scheduler.add_job(send_reminder, 'date', run_date=reminder_time, args=[phone_number, normalized_date, time])
                        scheduler.add_job(send_feedback_link, 'date', run_date=feedback_time, args=[phone_number])
                    elif normalized_date not in available_slots:
                        response_text = f"No slots available for {normalized_date}. Please choose another date."
                        msg.body(response_text)
                    else:
                        response_text = f"The selected time {time} is not available on {normalized_date}. Please choose from: {', '.join(available_slots.get(normalized_date, []))}."
                        msg.body(response_text)
                except (IndexError, ValueError) as e:
                    logging.error(f"Error parsing input: {e}")
                    response_text = "Invalid format. Please use the format: Book [date] [time]. Example: Book 28-12-2024 10:00 AM"
                    msg.body(response_text)

        # Handle owner actions
        if is_owner:
            if incoming_msg.strip() == "1":
                response_text = format_booked_appointments()
                msg.body(response_text)
            elif incoming_msg.lower().startswith("update"):
                try:
                    # Parse date and new slots
                    parts = incoming_msg.split(maxsplit=2)
                    if len(parts) < 3:
                        raise ValueError("Incomplete update details.")

                    input_date = parts[1].strip()
                    slots = parts[2].split(',')

                    normalized_date = parse_date(input_date)
                    if not normalized_date:
                        response_text = "Invalid date format. Please use DD-MM-YYYY."
                        msg.body(response_text)
                        return str(resp)

                    available_slots[normalized_date] = [slot.strip() for slot in slots]
                    response_text = f"Slots updated for {normalized_date}: {', '.join(available_slots[normalized_date])}"
                    msg.body(response_text)
                except ValueError as e:
                    logging.error(f"Error updating slots: {e}")
                    response_text = "Invalid format. Please use the format: Update [date] [slot1, slot2, ...]. Example: Update 28-12-2024 10:00 AM, 11:00 AM"
                    msg.body(response_text)
            elif incoming_msg.strip() == "3":
                response_text = f"Remaining slots:\n\n{format_available_slots()}"
                msg.body(response_text)
            elif incoming_msg.strip() == "4":
                response_text = format_booked_appointments()
                msg.body(response_text)

        return str(resp)

    except Exception as e:
        logging.error(f"An error occurred: {e}")
        resp = MessagingResponse()
        resp.message("An error occurred. Please try again later.")
        return str(resp)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
