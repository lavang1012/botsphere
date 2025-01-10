from flask import Flask, request
from flask_sqlalchemy import SQLAlchemy
from twilio.twiml.messaging_response import MessagingResponse
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import logging
import os

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgres://ud3884iptels6u:p9e8ff5282a8fb1693b5ba1780a9d0a80b1050d281d6ac8c4e925541ec232fdd3@cb5ajfjosdpmil.cluster-czrs8kj4isg7.us-east-1.rds.amazonaws.com:5432/d8s96f4s2if0t9'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Define the Appointment model
class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(20), nullable=False)
    date = db.Column(db.String(20), nullable=False)
    time = db.Column(db.String(20), nullable=False)

# Define the Slot model
class Slot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(20), nullable=False)
    time = db.Column(db.String(20), nullable=False)
    is_available = db.Column(db.Boolean, default=True)

db.create_all()

# Feedback link
FEEDBACK_LINK = "https://feedback-form.example.com"

# Owner phone numbers
OWNER_PHONE_NUMBERS = ["whatsapp:+918860397260"]

# Initialize APScheduler
scheduler = BackgroundScheduler()
scheduler.start()

@app.route("/", methods=["GET"])
def home():
    return "WhatsApp Bot is running!", 200

@app.route("/whatsapp", methods=["POST"])
def whatsapp_reply():
    try:
        incoming_msg = request.values.get('Body', '').strip()
        phone_number = request.values.get('From', '').strip()
        is_owner = phone_number in OWNER_PHONE_NUMBERS

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
                slots = Slot.query.filter_by(is_available=True).all()
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
                    parts = incoming_msg.split(maxsplit=2)
                    if len(parts) < 3:
                        raise ValueError("Incomplete booking details.")

                    input_date = parts[1].strip()
                    time = parts[2].strip()

                    # Check if slot is available
                    slot = Slot.query.filter_by(date=input_date, time=time, is_available=True).first()
                    if not slot:
                        response_text = "The selected slot is already booked or unavailable. Please choose another."
                    else:
                        slot.is_available = False
                        db.session.commit()
                        new_appointment = Appointment(phone_number=phone_number, date=input_date, time=time)
                        db.session.add(new_appointment)
                        db.session.commit()

                        # Notify the owner
                        for owner in OWNER_PHONE_NUMBERS:
                            logging.info(f"New appointment booked: {input_date} at {time} by {phone_number}")

                        response_text = f"Your appointment is confirmed for {input_date} at {time}. Thank you!"

                    msg.body(response_text)
                except Exception as e:
                    logging.error(f"Error booking appointment: {e}")
                    response_text = "Invalid format. Please use the format: Book [date] [time]."
                    msg.body(response_text)
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
                    msg.body(response_text)
                except Exception as e:
                    logging.error(f"Error updating slots: {e}")
                    response_text = "Invalid format. Please use the format: Update [date] [time1, time2, ...]."
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
