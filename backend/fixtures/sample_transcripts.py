# Sample transcripts and expected structured JSON for testing

SAMPLE_CHECKIN_TRANSCRIPT = """
Agent: Hi Mike, this is Dispatch checking on load 7891-B. Can you give me an update on your status?
Driver: Hey, I'm driving, I'm on I-10 near Indio, CA. I should arrive tomorrow around 8:00 AM.
Agent: Great, thanks. Any delays?
Driver: No delays.
Agent: Thanks, talk soon.
"""

EXPECTED_CHECKIN_SUMMARY = {
  "call_outcome": "In-Transit Update",
  "driver_status": "Driving",
  "current_location": "I-10 near Indio, CA",
  "eta": "Tomorrow, 8:00 AM",
  "emergency_type": None,
  "emergency_location": None,
  "escalation_status": None,
  "extraction_notes": "Clear in-transit update."
}

SAMPLE_EMERGENCY_TRANSCRIPT = """
Agent: Hi Mike, can you give me an update on load 7891-B?
Driver: I just had a blowout, I'm pulling over on I-15 North at mile marker 123.
Agent: Are you injured? We will have a human dispatcher call you back right now.
Driver: No injuries but my truck's blocking the shoulder.
"""

EXPECTED_EMERGENCY_SUMMARY = {
  "call_outcome": "Emergency Detected",
  "driver_status": None,
  "current_location": None,
  "eta": None,
  "emergency_type": "Breakdown",
  "emergency_location": "I-15 North, Mile Marker 123",
  "escalation_status": "Escalation Flagged",
  "extraction_notes": "Driver reported blowout and pulled over, no injuries."
}
