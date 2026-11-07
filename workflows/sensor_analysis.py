"""
Sensor analysis workflow (IoT use case) — a window of equipment telemetry analysed for
anomalies, trends and threshold breaches. Characteristic traffic: a long task input (a CSV
window, several hundred to several thousand bytes) and analysis-heavy specialist replies.

All telemetry is synthetic: invented sites and assets, values drawn around a nominal operating
point, with one injected anomaly (spike, drift, step, stuck value or dropout) in most windows.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from .base import BaseWorkflow, WorkflowClass

# kind: (description, asset prefix, columns: (name, nominal, noise, decimals))
_KINDS = {
    "ahu": ("air handling unit, supply air", "AHU",
            [("supply_temp_c", 13.5, 0.4, 1), ("setpoint_c", 13.0, 0.0, 1), ("return_temp_c", 22.5, 0.5, 1),
             ("fan_pct", 62, 4, 0)]),
    "chiller": ("chiller plant", "CH",
                [("chw_supply_c", 6.7, 0.2, 1), ("chw_return_c", 12.1, 0.4, 1), ("load_pct", 58, 6, 0),
                 ("kw", 182, 12, 1)]),
    "motor": ("pump motor vibration", "M",
              [("rms_velocity_mm_s", 2.1, 0.3, 2), ("peak_accel_g", 0.8, 0.1, 2), ("dominant_hz", 24.8, 0.3, 1),
               ("bearing_temp_c", 48, 1.5, 1)]),
    "conveyor": ("conveyor drive", "CV",
                 [("speed_m_min", 32.0, 0.6, 1), ("current_a", 14.2, 0.8, 1), ("torque_pct", 41, 3, 0),
                  ("vib_mm_s", 1.6, 0.2, 2)]),
    "meter": ("floor energy meter", "EM",
              [("kw", 96, 9, 1), ("kvar", 31, 4, 1), ("power_factor", 0.94, 0.01, 2), ("thd_pct", 3.2, 0.4, 1)]),
    "cold_room": ("cold room", "CR",
                  [("air_temp_c", 3.2, 0.3, 1), ("rh_pct", 82, 3, 0), ("door_open", 0, 0, 0),
                   ("compressor_on", 1, 0, 0)]),
    "compressor": ("compressed air", "AC",
                   [("pressure_bar", 7.1, 0.1, 2), ("flow_m3_min", 11.4, 0.9, 1), ("kw", 68, 4, 1),
                    ("dewpoint_c", 3.5, 0.4, 1)]),
    "zone": ("zone air quality", "Z",
             [("co2_ppm", 640, 60, 0), ("occupancy", 18, 5, 0), ("temp_c", 22.1, 0.4, 1), ("damper_pct", 35, 5, 0)]),
}
_SITES = ["Building A", "Building B", "Building C", "Building D", "Plant 1", "Plant 2", "Plant 3",
          "Warehouse North", "Warehouse South", "Lab Wing"]
_INTERVALS = [("10 s", 10), ("30 s", 30), ("1 min", 60), ("5 min", 300), ("15 min", 900)]
_ANOMALIES = ["none", "spike", "drift", "step", "stuck", "dropout"]

_ASKS = [
    "Analyse this sensor telemetry window. Identify anomalies, trends and threshold breaches, and say "
    "whether maintenance is needed.",
    "Review the telemetry below for faults or abnormal behaviour. Summarise the operating state and flag "
    "any readings that need attention.",
    "Check this data for sensor drift, spikes or stuck values. Estimate when each anomaly started and how "
    "severe it is.",
    "Compare the readings against normal operating ranges for this equipment and recommend actions for "
    "the operations team.",
    "Summarise this telemetry for the shift report: averages, extremes, notable events, and any alarms "
    "that should have fired.",
    "Is this equipment operating efficiently? Use the telemetry to identify waste or degradation and "
    "estimate its impact.",
]


def _window(columns: list, rows: int, anomaly: str) -> list[list]:
    target = random.randrange(len(columns))
    start = random.randint(rows // 4, max(rows // 4, rows - 3))
    values = []
    for r in range(rows):
        row = []
        for c, (_, nominal, noise, dec) in enumerate(columns):
            v = random.gauss(nominal, noise) if noise else nominal
            if c == target and r >= start and anomaly != "none":
                span = max(abs(nominal) * 0.25, noise * 6, 1)
                if anomaly == "spike" and r - start < 2:
                    v += span * random.choice([1, -1]) * 1.5
                elif anomaly == "drift":
                    v += span * (r - start) / max(rows - start, 1)
                elif anomaly == "step":
                    v += span * random.choice([1, -1])
                elif anomaly == "stuck":
                    v = values[start - 1][c] if start and values[start - 1][c] != "" else nominal
                elif anomaly == "dropout" and r - start < 4:
                    v = ""
            row.append(v if v == "" else round(v, dec) if dec else int(round(v)))
        values.append(row)
    return values


class SensorAnalysisWorkflow(BaseWorkflow):
    workflow_class = WorkflowClass.SENSOR_ANALYSIS
    template_pools = {"equipment kinds": len(_KINDS), "asks": len(_ASKS), "sites": len(_SITES),
                      "sample intervals": len(_INTERVALS), "anomaly patterns": len(_ANOMALIES)}

    def generate_prompt(self) -> str:
        kind = random.choice(sorted(_KINDS))
        desc, prefix, columns = _KINDS[kind]
        asset = f"{prefix}-{random.randint(1, 40):02d}"
        site = random.choice(_SITES)
        label, step = random.choice(_INTERVALS)
        rows = random.randint(8, 110)
        anomaly = random.choice(_ANOMALIES)
        t0 = datetime(2026, random.randint(1, 12), random.randint(1, 28), random.randint(0, 23),
                      random.choice([0, 15, 30, 45]))
        lines = ["timestamp,asset," + ",".join(c[0] for c in columns)]
        for r, row in enumerate(_window(columns, rows, anomaly)):
            ts = (t0 + timedelta(seconds=r * step)).isoformat()
            lines.append(f"{ts},{asset}," + ",".join(str(v) for v in row))
        head = (f"SITE: {site}, asset {asset} ({desc})\n"
                f"WINDOW: {rows} samples at {label} intervals\n")
        return f"{random.choice(_ASKS)}\n\n{head}\n" + "\n".join(lines)
