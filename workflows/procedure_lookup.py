"""
Procedure lookup workflow (IoT use case) — a short maintenance or operating-procedure question
from a technician. Characteristic traffic: a short task input (roughly 50–150 bytes) answered from
procedures, a lookup more than an analysis.

All questions are synthetic: templates with slots for invented assets, parts and locations.
"""

from __future__ import annotations

import random

from .base import BaseWorkflow, WorkflowClass

_TEMPLATES = [
    "What is the lockout/tagout procedure before replacing the {part} on {asset}?",
    "How often should the filters on {asset} be replaced?",
    "What torque should the {part} on {asset} be tightened to after maintenance?",
    "What are the steps to recalibrate the {sensor} sensor in {location}?",
    "Which PPE is required for {task} in {location}?",
    "How do I reset {asset} after a {fault} trip?",
    "What is the start-up sequence for {asset} after a planned shutdown?",
    "Who must sign off before {task} on {asset}?",
    "What is on the monthly inspection checklist for {asset}?",
    "How long must {asset} be isolated before {task}?",
    "Where is the isolation valve for {asset} in {location}?",
    "What is the normal operating range for the {sensor} reading on {asset}?",
    "What should be recorded in the log after {task}?",
    "Can {task} be done while {asset} is running?",
    "What is the procedure to test the emergency stop on {asset}?",
    "How do I replace the battery in the {sensor} sensor in {location}?",
    "What spare parts should be kept on site for {asset}?",
    "How do I put {asset} into maintenance mode on the building management system?",
    "What is the escalation path if {asset} fails during the night shift?",
    "What is the cleaning procedure for the {part} on {asset}?",
]
_ASSETS = ["AHU-3", "AHU-7", "chiller CH-2", "boiler BLR-1", "pump P-14", "conveyor CV-4", "compressor AC-2",
           "cold room CR-1", "packaging line PLC-5", "the rooftop unit on Building B", "the freight lift",
           "the backup generator", "the sprinkler pump", "dock door 6"]
_PARTS = ["drive belt", "bearing housing", "door seal", "inlet guide vane", "coupling", "fan motor",
          "pressure relief valve", "contactor", "heat exchanger gasket"]
_SENSORS = ["CO2", "temperature", "humidity", "differential pressure", "vibration", "flow", "level"]
_LOCATIONS = ["the plant room", "Building A level 2", "the server room", "the cold store", "Line 3",
              "the roof plant area", "the loading bay", "the lab wing"]
_TASKS = ["hot work", "a filter change", "working at height", "electrical panel work", "confined space entry",
          "a refrigerant top-up", "a firmware update"]
_FAULTS = ["high pressure", "overcurrent", "low water", "phase loss", "high temperature"]
_PREFIXES = ["", "", "Quick question: ", "From the site maintenance manual: ", "Procedure lookup: "]


class ProcedureLookupWorkflow(BaseWorkflow):
    workflow_class = WorkflowClass.PROCEDURE_LOOKUP
    template_pools = {"question templates": len(_TEMPLATES), "prefixes": len(set(_PREFIXES)),
                      "assets": len(_ASSETS), "parts": len(_PARTS), "sensors": len(_SENSORS),
                      "locations": len(_LOCATIONS), "tasks": len(_TASKS), "faults": len(_FAULTS)}

    def generate_prompt(self) -> str:
        q = random.choice(_TEMPLATES).format(
            asset=random.choice(_ASSETS), part=random.choice(_PARTS), sensor=random.choice(_SENSORS),
            location=random.choice(_LOCATIONS), task=random.choice(_TASKS), fault=random.choice(_FAULTS))
        return random.choice(_PREFIXES) + q
