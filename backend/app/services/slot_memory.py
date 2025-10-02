from typing import Dict, Any, Tuple
import os
import re


SLOT_KEYS = [
	"driver_status",
	"current_location",
	"eta",
	"emergency_type",
	"emergency_location",
]


def extract_slots(text: str) -> Dict[str, Any]:
	"""Heuristic extraction of slot values from a single user utterance.

	This is optional behavior. Disable by setting env SLOT_HEURISTICS_ENABLED=false
	to rely entirely on the LLM for extraction downstream.
	"""
	if not text:
		return {}
	if str(os.getenv("SLOT_HEURISTICS_ENABLED", "true")).lower() in ("0", "false", "no"):
		return {}
	lower_text = text.lower()
	slots: Dict[str, Any] = {}
	# Status
	for status in ["driving", "delayed", "arrived", "dispatched", "stopped", "waiting"]:
		if status in lower_text:
			slots["driver_status"] = status.capitalize()
			break
	# Emergency quick detection
	if any(k in lower_text for k in ["emergency", "accident", "crash", "injury", "medical", "breakdown", "fire"]):
		# Attempt to infer an emergency type keyword
		for e_type in ["accident", "breakdown", "medical", "fire", "other"]:
			if e_type in lower_text:
				slots["emergency_type"] = e_type.capitalize()
				break
		# Emergency location often appears with the same patterns as normal location
	# Location
	loc_match = re.search(r"(?i)\b(?:my\s+location\s+is|location\s+is|currently\s+in|in|at|near|around|by|on)\s+([A-Za-z][\w\-\s,]{2,})\b", text)
	if loc_match:
		loc = loc_match.group(1).strip().rstrip('.')
		# Simple normalization for common misspellings
		for a, b in [("moutan", "Multan"), ("mudan", "Multan"), ("muzan", "Multan"), ("muntan", "Multan"), ("lahar", "Lahore")]:
			if a.lower() in loc.lower():
				loc = b
		slots["current_location"] = loc
		# If emergency context words present, treat as emergency_location too
		if any(k in lower_text for k in ["emergency", "accident", "crash", "injury", "medical", "breakdown", "fire"]):
			slots["emergency_location"] = loc
	# ETA (times, relative durations, or markers)
	eta_digit = re.search(r"(?i)\b(\d{1,2}\s?(am|pm))\b|\b\d{1,2}:\d{2}\b", lower_text)
	eta_word = re.search(r"(?i)\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s?(am|pm)\b", lower_text)
	eta_rel  = re.search(r"(?i)\b(in\s+\d+\s+(hours?|hrs?|minutes?|mins?))\b", lower_text)
	eta_day  = re.search(r"(?i)\b(today|tonight|tomorrow)\b", lower_text)
	if eta_digit:
		slots["eta"] = eta_digit.group(0)
	elif eta_word and eta_day:
		slots["eta"] = f"{eta_day.group(0)} {eta_word.group(0)}"
	elif eta_word:
		slots["eta"] = eta_word.group(0)
	elif eta_rel:
		slots["eta"] = eta_rel.group(0)
	return slots


def get_missing_slots(current: Dict[str, Any]) -> Tuple[str, ...]:
	missing = []
	for key in SLOT_KEYS:
		val = (current or {}).get(key)
		if val is None or val == "":
			missing.append(key)
	return tuple(missing)


def build_followup_for_missing(missing: Tuple[str, ...]) -> str:
	"""Optionally return a short question for the next missing slot.

	If SLOT_TEXT_TEMPLATES_ENABLED=false, return empty string to let the LLM craft phrasing.
	"""
	if str(os.getenv("SLOT_TEXT_TEMPLATES_ENABLED", "true")).lower() in ("0", "false", "no"):
		return ""
	if not missing:
		return "Thanks. Anything else you want to add?"
	if "driver_status" in missing:
		return "Got it. What's your current status?"
	if "current_location" in missing:
		return "Thanks. Where are you right now?"
	if "eta" in missing:
		return "Noted. What's your ETA?"
	if "emergency_type" in missing:
		return "Understood. What type of emergency is it?"
	if "emergency_location" in missing:
		return "Where exactly is the emergency?"
	return "Okay, could you share a bit more?"


def polite_end_from_slots(slots: Dict[str, Any]) -> str:
	status = slots.get("driver_status")
	loc = slots.get("current_location")
	eta = slots.get("eta")
	# Allow disabling templated close text
	if str(os.getenv("SLOT_TEXT_TEMPLATES_ENABLED", "true")).lower() not in ("0", "false", "no"):
		if status and loc and eta:
			return f"Thanks for the update — status {status}, location {loc}, ETA {eta}. Drive safe."
	# Emergency closure
	etype = slots.get("emergency_type")
	eloc = slots.get("emergency_location")
	if str(os.getenv("SLOT_TEXT_TEMPLATES_ENABLED", "true")).lower() not in ("0", "false", "no"):
		if etype and eloc:
			return f"I have the emergency noted: {etype} at {eloc}. A dispatcher will call you immediately."
		return "Thanks for the details. We'll follow up if needed."
	# When templates disabled, return empty to let LLM handle closing text
	return ""


