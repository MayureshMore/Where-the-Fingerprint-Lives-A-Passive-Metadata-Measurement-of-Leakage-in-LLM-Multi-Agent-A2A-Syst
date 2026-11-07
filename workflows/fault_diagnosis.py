"""
Fault diagnosis workflow (IoT use case) — a device fault diagnosed from its log and a
configuration excerpt. Characteristic traffic: the longest task inputs of the IoT set (a log
timeline plus a config file, roughly 2–6 KB) and reasoning-heavy specialist replies.

All logs and configurations are synthetic: invented devices, sites and values. Each device kind
has a few fault scenarios; a scenario contributes its warning and error lines to a timeline of
routine lines, and the config excerpt carries the setting the fault involves.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from .base import BaseWorkflow, WorkflowClass

# kind: (description, name prefix, routine log lines, {scenario: (symptom, fault lines)}, config builder)
_ROUTINE = {
    "controller": ["BACnet COV notification sent for AV-{n}", "Schedule {s} applied: occupied mode",
                   "PID loop SAT-{n} output {p}%", "Trend log TL-{n} flushed ({k} records)",
                   "Heartbeat to supervisor ok (rtt {r} ms)"],
    "plc": ["Scan cycle {r} ms", "Modbus TCP poll ok: slave {n}, {k} registers", "Recipe {s} loaded",
            "IO module slot {n} status ok", "Counter C{n} = {k}"],
    "vfd": ["Run command from fieldbus", "Output frequency {p}.{n} Hz", "Motor current {r}.{n} A",
            "DC bus {k} V", "Heatsink temperature {p} C"],
    "gateway": ["MQTT publish ok: site/{s}/telemetry ({k} msgs)", "Buffer usage {p}%",
                "TLS session resumed with broker", "Modbus RTU poll ok: unit {n}", "NTP sync ok (offset {r} ms)"],
    "access": ["Door D{n} unlocked by schedule {s}", "Card read ok at reader R{n}", "Door D{n} closed",
               "Sync with access server ok ({k} cards)", "Tamper input normal on R{n}"],
    "boiler": ["Burner on, firing rate {p}%", "Flow temperature {p} C", "Flame signal {r} uA",
               "Purge complete", "Pump P{n} running"],
}
_FAULTS = {
    "controller": {
        "sensor_failure": ("supply air temperature reading jumps between -40 C and 85 C",
                           ["AI-{n} value out of range (-40.0)", "AI-{n} value out of range (85.0)",
                            "PID loop SAT-{n} forced to manual: input fault", "Alarm AL-{n}: SAT sensor fault"]),
        "comm_loss": ("controller drops off the supervisor several times an hour",
                      ["Heartbeat to supervisor timed out (3000 ms)", "MS/TP token lost, re-initialising",
                       "Duplicate device instance {k} detected on network", "Supervisor link down"]),
        "schedule": ("zone stays in unoccupied mode during working hours",
                     ["Schedule {s} skipped: calendar exception active", "Occupancy override ignored",
                      "Time source mismatch: local clock {r} min behind"]),
    },
    "plc": {
        "watchdog": ("line stops with a CPU fault every few hours",
                     ["Scan cycle {k} ms exceeds watchdog 150 ms", "CPU entered STOP: watchdog",
                      "Restart by operator", "Task T{n} overrun"]),
        "io_fault": ("one station ignores start commands",
                     ["IO module slot {n} status: no response", "Output Q{n}.{r} forced off: module fault",
                      "Station {n} interlock open"]),
        "modbus": ("tank level shows stale values on the HMI",
                   ["Modbus TCP poll timeout: slave {n}", "Register {k} read error: exception 0x0B",
                    "Using last good value for LT-{n}"]),
    },
    "vfd": {
        "overcurrent": ("pump drive trips on start",
                        ["F0001 overcurrent during acceleration", "Motor current {k} A exceeds limit",
                         "Drive tripped, waiting for reset"]),
        "overvoltage": ("drive trips when the pump stops",
                        ["F0002 DC bus overvoltage during deceleration", "DC bus {k} V", "Drive tripped"]),
        "overheat": ("drive derates in the afternoon",
                     ["A0504 heatsink temperature high", "Output current limited to {p}%",
                      "Cooling fan speed low"]),
    },
    "gateway": {
        "cert_expiry": ("no telemetry reaches the cloud dashboard since this morning",
                        ["TLS handshake failed: certificate expired", "MQTT connect refused (rc=5)",
                         "Buffer usage {p}%", "Dropping oldest messages"]),
        "buffer_full": ("telemetry arrives in bursts with gaps",
                        ["Buffer usage 98%", "Publish rate limited by broker", "Dropping {k} messages"]),
        "rtu_timeout": ("meter readings missing for one floor",
                        ["Modbus RTU timeout: unit {n}", "CRC error on serial port", "Unit {n} marked offline"]),
    },
    "access": {
        "reader_offline": ("badge reader at a side entrance rejects valid cards",
                           ["Reader R{n} offline", "Card read rejected at R{n}: no database",
                            "Sync with access server failed"]),
        "door_forced": ("door forced alarms several times a night",
                        ["Door D{n} forced open", "Door D{n} held open {k} s", "Door contact D{n} chatter"]),
        "clock_drift": ("schedule unlocks doors an hour late",
                        ["Schedule {s} applied late", "Clock offset {r} min", "NTP unreachable"]),
    },
    "boiler": {
        "flame_failure": ("boiler locks out during morning start-up",
                          ["Flame signal low ({r} uA)", "Ignition failure, retry {n}", "Lockout L{n}: flame failure"]),
        "low_flow": ("boiler cycles on and off rapidly",
                     ["Flow switch open", "Flow temperature {k} C rising fast", "High limit trip"]),
        "pump_fault": ("radiators cold on upper floors",
                       ["Pump P{n} feedback missing", "Pump P{n} overload trip", "Differential pressure low"]),
    },
}
_KIND_INFO = {
    "controller": ("building automation controller", "BAC"),
    "plc": ("packaging line PLC", "PLC"),
    "vfd": ("pump variable frequency drive", "VFD"),
    "gateway": ("IoT edge gateway (MQTT bridge)", "GW"),
    "access": ("access control panel", "ACP"),
    "boiler": ("boiler controller", "BLR"),
}
_SITES = ["Building A", "Building B", "Building C", "Plant 1", "Plant 2", "Plant 3", "Warehouse North",
          "Lab Wing", "Data Hall 2", "Parking Structure"]

_ASKS = [
    "Diagnose this device fault from the log and configuration excerpt. Give the most likely root cause, the "
    "evidence for it, and the fix.",
    "The device below keeps faulting. Identify the root cause, rank alternative explanations, and list the "
    "checks a technician should do on site.",
    "Use the log and config to decide whether this is a hardware, configuration or network fault, and "
    "propose a corrective action plan.",
    "Write a fault analysis for the maintenance ticket: symptoms, timeline, root cause, and the configuration "
    "change or part replacement needed.",
    "Explain what failed and why, using the log timeline and the configuration below. Say whether it is "
    "safe to restart the device.",
]


def _fill(line: str) -> str:
    return line.format(n=random.randint(1, 24), k=random.randint(120, 9800), p=random.randint(5, 99),
                       r=random.randint(2, 480), s=random.choice(["WEEKDAY", "WEEKEND", "HOLIDAY", "NIGHT"]))


def _config(kind: str) -> tuple[str, list[str]]:
    r = random.randint
    if kind == "controller":
        return "controller.ini", [
            "[network]", f"device_instance = {r(1000, 9999)}", f"mstp_mac = {r(1, 127)}",
            f"baud = {random.choice([38400, 76800])}", "[points]", f"AI-{r(1, 24)}.type = thermistor_10k",
            f"AI-{r(1, 24)}.offset = {r(-20, 20) / 10}", "[pid.SAT]", f"kp = {r(5, 40) / 10}",
            f"ti_s = {r(60, 600)}", f"setpoint_c = {r(120, 160) / 10}", "[schedule]",
            f"occupied = 0{r(6, 8)}:00-{r(17, 20)}:00", f"timezone = UTC{random.choice(['+0', '+1', '-5', '-8'])}"]
    if kind == "plc":
        return "plc_project.cfg", [
            f"cpu.watchdog_ms = {random.choice([100, 150, 200])}", f"task.T1.cycle_ms = {r(10, 50)}",
            f"task.T2.cycle_ms = {r(50, 200)}", f"modbus.slave.{r(1, 9)}.ip = 10.20.{r(0, 9)}.{r(10, 99)}",
            f"modbus.timeout_ms = {random.choice([200, 500, 1000])}", f"modbus.retries = {r(0, 3)}",
            f"io.slot{r(1, 8)}.type = DO16", f"io.slot{r(1, 8)}.type = AI8",
            f"recipe.default = R{r(1, 20):02d}", f"interlock.station{r(1, 6)} = enabled"]
    if kind == "vfd":
        return "drive_parameters.txt", [
            f"P0304 motor_voltage = {random.choice([400, 415, 460])} V", f"P0305 motor_current = {r(80, 300) / 10} A",
            f"P0307 motor_power = {random.choice([5.5, 7.5, 11, 15, 22])} kW", f"P1120 ramp_up_time = {r(1, 30)} s",
            f"P1121 ramp_down_time = {r(1, 30)} s", f"P0640 current_limit = {r(110, 160)} %",
            f"P1240 vdc_max_controller = {random.choice(['on', 'off'])}", f"P1082 max_frequency = {r(45, 60)} Hz",
            f"P0290 overload_reaction = {r(0, 3)}"]
    if kind == "gateway":
        return "gateway.yaml", [
            "mqtt:", f"  broker: mqtts://broker.site{r(1, 9)}.example.internal:8883", f"  qos: {r(0, 2)}",
            f"  keepalive_s: {random.choice([30, 60, 120])}",
            f"  client_cert: /etc/gw/certs/gw-{r(100, 999)}.pem", f"  cert_not_after: 2026-{r(1, 12):02d}-{r(1, 28):02d}",
            "buffer:", f"  max_messages: {random.choice([5000, 10000, 50000])}", "modbus_rtu:",
            f"  port: /dev/ttyS{r(0, 3)}", f"  baud: {random.choice([9600, 19200])}",
            f"  timeout_ms: {random.choice([100, 250, 500])}", f"  units: [{', '.join(str(r(1, 30)) for _ in range(4))}]"]
    if kind == "access":
        return "panel_config.json (excerpt)", [
            "{", f'  "panel_id": "ACP-{r(10, 99)}",', f'  "server": "10.40.{r(0, 9)}.{r(10, 99)}",',
            f'  "offline_mode": "{random.choice(["deny_all", "cache", "facility_code"])}",',
            f'  "door_held_alarm_s": {random.choice([15, 30, 60])},',
            f'  "ntp": "10.40.0.{r(1, 9)}",', f'  "schedules": ["WEEKDAY 07:00-19:00", "WEEKEND 09:00-13:00"],',
            f'  "readers": {r(2, 12)}', "}"]
    return "burner_settings.cfg", [
        f"ignition_attempts = {r(1, 3)}", f"flame_min_ua = {r(2, 6)}", f"purge_time_s = {r(30, 90)}",
        f"flow_temp_setpoint_c = {r(60, 82)}", f"high_limit_c = {r(85, 95)}",
        f"pump_overrun_s = {r(60, 300)}", f"min_flow_lpm = {r(20, 80)}", f"modulation_min_pct = {r(15, 40)}"]


class FaultDiagnosisWorkflow(BaseWorkflow):
    workflow_class = WorkflowClass.FAULT_DIAGNOSIS
    template_pools = {"device kinds": len(_KIND_INFO), "fault scenarios": sum(len(v) for v in _FAULTS.values()),
                      "asks": len(_ASKS), "sites": len(_SITES),
                      "routine log lines": sum(len(v) for v in _ROUTINE.values())}

    def generate_prompt(self) -> str:
        kind = random.choice(sorted(_KIND_INFO))
        desc, prefix = _KIND_INFO[kind]
        scenario = random.choice(sorted(_FAULTS[kind]))
        symptom, fault_lines = _FAULTS[kind][scenario]
        name = f"{prefix}-{random.randint(1, 60):02d}"
        t = datetime(2026, random.randint(1, 12), random.randint(1, 28), random.randint(0, 20), random.randint(0, 59))
        n_lines = random.randint(30, 80)
        first_fault = random.randint(n_lines // 3, (2 * n_lines) // 3)
        log = []
        for i in range(n_lines):
            t += timedelta(seconds=random.randint(1, 240))
            if i >= first_fault and random.random() < 0.45:
                level, msg = random.choice(["WARN", "ERROR"]), _fill(random.choice(fault_lines))
            else:
                level, msg = "INFO", _fill(random.choice(_ROUTINE[kind]))
            log.append(f"{t.isoformat(sep=' ')} {level:5s} {msg}")
        cfg_name, cfg = _config(kind)
        return (f"{random.choice(_ASKS)}\n\n"
                f"DEVICE: {name}, {desc}, {random.choice(_SITES)}\n"
                f"FIRMWARE: {random.randint(1, 6)}.{random.randint(0, 12)}.{random.randint(0, 30)}\n"
                f"SYMPTOM: {symptom}\n\n"
                f"LOG (last {n_lines} lines):\n" + "\n".join(log) +
                f"\n\nCONFIG EXCERPT ({cfg_name}):\n" + "\n".join(cfg))
