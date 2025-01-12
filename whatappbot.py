from flask import Flask, request
from flask_sqlalchemy import SQLAlchemy
from twilio.twiml.messaging_response import MessagingResponse
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from sqlalchemy import text
import logging
import os
from twilio.rest import Client
import re

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Twilio configuration
ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = "whatsapp:+14155238886"  # Twilio Sandbox Number

client = Client(ACCOUNT_SID, AUTH_TOKEN)

# Database configuration
raw_db_url = os.getenv('DATABASE_URL', 'postgresql://ud3884iptels6u:p9e8ff5282a8fb1693b5ba1780a9d0a80b1050d281d6ac8c4e925541ec232fdd3@cb5ajfjosdpmil.cluster-czrs8kj4isg7.us-east-1.rds.amazonaws.com:5432/d8s96f4s2if0t9')
if raw_db_url.startswith("postgres://"):
    raw_db_url = re.sub(r"^postgres://", "postgresql://", raw_db_url)

app.config['SQLALCHEMY_DATABASE_URI'] = raw_db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Define the Appointment model
class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(30), nullable=False)
    date = db.Column(db.String(20), nullable=False)
    time = db.Column(db.String(20), nullable=False)

# Define the Slot model
class Slot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(20), nullable=False)
    time = db.Column(db.String(20), nullable=False)
    is_available = db.Column(db.Boolean, default=True)

with app.app_context():
    try:
        db.create_all()
        logging.info("Database tables created successfully.")
    except Exception as e:
        logging.error(f"Error during database table creation: {e}")
        raise e

# Feedback link
FEEDBACK_LINK = "https://feedback-form.example.com"

# Owner phone numbers
OWNER_PHONE_NUMBERS = ["whatsapp:+918860397260"]

# Initialize APScheduler
scheduler = BackgroundScheduler()
scheduler.start()

@app.route("/", methods=["GET"])
def home():
    try:
        result = db.session.execute(text("SELECT 1")).fetchall()
        return "Database connected successfully!", 200
    except Exception as e:
        logging.error(f"Database connection error: {e}")
        return f"Database connection error: {e}", 500

@app.route("/whatsapp", methods=["POST"])
def whatsapp_reply():
    try:
        incoming_msg = request.values.get('Body', '').strip()
        phone_number = request.values.get('From', '').strip()
        is_owner = phone_number in OWNER_PHONE_NUMBERS

        logging.debug(f"Incoming message: {incoming_msg}, From: {phone_number}, Is Owner: {is_owner}")

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
            return str(resp)

        if not is_owner:
            # View available slots
            if incoming_msg.strip() == "1":
                today_date = datetime.now().strftime("%d-%m-%Y")  # Adjusted to match DB format
                try:
                    slots = Slot.query.filter(
                        Slot.date >= today_date, 
                        Slot.is_available == True
                    ).order_by(Slot.date, Slot.time).all()
                    logging.debug(f"Query Result for Slots: {slots}")
                except Exception as e:
                    logging.error(f"Error querying slots: {e}")
                    slots = []

                if not slots:
                    response_text = "No slots available."
                else:
                    response_text = "Available slots:\n" + "\n".join(
                        f"{slot.date} at {slot.time}" for slot in slots
                    )
                msg.body(response_text)
                return str(resp)

            # Book appointment
            elif incoming_msg.lower().startswith("book"):
                try:
                    # Split and validate the input
                    parts = incoming_msg.split(maxsplit=2)
                    if len(parts) < 3:
                        raise ValueError("Incomplete booking details.")

                    input_date = parts[1].strip()
                    input_time = parts[2].strip()

                    # Validate the date format
                    try:
                        datetime.strptime(input_date, "%d-%m-%Y")
                    except ValueError:
                        raise ValueError("Invalid date format. Use DD-MM-YYYY.")

                    # Validate the time format
                    try:
                        datetime.strptime(input_time, "%I:%M %p")
                    except ValueError:
                        raise ValueError("Invalid time format. Use hh:mm AM/PM.")

                    # Check if the slot exists and is available
                    slot = Slot.query.filter_by(date=input_date, time=input_time, is_available=True).first()
                    if not slot:
                        response_text = "The selected slot is already booked or unavailable. Please choose another."
                    else:
                        # Update slot and create appointment
                        slot.is_available = False
                        new_appointment = Appointment(phone_number=phone_number, date=input_date, time=input_time)
                        db.session.add(new_appointment)
                        db.session.commit()

                        # Notify owner
                        for owner in OWNER_PHONE_NUMBERS:
                            client.messages.create(
                                from_=TWILIO_PHONE_NUMBER,
                                to=owner,
                                body=f"New appointment booked: {input_date} at {input_time} by {phone_number}"
                            )

                        response_text = f"Your appointment is confirmed for {input_date} at {input_time}. Thank you!"

                    msg.body(response_text)

                except ValueError as ve:
                    logging.error(f"Validation error: {ve}")
                    msg.body(str(ve))
                except Exception as e:
                    logging.error(f"Error booking appointment: {e}")
                    msg.body("An error occurred. Please try again later.")
                return str(resp)

            # End or cancel appointment
            elif incoming_msg.lower() in ["end", "cancel"]:
                appointment = Appointment.query.filter_by(phone_number=phone_number).first()
                if not appointment:
                    response_text = "You have no active appointments to end or cancel."
                else:
                    # Mark slot as available again
                    slot = Slot.query.filter_by(date=appointment.date, time=appointment.time).first()
                    if slot:
                        slot.is_available = True

                    db.session.delete(appointment)
                    db.session.commit()

                    # Notify the owner
                    for owner in OWNER_PHONE_NUMBERS:
                        client.messages.create(
                            from_=TWILIO_PHONE_NUMBER,
                            to=owner,
                            body=f"Appointment on {appointment.date} at {appointment.time} has been canceled by {phone_number}"
                        )

                    if incoming_msg.lower() == "end":
                        response_text = f"Your appointment on {appointment.date} at {appointment.time} has been marked as completed. Please provide your feedback here: {FEEDBACK_LINK}"
                    else:
                        response_text = f"Your appointment on {appointment.date} at {appointment.time} has been canceled."

                msg.body(response_text)
                return str(resp)

        # Admin actions
        if is_owner:
            if incoming_msg.strip() == "1":
                appointments = Appointment.query.all()
                if not appointments:
                    response_text = "No appointments booked yet."
                else:
                    response_text = "Booked Appointments:\n" + "\n".join(
                        f"{appt.date} at {appt.time} - {appt.phone_number}" for appt in appointments
                    )
                msg.body(response_text)
            elif incoming_msg.lower().startswith("update"):
                try:
                    parts = incoming_msg.split(maxsplit=2)
                    if len(parts) < 3:
                        raise ValueError("Incomplete update details.")

                    input_date = parts[1].strip()
                    times = parts[2].split(',')

                    for time in times:
                        existing_slot = Slot.query.filter_by(date=input_date, time=time.strip()).first()
                        if existing_slot:
                            existing_slot.is_available = True
                        else:
                            new_slot = Slot(date=input_date, time=time.strip(), is_available=True)
                            db.session.add(new_slot)

                    db.session.commit()

                    response_text = f"Slots updated for {input_date}: {', '.join(times)}"
                except Exception as e:
                    logging.error(f"Error updating slots: {e}")
                    response_text = "Error updating slots. Please use the format: Update [date] [time1, time2, ...]"

                msg.body(response_text)
                return str(resp)

            elif incoming_msg.strip() == "3":
                today_date = datetime.now().strftime("%d-%m-%Y")  # Adjusted to match DB format
                slots = Slot.query.filter(Slot.date >= today_date, Slot.is_available == True).order_by(Slot.date, Slot.time).all()
                if not slots:
                    response_text = "No remaining slots available."
                else:
                    response_text = "Remaining Slots:\n" + "\n".join(
                        f"{slot.date} at {slot.time}" for slot in slots
                    )
                msg.body(response_text)
            elif incoming_msg.strip() == "4":
                appointments = Appointment.query.all()
                if not appointments:
                    response_text = "No appointments booked yet."
                else:
                    response_text = (
                        "Report:\n" +
                        "\n".join(
                            f"{appt.date} at {appt.time} - {appt.phone_number}" for appt in appointments
                        )
                    )
                msg.body(response_text)

        return str(resp)

    except Exception as e:
        logging.error(f"Error handling the incoming message: {e}")
        resp = MessagingResponse()
        msg = resp.message()
        msg.body("An error occurred. Please try again later.")
        return str(resp)

if __name__ == "__main__":
    app.run(debug=True)
