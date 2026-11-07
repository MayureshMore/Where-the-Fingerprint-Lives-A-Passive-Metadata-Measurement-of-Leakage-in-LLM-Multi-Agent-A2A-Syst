"""
Alert triage workflow (IoT use case) — a short alarm from the building or plant systems, or an
occupant's request, to be prioritised and routed. Characteristic traffic: a short task input
(roughly 120–200 bytes) and short decision-style replies.

All alerts and requests are synthetic: templates with slots for invented assets, codes and rooms.
"""

from __future__ import annotations

import random

from .base import BaseWorkflow, WorkflowClass

_ALARMS = [
    "ALARM {code} {sev}: {asset} {condition}, {value} {unit} (limit {limit} {unit}) at {time}.",
    "ALERT: {asset} offline since {time}; last heartbeat {mins} min ago.",
    "WARNING {code}: {asset} {condition} for {mins} minutes in {location}.",
    "FAULT: {asset} reports {fault} at {time}; auto-restarted {n} times.",
    "ALARM {code}: {location} {condition}, {value} {unit} at {time}.",
]
_REQUESTS = [
    "Occupant request from {location}: {complaint}",
    "Room {room}: {complaint} Reported at {time}.",
    "Request via the helpdesk app, {location}: {complaint}",
]
_ASSETS = ["AHU-4", "chiller CH-1", "boiler BLR-2", "pump P-09", "cold room CR-3", "compressor AC-1",
           "conveyor CV-2", "lift L2", "generator G1", "gateway GW-07", "meter EM-12"]
_CONDITIONS = [("high temperature", "C", 31, 28), ("low pressure", "bar", 4.8, 6.0), ("high vibration", "mm/s", 7.9, 4.5),
               ("high CO2", "ppm", 1650, 1200), ("high humidity", "%", 78, 65), ("low flow", "l/min", 12, 30),
               ("high current", "A", 42, 35)]
_FAULTS = ["a communication timeout", "an overcurrent trip", "a sensor out of range", "a door left open",
           "a watchdog reset"]
_LOCATIONS = ["Building A level 3", "Building B lobby", "the server room", "the cold store", "Line 2",
              "the loading bay", "the lab wing", "the east stairwell", "meeting room 4.12"]
_COMPLAINTS = ["It is too hot, about 28 C since this morning.", "No hot water in the washroom.",
               "Loud rattling from the ceiling vent.", "Lights keep flickering.",
               "The badge reader at the side entrance rejects valid cards.", "Smell of burning near the printer room.",
               "Water is dripping from a ceiling tile.", "The lift is stuck on level 3.",
               "The room is freezing and the thermostat does nothing.", "The automatic door will not close."]
_ASKS = [
    "Triage this alert: assign a priority (P1–P4), the responsible team and the first action.",
    "Classify this event and decide whether to dispatch a technician now or schedule it.",
    "Is this urgent? Give a priority, the likely cause and who should respond.",
    "Route this to the right team and draft a one-line reply to the requester.",
    "Assess the safety risk of this alert and give a priority and response time.",
]


class AlertTriageWorkflow(BaseWorkflow):
    workflow_class = WorkflowClass.ALERT_TRIAGE
    template_pools = {"alarm templates": len(_ALARMS), "request templates": len(_REQUESTS), "asks": len(_ASKS),
                      "assets": len(_ASSETS), "conditions": len(_CONDITIONS), "faults": len(_FAULTS),
                      "locations": len(_LOCATIONS), "complaints": len(_COMPLAINTS)}

    def generate_prompt(self) -> str:
        cond, unit, value, limit = random.choice(_CONDITIONS)
        jitter = 1 + random.uniform(-0.1, 0.1)
        slots = dict(
            code=f"{random.choice('ABHT')}{random.randint(100, 999)}", sev=random.choice(["HIGH", "MEDIUM", "LOW"]),
            asset=random.choice(_ASSETS), condition=cond, unit=unit,
            value=round(value * jitter, 1), limit=limit, time=f"{random.randint(0, 23):02d}:{random.randint(0, 59):02d}",
            mins=random.randint(3, 180), location=random.choice(_LOCATIONS), fault=random.choice(_FAULTS),
            n=random.randint(1, 6), room=f"{random.randint(1, 6)}.{random.randint(1, 40):02d}",
            complaint=random.choice(_COMPLAINTS))
        event = random.choice(_REQUESTS if random.random() < 0.4 else _ALARMS).format(**slots)
        return f"{random.choice(_ASKS)}\n\n{event}"
