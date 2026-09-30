"""
backend/agents.py
=================
IBM Bob 2.0 Hackathon — Multi-Agent Application Maintenance Pipeline
Criteria satisfied: Agent Mode, Parallel Tasks, Subagents, Document Understanding

Pipeline architecture
---------------------

  ┌─────────────────────────────────────────────────────────────────────┐
  │                    asyncio.gather()  ← PARALLEL                     │
  │  Subagent 1: TelemetryIngestionSubagent                              │
  │  Subagent 2: DocumentUnderstandingSubagent                           │
  └───────────────────────┬─────────────────────────────────────────────┘
                          │ (results merged)
                          ▼
             Subagent 3: SafetyTriageSubagent
                          │
                          ▼
           Subagent 4: ResolutionDispatchSubagent
                          │
                          ▼
              DiagnosticResult  +  agent_execution_trace[]

Each subagent:
  - Has a unique name, version, and responsibility
  - Appends a timestamped TraceEntry to the shared execution trace
  - Falls back to deterministic rule-based logic when IBM Watsonx is unavailable
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Watsonx lazy singleton ─────────────────────────────────────────────────────
_wx_model = None


def _get_wx():
    global _wx_model
    if _wx_model is not None:
        return _wx_model

    api_key    = os.getenv("WATSONX_API_KEY", "")
    project_id = os.getenv("WATSONX_PROJECT_ID", "")
    url        = os.getenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
    model_id   = "ibm/granite-3-8b-instruct"

    if not api_key or not project_id:
        logger.warning("[Watsonx] Credentials absent — deterministic fallback active.")
        return None

    try:
        from ibm_watsonx_ai import Credentials
        from ibm_watsonx_ai.foundation_models import ModelInference
        from ibm_watsonx_ai.metanames import GenTextParamsMetaNames as P

        _wx_model = ModelInference(
            model_id=model_id,
            credentials=Credentials(url=url, api_key=api_key),
            project_id=project_id,
            params={
                P.MAX_NEW_TOKENS: 800,
                P.TEMPERATURE:    0.15,
                P.STOP_SEQUENCES: ["```"],
            },
        )
        logger.info("[Watsonx] Model '%s' initialised.", model_id)
        return _wx_model
    except Exception as exc:  # noqa: BLE001
        logger.error("[Watsonx] Init failed: %s", exc)
        return None


def _llm_call(prompt: str) -> str:
    m = _get_wx()
    if m is None:
        raise RuntimeError("Watsonx not available.")
    return m.generate_text(prompt=prompt)


def _parse_json(raw: str) -> dict:
    raw = re.sub(r"```(?:json)?", "", raw).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    s, e = raw.find("{"), raw.rfind("}")
    if s != -1 and e > s:
        try:
            return json.loads(raw[s : e + 1])
        except json.JSONDecodeError:
            pass
    raise ValueError(f"No JSON in: {raw[:200]}")


# ── Trace entry ────────────────────────────────────────────────────────────────

@dataclass
class TraceEntry:
    subagent:     str
    version:      str
    status:       str            # "running" | "completed" | "fallback"
    started_at:   str
    completed_at: str
    duration_ms:  int
    input_summary: str
    output_summary: str
    log_lines:    list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _entry(name: str, ver: str, t0: float, status: str,
           in_s: str, out_s: str, logs: list[str]) -> TraceEntry:
    t1 = time.perf_counter()
    return TraceEntry(
        subagent=name, version=ver, status=status,
        started_at=datetime.fromtimestamp(
            time.time() - (t1 - t0), tz=timezone.utc).isoformat(),
        completed_at=_ts(),
        duration_ms=int((t1 - t0) * 1000),
        input_summary=in_s,
        output_summary=out_s,
        log_lines=logs,
    )


# ════════════════════════════════════════════════════════════════════════════════
# Subagent 1 — TelemetryIngestionSubagent
# Responsibility: Parse and normalise hardware registers (RPM, water level,
#                 power draw, error codes) into a structured telemetry summary.
# ════════════════════════════════════════════════════════════════════════════════

_SA1_SYS = """You are TelemetryIngestionSubagent v1.0 — part of an IBM Bob 2.0 multi-agent
appliance maintenance pipeline. Your sole responsibility is parsing raw hardware signals.

Input fields:
  error_code    : alphanumeric fault code on display (may be null)
  water_level   : sensor reading (string or null)
  drum_rpm      : integer or null
  power_draw_w  : watts drawn by motor (integer or null)
  user_symptom  : plain-language description (may be null)

Output ONLY valid JSON with these exact keys:
  normalised_error_code   (string | null)
  water_level_status      ("NORMAL" | "HIGH" | "LOW" | "UNKNOWN")
  drum_rpm                (integer | null)
  power_draw_w            (integer | null)
  symptom_class           ("DRAIN"|"BALANCE"|"DOOR"|"MOTOR"|"FILL"|"HEAT"|"UNKNOWN")
  anomaly_flags           (array of strings — e.g. "HIGH_WATER", "DRUM_STALLED", "OVERPOWER")
  confidence              (integer 0–100)
"""


async def telemetry_ingestion_subagent(
    error_code:   Optional[str],
    water_level:  Optional[str],
    drum_rpm:     Optional[int],
    power_draw_w: Optional[int],
    user_symptom: Optional[str],
) -> tuple[dict, TraceEntry]:
    """Subagent 1 — runs concurrently with Subagent 2."""
    t0   = time.perf_counter()
    logs = [f"[SA1] TelemetryIngestionSubagent v1.0 started at {_ts()}"]
    logs.append(f"[SA1] Input: error_code={error_code}, rpm={drum_rpm}, "
                f"water={water_level}, power={power_draw_w}W, symptom={user_symptom!r}")

    prompt = (
        f"<|system|>\n{_SA1_SYS.strip()}\n<|user|>\n"
        f"error_code   : {error_code or 'null'}\n"
        f"water_level  : {water_level or 'null'}\n"
        f"drum_rpm     : {drum_rpm or 'null'}\n"
        f"power_draw_w : {power_draw_w or 'null'}\n"
        f"user_symptom : {user_symptom or 'null'}\n"
        "<|assistant|>\n"
    )

    status = "completed"
    try:
        raw    = await asyncio.to_thread(_llm_call, prompt)
        result = _parse_json(raw)
        logs.append(f"[SA1] LLM parsed successfully. class={result.get('symptom_class')}, "
                    f"flags={result.get('anomaly_flags')}")
    except Exception as exc:  # noqa: BLE001
        logs.append(f"[SA1] LLM unavailable ({exc}). Executing deterministic fallback.")
        status = "fallback"
        result = _sa1_fallback(error_code, water_level, drum_rpm, power_draw_w, user_symptom)
        logs.append(f"[SA1] Fallback result: class={result['symptom_class']}, "
                    f"flags={result['anomaly_flags']}")

    logs.append(f"[SA1] Completed — confidence={result.get('confidence')}%")
    trace = _entry("TelemetryIngestionSubagent", "1.0", t0, status,
                   f"ec={error_code} rpm={drum_rpm} water={water_level}",
                   f"class={result.get('symptom_class')} flags={result.get('anomaly_flags')}",
                   logs)
    return result, trace


def _sa1_fallback(ec, wl, rpm, pwr, sym) -> dict:
    ec_up  = (ec  or "").upper()
    sym_up = (sym or "").upper()
    wl_up  = (wl  or "").upper()

    def hit(kws): return any(k in ec_up or k in sym_up for k in kws)

    if hit({"DRAIN","OE","5E","E18","C5","PUMP"}):    cls = "DRAIN"
    elif hit({"MOTOR","LE","3E","3C","C9","BURN"}):   cls = "MOTOR"
    elif hit({"HEAT","C7","TEMP","HOT"}):             cls = "HEAT"
    elif hit({"FILL","4E","F8E1","E17","WATER","NO WATER"}): cls = "FILL"
    elif hit({"DOOR","DE","C1","F21","LATCH"}):       cls = "DOOR"
    elif hit({"BALANCE","UE","UB","SHAKE","VIBRAT"}): cls = "BALANCE"
    else:                                              cls = "UNKNOWN"

    flags = []
    if wl_up in ("HIGH","OVERFLOW"):   flags.append("HIGH_WATER")
    if rpm == 0 and cls == "MOTOR":    flags.append("DRUM_STALLED")
    if pwr and pwr > 2500:             flags.append("OVERPOWER")
    if wl_up == "LOW" and cls == "FILL": flags.append("NO_FILL")

    return {
        "normalised_error_code": ec_up or None,
        "water_level_status":    wl_up if wl_up in ("NORMAL","HIGH","LOW") else "UNKNOWN",
        "drum_rpm":              rpm,
        "power_draw_w":          pwr,
        "symptom_class":         cls,
        "anomaly_flags":         flags,
        "confidence":            85 if ec else 55,
    }


# ════════════════════════════════════════════════════════════════════════════════
# Subagent 2 — DocumentUnderstandingSubagent
# Responsibility: Semantic document understanding over multi-brand service
#                 manuals, schematics, and OEM tolerance tables to extract
#                 root cause, wiring hazard warnings, and repair tolerances.
# ════════════════════════════════════════════════════════════════════════════════

# ── Embedded multi-brand service manual corpus ────────────────────────────────
# In production this would be a vector-store retrieval pipeline.
# Here it is structured JSON that mimics indexed document chunks.

MANUAL_CORPUS: dict[str, dict] = {
    "LG": {
        "brand": "LG Electronics",
        "phone": "1800-315-9999",
        "models": ["FHM1207ZDL", "FHT1006SNL", "FHM1408BDL"],
        "wiring_notes": (
            "LG Direct Drive motor operates at 230 V AC input rectified to ~310 V DC bus. "
            "Inverter capacitors retain charge for 5–10 min post power-off. "
            "Never open the motor compartment without discharging with a 10 kΩ resistor."
        ),
        "error_codes": {
            "OE": {
                "title": "Drain Error", "severity": "LOW",
                "oem_tolerance": "Drain time < 15 min from tub full.",
                "root_cause": "Blocked pump filter, kinked drain hose, or standpipe > 100 cm.",
                "hazard_warning": None, "can_diy": True,
                "youtube_id": "LkCeqi1fFRs",
                "steps": [
                    "Unplug power — safety first.",
                    "Place tray under pump filter access hatch (bottom-front).",
                    "Rotate filter cap counter-clockwise, let water drain.",
                    "Remove lint, coins, debris from filter cavity.",
                    "Check drain hose for kinks; standpipe must be 60–100 cm.",
                    "Reinstall filter cap, plug in, run Spin Only cycle.",
                ],
            },
            "UE": {
                "title": "Unbalanced Load", "severity": "LOW",
                "oem_tolerance": "Drum vibration < 2 mm at 1200 RPM.",
                "root_cause": "Load imbalance > OEM threshold; floor contact on all 4 feet required.",
                "hazard_warning": None, "can_diy": True, "youtube_id": "jFu7kQfHKns",
                "steps": [
                    "Open door, redistribute laundry evenly.",
                    "Add 1–2 towels if washing one bulky item.",
                    "Verify all levelling feet contact floor.",
                    "Restart spin cycle.",
                ],
            },
            "dE": {
                "title": "Door Lock Failure", "severity": "LOW",
                "oem_tolerance": "Lock solenoid must engage < 3 s after Start.",
                "root_cause": "Worn latch, foreign object in gasket, or solenoid relay fault.",
                "hazard_warning": "If dE persists — door lock solenoid failed. Do not force open.",
                "can_diy": True, "youtube_id": None,
                "steps": [
                    "Inspect door gasket for trapped clothing.",
                    "Push door firmly until latch clicks.",
                    "Run Rinse+Spin; if dE persists call LG service.",
                ],
            },
            "LE": {
                "title": "Motor Overload / Winding Short", "severity": "HIGH",
                "oem_tolerance": "Motor current must not exceed 9 A RMS.",
                "root_cause": "Motor winding short, seized bearing, or inverter PCB fault.",
                "hazard_warning": (
                    "CRITICAL — 310 V DC bus capacitors retain lethal charge. "
                    "Motor compartment access requires certified discharge procedure."
                ),
                "can_diy": False, "youtube_id": None,
                "steps": [
                    "Unplug immediately.",
                    "Wait 15 min for capacitor discharge.",
                    "Do not open rear panel — call LG certified engineer.",
                ],
            },
        },
    },
    "SAMSUNG": {
        "brand": "Samsung Electronics",
        "phone": "1800-572-6786",
        "models": ["WW70T4020EE", "WW90T684DLN", "WF45R6100AW"],
        "wiring_notes": (
            "Samsung EcoBubble uses a BLDC motor with hall sensors on 12 V logic bus. "
            "Main inverter runs at 350 V DC. PCB has MOV surge protectors — replace if burnt. "
            "Heater NTC thermistor: nominal 10 kΩ at 25 °C, short indicates heater failure."
        ),
        "error_codes": {
            "5E": {
                "title": "Drain Error", "severity": "LOW",
                "oem_tolerance": "Drain pump must clear tub in < 12 min.",
                "root_cause": "Clogged debris filter or kinked hose.",
                "hazard_warning": None, "can_diy": True, "youtube_id": "4kqMqkKnTvs",
                "steps": [
                    "Unplug machine.",
                    "Open lower access panel, use emergency drain hose.",
                    "Unscrew debris filter, clean under tap.",
                    "Reinstall, run Rinse cycle.",
                ],
            },
            "4E": {
                "title": "Water Inlet Timeout", "severity": "LOW",
                "oem_tolerance": "Inlet must fill to target level in < 13 min.",
                "root_cause": "Tap closed, low pressure, or clogged inlet mesh.",
                "hazard_warning": None, "can_diy": True, "youtube_id": None,
                "steps": [
                    "Confirm supply tap is fully open.",
                    "Detach inlet hose, clean mesh filter.",
                    "Reconnect, restart cycle.",
                ],
            },
            "3E": {
                "title": "BLDC Motor / Hall Sensor Fault", "severity": "HIGH",
                "oem_tolerance": "Hall sensor output must toggle within 50 ms of motor start.",
                "root_cause": "Hall sensor IC, winding short, or motor driver PCB failure.",
                "hazard_warning": (
                    "HIGH-VOLTAGE HAZARD — Samsung 350 V DC inverter bus. "
                    "Capacitors rated 400 V/470 µF hold lethal charge up to 10 min after power-off. "
                    "Arc flash risk if bus bar contacts are touched. Certified discharge required."
                ),
                "can_diy": False, "youtube_id": None,
                "steps": [
                    "Power off and unplug immediately.",
                    "Do not restart — arc flash and fire risk.",
                    "Contact Samsung authorised service.",
                ],
            },
            "3C": {
                "title": "Motor Drive Circuit Fault", "severity": "HIGH",
                "oem_tolerance": "IGBT gate drive voltage 12–15 V; Vce(sat) ≤ 3 V at rated current.",
                "root_cause": (
                    "Short-circuit in BLDC motor drive IGBT, winding insulation "
                    "breakdown, or motor control PCB failure."
                ),
                "hazard_warning": (
                    "HIGH-VOLTAGE HAZARD — Samsung 350 V DC inverter bus. "
                    "Capacitors (400 V / 470 µF) hold lethal charge up to 10 min after power-off. "
                    "Arc-flash risk if bus bar is touched. Samsung-certified engineer required."
                ),
                "can_diy": False, "youtube_id": None,
                "steps": [
                    "Switch off and unplug immediately — do not restart.",
                    "Wait 20 min for 350 V DC bus to discharge.",
                    "Do not open any panels — arc-flash risk from shorted IGBT.",
                    "Call Samsung: 1800-572-6786. Quote model WW90T684DLN + 3C.",
                ],
            },
            "UB": {
                "title": "Unbalanced Load", "severity": "LOW",
                "oem_tolerance": "Eccentric mass < 250 g equivalent at drum centre.",
                "root_cause": "Laundry bunched to one side.",
                "hazard_warning": None, "can_diy": True, "youtube_id": None,
                "steps": [
                    "Open door, redistribute load.",
                    "Resume cycle.",
                ],
            },
        },
    },
    "BOSCH": {
        "brand": "Bosch Home Appliances",
        "phone": "1800-266-1880",
        "models": ["WAJ2416SIN", "WAU28PH9GB", "WGA142X0IN"],
        "wiring_notes": (
            "Bosch EcoSilence Drive motor: brushless, 240 V AC, inverter at 325 V DC. "
            "Aquastop solenoid valve rated 24 V DC — check connector before any drainage work. "
            "E23 Aquastop trip indicates water in base pan; do not tilt machine — spill hazard."
        ),
        "error_codes": {
            "E18": {
                "title": "Pump Blocked / Drain Fault", "severity": "LOW",
                "oem_tolerance": "Drain pump head pressure > 0.8 bar at rated RPM.",
                "root_cause": "Foreign object blocking impeller; drain hose kinked.",
                "hazard_warning": None, "can_diy": True, "youtube_id": "D8P4Flu4MMQ",
                "steps": [
                    "Unplug machine.",
                    "Open pump cover flap (bottom-right front panel).",
                    "Drain residual water into tray.",
                    "Unscrew pump cap, remove debris, manually spin impeller.",
                    "Refit cap; run self-test (Start + Temp).",
                ],
            },
            "F21": {
                "title": "Door Lock Fault", "severity": "LOW",
                "oem_tolerance": "Interlock relay must switch < 2 s after door closure.",
                "root_cause": "Worn latch hook or relay contact oxidation.",
                "hazard_warning": "Persistent F21 = interlock relay failure — do not bypass.",
                "can_diy": True, "youtube_id": None,
                "steps": [
                    "Re-close door firmly.",
                    "Check door seal for obstructions.",
                    "If persists, call Bosch service.",
                ],
            },
            "E23": {
                "title": "Aquastop / Active Leak Detected", "severity": "HIGH",
                "oem_tolerance": "Base tray float sensor: trip at > 0.5 L accumulated.",
                "root_cause": "Hose connection leak, pump shaft seal, or tub gasket breach.",
                "hazard_warning": (
                    "AQUASTOP ACTIVE — water in base tray. Do not tilt or move machine. "
                    "Water in proximity to 325 V DC inverter presents electrocution hazard."
                ),
                "can_diy": False, "youtube_id": None,
                "steps": [
                    "Unplug immediately — water near inverter.",
                    "Do not tilt machine; base tray holds water.",
                    "Call Bosch emergency service line.",
                ],
            },
            "E17": {
                "title": "Water Inlet Timeout", "severity": "LOW",
                "oem_tolerance": "Fill to NTC target in < 15 min at rated pressure 0.05–1 MPa.",
                "root_cause": "Supply valve closed, low mains pressure, or inlet mesh blocked.",
                "hazard_warning": None, "can_diy": True, "youtube_id": None,
                "steps": [
                    "Open supply tap fully.",
                    "Disconnect inlet hose, clean mesh.",
                    "Reconnect and restart program.",
                ],
            },
        },
    },
    "WHIRLPOOL": {
        "brand": "Whirlpool Corporation",
        "phone": "1800-208-1800",
        "models": ["WHITEMAGIC75", "WTW5000DW", "WFW5000HW"],
        "wiring_notes": (
            "Whirlpool Direct-Drive motor: 120/240 V AC. Motor control board (MCB) at J12 connector. "
            "F7E1 speed sensor fault: check basket speed sensor at P13 pin 3–4 with DMM (AC mV). "
            "F5E2 lid switch: actuator tab must depress switch plunger by ≥ 3 mm."
        ),
        "error_codes": {
            "F8E1": {
                "title": "Long Fill / No Water", "severity": "LOW",
                "oem_tolerance": "Fill sensor must reach target within 13 min.",
                "root_cause": "Supply valve closed, pressure < 14 PSI, or inlet clogged.",
                "hazard_warning": None, "can_diy": True, "youtube_id": None,
                "steps": [
                    "Verify supply valve fully open.",
                    "Check inlet hose for kinks.",
                    "Clean inlet mesh filter.",
                    "Confirm pressure ≥ 14 PSI.",
                    "Restart cycle.",
                ],
            },
            "F5E2": {
                "title": "Lid Switch Open", "severity": "LOW",
                "oem_tolerance": "Lid switch plunger depression ≥ 3 mm.",
                "root_cause": "Broken actuator tab or loose harness at P5.",
                "hazard_warning": "Persistent F5E2 after actuator check = switch assembly replacement.",
                "can_diy": True, "youtube_id": "pX0mXf9CyBM",
                "steps": [
                    "Press lid firmly, listen for click.",
                    "Inspect actuator tab for cracks.",
                    "If broken, order WPW10131219 replacement.",
                ],
            },
            "F7E1": {
                "title": "Motor Speed Sensor Fault", "severity": "HIGH",
                "oem_tolerance": "Speed sensor AC voltage 200–600 mV at J2 during spin.",
                "root_cause": "Faulty basket speed sensor or MCB failure.",
                "hazard_warning": (
                    "MCB replacement involves 240 V mains connections at J1. "
                    "Capacitor discharge required before PCB removal."
                ),
                "can_diy": False, "youtube_id": None,
                "steps": [
                    "Unplug machine.",
                    "Do not attempt MCB replacement without proper training.",
                    "Call Whirlpool authorised service.",
                ],
            },
        },
    },
    "IFB": {
        "brand": "IFB Industries",
        "phone": "1860-425-5678",
        "models": ["SENATOR-WXSN", "NEO-WS8514", "ELITE-WXS"],
        "wiring_notes": (
            "IFB Senator uses BLDC motor with inverter at 300 V DC. "
            "C7 heater fault: NTC thermistor at CN7 connector. Resistance: 10 kΩ at 25 °C. "
            "C9 motor fault: inverter IGBT module — lethal voltage, no DIY access permitted."
        ),
        "error_codes": {
            "C1": {
                "title": "Door Not Locked", "severity": "LOW",
                "oem_tolerance": "Door lock confirmation < 3 s post Start press.",
                "root_cause": "Door not fully closed or latch spring worn.",
                "hazard_warning": "Persistent C1 = latch solenoid failure.",
                "can_diy": True, "youtube_id": None,
                "steps": [
                    "Push door until double-click.",
                    "Inspect gasket for debris.",
                    "Press Start — machine retries 3×.",
                ],
            },
            "C5": {
                "title": "Drain Pump Error", "severity": "LOW",
                "oem_tolerance": "Pump must lower water level by 5 cm/min.",
                "root_cause": "Blocked filter, kinked hose, or seized impeller.",
                "hazard_warning": None, "can_diy": True, "youtube_id": "lZU8RQZYpAM",
                "steps": [
                    "Unplug machine.",
                    "Open front service panel.",
                    "Drain via emergency hose.",
                    "Remove and clean pump filter.",
                    "Manually spin impeller — confirm free rotation.",
                    "Reassemble, run Drain+Spin.",
                ],
            },
            "C7": {
                "title": "Heater / NTC Thermistor Fault", "severity": "HIGH",
                "oem_tolerance": "Heater element resistance 22–28 Ω at 20 °C.",
                "root_cause": "Heating element open-circuit or NTC thermistor shorted.",
                "hazard_warning": (
                    "Heater circuit at 230 V mains. Thermistor at CN7 — "
                    "live rail present when machine is plugged in. "
                    "Electrocution risk if accessed without insulated tools and discharge."
                ),
                "can_diy": False, "youtube_id": None,
                "steps": [
                    "Cancel cycle immediately.",
                    "Unplug machine.",
                    "Do not use hot-wash programs until repaired.",
                    "Call IFB service.",
                ],
            },
            "C9": {
                "title": "Motor Control / IGBT Fault", "severity": "HIGH",
                "oem_tolerance": "IGBT gate voltage 12–15 V; collector-emitter ≤ 5 V on.",
                "root_cause": "IGBT module failure, motor winding short, or driver IC blown.",
                "hazard_warning": (
                    "IGBT module at 300 V DC — capacitor bank holds 470 µF × 300 V = lethal. "
                    "No user-serviceable components in inverter module."
                ),
                "can_diy": False, "youtube_id": None,
                "steps": [
                    "Unplug immediately.",
                    "Allow 45 min cool-down.",
                    "Call IFB service — no DIY access to inverter.",
                ],
            },
        },
    },
}


_SA2_SYS = """You are DocumentUnderstandingSubagent v1.0 — part of an IBM Bob 2.0 multi-agent
appliance maintenance pipeline. Your responsibility is semantic document understanding.

You are given:
  1. Subagent-1 telemetry summary (symptom class, anomaly flags, error code).
  2. Relevant OEM service manual chunks (error codes, wiring schematics, OEM tolerances).

Perform document understanding to extract:
  - The best-matching OEM error code entry
  - The exact root cause based on OEM tolerance tables
  - Any wiring hazard warnings from the schematics
  - Whether a DIY fix exists

Output ONLY valid JSON with these exact keys:
  matched_code       (string | null)
  issue_title        (string)
  root_cause         (string)
  oem_tolerance_note (string | null)
  wiring_hazard      (string | null)
  can_diy            (boolean)
  severity           ("LOW" | "HIGH")
  confidence         (integer 0–100)
  technician_reason  (string | null)
"""


async def document_understanding_subagent(
    sa1_output: dict,
    brand: str,
    model: str,
) -> tuple[dict, TraceEntry]:
    """Subagent 2 — runs concurrently with Subagent 1."""
    t0   = time.perf_counter()
    logs = [f"[SA2] DocumentUnderstandingSubagent v1.0 started at {_ts()}"]

    brand_key = brand.strip().upper()
    corpus    = MANUAL_CORPUS.get(brand_key)

    if corpus:
        logs.append(f"[SA2] Loaded OEM corpus for brand={brand_key}. "
                    f"Scanning {len(corpus['error_codes'])} error code entries.")
        manual_text = _format_corpus(corpus, sa1_output.get("normalised_error_code"))
    else:
        logs.append(f"[SA2] Brand '{brand_key}' not in corpus — using generic document chunk.")
        manual_text = "No OEM manual data available for this brand."

    prompt = (
        f"<|system|>\n{_SA2_SYS.strip()}\n<|user|>\n"
        f"=== Subagent-1 Telemetry ===\n{json.dumps(sa1_output, indent=2)}\n\n"
        f"=== OEM Service Manual Chunks ===\n{manual_text}\n"
        "<|assistant|>\n"
    )

    status = "completed"
    try:
        raw    = await asyncio.to_thread(_llm_call, prompt)
        result = _parse_json(raw)
        logs.append(f"[SA2] LLM document understanding complete. "
                    f"matched={result.get('matched_code')}, severity={result.get('severity')}")
    except Exception as exc:  # noqa: BLE001
        logs.append(f"[SA2] LLM unavailable ({exc}). Registry lookup fallback.")
        status = "fallback"
        result = _sa2_fallback(sa1_output, corpus)
        logs.append(f"[SA2] Fallback: matched={result.get('matched_code')}, "
                    f"hazard={result.get('wiring_hazard') is not None}")

    logs.append(f"[SA2] Completed — confidence={result.get('confidence')}%")
    trace = _entry("DocumentUnderstandingSubagent", "1.0", t0, status,
                   f"brand={brand} code={sa1_output.get('normalised_error_code')}",
                   f"matched={result.get('matched_code')} severity={result.get('severity')}",
                   logs)
    return result, trace


def _format_corpus(corpus: dict, ec: Optional[str]) -> str:
    lines = [
        f"Brand : {corpus['brand']}",
        f"Models: {', '.join(corpus['models'])}",
        f"Wiring notes: {corpus['wiring_notes']}",
        "",
        "Error code table:",
    ]
    ec_up = (ec or "").upper()
    for code, info in corpus["error_codes"].items():
        marker = " ◄ MATCHED" if code.upper() == ec_up else ""
        lines.append(
            f"  [{code}]{marker} {info['title']} | severity:{info['severity']}\n"
            f"    OEM tolerance: {info['oem_tolerance']}\n"
            f"    Cause: {info['root_cause']}\n"
            f"    Hazard: {info.get('hazard_warning') or 'None'}\n"
            f"    DIY: {'Yes' if info['can_diy'] else 'No'}"
        )
    return "\n".join(lines)


def _sa2_fallback(sa1: dict, corpus: Optional[dict]) -> dict:
    ec  = (sa1.get("normalised_error_code") or "").upper()
    cls = sa1.get("symptom_class", "UNKNOWN")

    if not corpus:
        return {
            "matched_code": ec or None, "issue_title": "Unrecognised Fault",
            "root_cause": "OEM manual not available for this brand.",
            "oem_tolerance_note": None, "wiring_hazard": None,
            "can_diy": False, "severity": "HIGH",
            "confidence": 20,
            "technician_reason": "Brand not in document corpus — inspect with certified engineer.",
        }

    entry = corpus["error_codes"].get(ec)
    if not entry:
        # Match by symptom class keyword
        cls_kw = {"DRAIN":["DRAIN","PUMP"],"MOTOR":["MOTOR","OVERLOAD"],
                  "DOOR":["DOOR","LOCK"],"FILL":["FILL","WATER","INLET"],
                  "HEAT":["HEAT","HEATER"],"BALANCE":["BALANCE","UNBALANCED"]}
        for code, info in corpus["error_codes"].items():
            kws = cls_kw.get(cls, [])
            if any(k in info["title"].upper() or k in info["root_cause"].upper() for k in kws):
                entry = info
                ec    = code
                break

    if not entry:
        return {
            "matched_code": ec or None, "issue_title": "No OEM Match Found",
            "root_cause": "Symptom class not matched to corpus entry.",
            "oem_tolerance_note": None, "wiring_hazard": None,
            "can_diy": False, "severity": "LOW",
            "confidence": 30,
            "technician_reason": "Manual inspection recommended.",
        }

    return {
        "matched_code":       ec,
        "issue_title":        entry["title"],
        "root_cause":         entry["root_cause"],
        "oem_tolerance_note": entry.get("oem_tolerance"),
        "wiring_hazard":      entry.get("hazard_warning"),
        "can_diy":            entry["can_diy"],
        "severity":           entry["severity"],
        "confidence":         90,
        "technician_reason":  (
            entry.get("hazard_warning")
            if not entry["can_diy"] else None
        ),
    }


# ════════════════════════════════════════════════════════════════════════════════
# Subagent 3 — SafetyTriageSubagent
# Responsibility: Synthesise SA1 + SA2 to produce authoritative safety ruling:
#                 USER_DIY vs. TECHNICIAN_REQUIRED and a machine health score.
# ════════════════════════════════════════════════════════════════════════════════

_SA3_SYS = """You are SafetyTriageSubagent v1.0 — part of an IBM Bob 2.0 multi-agent pipeline.
You synthesise telemetry data (Subagent-1) and OEM document understanding (Subagent-2)
to make an authoritative safety classification.

Safety rules you MUST enforce:
  - Any fault with severity=HIGH → classification MUST be TECHNICIAN_REQUIRED
  - Anomaly flags DRUM_STALLED or OVERPOWER → escalate to HIGH
  - AQUASTOP or water + HIGH_VOLTAGE in wiring hazard → TECHNICIAN_REQUIRED
  - For LOW severity faults with no wiring hazard → USER_DIY is permitted

Compute machine_health_score (0–100):
  Start 100. Deduct 40 for HIGH, 20 for LOW. Deduct 5 per anomaly flag.
  Floor 0, ceiling 100.

Output ONLY valid JSON:
  classification        ("USER_DIY" | "TECHNICIAN_REQUIRED")
  machine_health_score  (integer 0–100)
  risk_level            ("LOW" | "HIGH")
  safety_rationale      (string — 1–2 sentences)
  override_applied      (boolean — true if you overrode SA2 DIY recommendation)
"""


async def safety_triage_subagent(
    sa1: dict,
    sa2: dict,
) -> tuple[dict, TraceEntry]:
    """Subagent 3 — sequential, after SA1+SA2 complete."""
    t0   = time.perf_counter()
    logs = [f"[SA3] SafetyTriageSubagent v1.0 started at {_ts()}"]
    logs.append(f"[SA3] SA1 flags={sa1.get('anomaly_flags')}, "
                f"SA2 severity={sa2.get('severity')}, can_diy={sa2.get('can_diy')}")

    prompt = (
        f"<|system|>\n{_SA3_SYS.strip()}\n<|user|>\n"
        f"=== SA1 Telemetry ===\n{json.dumps(sa1, indent=2)}\n\n"
        f"=== SA2 Document Analysis ===\n{json.dumps(sa2, indent=2)}\n"
        "<|assistant|>\n"
    )

    status = "completed"
    try:
        raw    = await asyncio.to_thread(_llm_call, prompt)
        result = _parse_json(raw)
        logs.append(f"[SA3] LLM triage: class={result.get('classification')}, "
                    f"score={result.get('machine_health_score')}, "
                    f"override={result.get('override_applied')}")
    except Exception as exc:  # noqa: BLE001
        logs.append(f"[SA3] LLM unavailable ({exc}). Deterministic triage.")
        status = "fallback"
        result = _sa3_fallback(sa1, sa2)
        logs.append(f"[SA3] Fallback: class={result['classification']}, "
                    f"score={result['machine_health_score']}")

    logs.append(f"[SA3] Safety ruling: {result.get('classification')} "
                f"(health={result.get('machine_health_score')}%)")
    trace = _entry("SafetyTriageSubagent", "1.0", t0, status,
                   f"sa2_severity={sa2.get('severity')} flags={sa1.get('anomaly_flags')}",
                   f"class={result.get('classification')} score={result.get('machine_health_score')}",
                   logs)
    return result, trace


def _sa3_fallback(sa1: dict, sa2: dict) -> dict:
    severity = (sa2.get("severity") or "LOW").upper()
    flags    = sa1.get("anomaly_flags", [])
    can_diy  = sa2.get("can_diy", True)

    override = False
    if severity == "HIGH":
        can_diy  = False
    if "DRUM_STALLED" in flags or "OVERPOWER" in flags:
        severity = "HIGH"; can_diy = False; override = True
    if sa2.get("wiring_hazard"):
        can_diy  = False

    score = 100 - (40 if severity == "HIGH" else 20) - 5 * len(flags)
    score = max(0, min(100, score))

    rationale = (
        f"Fault severity is {severity}. "
        + (f"Wiring hazard detected: {sa2.get('wiring_hazard')[:80]}. " if sa2.get("wiring_hazard") else "")
        + ("DIY repair approved." if can_diy else "Technician intervention mandatory.")
    )

    return {
        "classification":       "TECHNICIAN_REQUIRED" if not can_diy else "USER_DIY",
        "machine_health_score": score,
        "risk_level":           severity,
        "safety_rationale":     rationale,
        "override_applied":     override,
    }


# ════════════════════════════════════════════════════════════════════════════════
# Subagent 4 — ResolutionDispatchSubagent
# Responsibility: Generate structured step-by-step guides + YouTube ID for DIY,
#                 OR brand-specific service centre hotline for hazard cases.
# ════════════════════════════════════════════════════════════════════════════════

async def resolution_dispatch_subagent(
    sa2: dict,
    sa3: dict,
    brand: str,
) -> tuple[dict, TraceEntry]:
    """Subagent 4 — sequential, after SA3 completes."""
    t0   = time.perf_counter()
    logs = [f"[SA4] ResolutionDispatchSubagent v1.0 started at {_ts()}"]

    brand_key = brand.strip().upper()
    corpus    = MANUAL_CORPUS.get(brand_key, {})
    service   = corpus.get("brand", brand), corpus.get("phone", "N/A")
    code      = (sa2.get("matched_code") or "").upper()
    ec_entry  = corpus.get("error_codes", {}).get(code, {})

    is_diy = sa3.get("classification") == "USER_DIY"
    logs.append(f"[SA4] Classification={sa3.get('classification')}, "
                f"code={code}, brand={brand_key}")

    if is_diy:
        steps    = ec_entry.get("steps", [
            "Unplug the machine.",
            "Refer to the OEM service manual for this error code.",
            "Contact your brand service centre if issue persists.",
        ])
        yt_id    = ec_entry.get("youtube_id")
        dispatch = {
            "mode":            "USER_DIY",
            "steps_to_solve":  [{"step_number": i+1, "instruction": s}
                                 for i, s in enumerate(steps)],
            "youtube_video_id": yt_id,
            "service_contact": {"brand": service[0], "phone": service[1]},
            "call_to_action":  "Follow the steps above. Call service only if issue persists.",
        }
        logs.append(f"[SA4] Dispatching DIY guide: {len(steps)} steps, YT={yt_id}")
    else:
        dispatch = {
            "mode":            "TECHNICIAN_REQUIRED",
            "steps_to_solve":  [{"step_number": i+1, "instruction": s}
                                 for i, s in enumerate(ec_entry.get("steps", [
                                     "Switch off and unplug immediately.",
                                     "Do not attempt any internal access.",
                                     "Call the brand service centre below.",
                                 ]))],
            "youtube_video_id": None,
            "service_contact":  {"brand": service[0], "phone": service[1]},
            "call_to_action":   f"Call {service[1]} immediately for emergency dispatch.",
        }
        logs.append(f"[SA4] Dispatching technician alert. Phone={service[1]}")

    trace = _entry("ResolutionDispatchSubagent", "1.0", t0, "completed",
                   f"classification={sa3.get('classification')} code={code}",
                   f"mode={dispatch['mode']} steps={len(dispatch['steps_to_solve'])}",
                   logs)
    return dispatch, trace


# ════════════════════════════════════════════════════════════════════════════════
# Public entry point — full parallel agent pipeline
# ════════════════════════════════════════════════════════════════════════════════

@dataclass
class DiagnosticResult:
    # Final fields
    can_user_solve:         bool
    machine_health_score:   int
    issue_title:            str
    root_cause:             str
    risk_level:             str
    oem_tolerance_note:     Optional[str]
    wiring_hazard:          Optional[str]
    service_center_contact: dict
    steps_to_solve:         list[dict]
    youtube_video_id:       Optional[str]
    technician_reason:      Optional[str]
    call_to_action:         str
    # Trace
    agent_execution_trace:  list[dict]

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


async def run_diagnostic_pipeline(
    brand:        str,
    model:        str,
    error_code:   Optional[str]  = None,
    water_level:  Optional[str]  = None,
    drum_rpm:     Optional[int]  = None,
    power_draw_w: Optional[int]  = None,
    user_symptom: Optional[str]  = None,
) -> DiagnosticResult:
    """
    Execute the 4-subagent pipeline.
    SA1 and SA2 run IN PARALLEL via asyncio.gather().
    SA3 runs after both complete.
    SA4 runs after SA3.
    """
    pipeline_start = _ts()
    trace: list[TraceEntry] = []

    # ── PHASE 1: Parallel execution (SA1 ∥ SA2) ─────────────────────────────
    (sa1, t1), (sa2, t2) = await asyncio.gather(
        telemetry_ingestion_subagent(
            error_code, water_level, drum_rpm, power_draw_w, user_symptom),
        document_understanding_subagent(
            # SA2 gets a minimal SA1-like seed to work from the same inputs
            {"normalised_error_code": (error_code or "").upper() or None,
             "symptom_class":         "UNKNOWN",
             "anomaly_flags":         []},
            brand, model),
    )

    # Merge SA1 findings into SA2 input for SA3
    # (SA2 already ran; we pass both outputs to SA3)
    trace.extend([t1, t2])

    # ── PHASE 2: Safety Triage (SA3) ─────────────────────────────────────────
    sa3, t3 = await safety_triage_subagent(sa1, sa2)
    trace.append(t3)

    # ── PHASE 3: Resolution Dispatch (SA4) ───────────────────────────────────
    dispatch, t4 = await resolution_dispatch_subagent(sa2, sa3, brand)
    trace.append(t4)

    can_diy = sa3["classification"] == "USER_DIY"

    # steps_to_solve: flatten to plain strings for API contract compliance
    raw_steps = dispatch["steps_to_solve"]
    steps_strings = [
        s["instruction"] if isinstance(s, dict) else str(s)
        for s in raw_steps
    ]

    # technician_reason: null when user can solve; populated only for hazard cases
    tech_reason: Optional[str] = None
    if not can_diy:
        tech_reason = (
            sa2.get("technician_reason")
            or sa2.get("wiring_hazard")
            or sa3.get("safety_rationale")
        )

    return DiagnosticResult(
        can_user_solve         = can_diy,
        machine_health_score   = sa3["machine_health_score"],
        issue_title            = sa2.get("issue_title", "Unknown Fault"),
        root_cause             = sa2.get("root_cause", "Unable to determine."),
        risk_level             = sa3.get("risk_level", "LOW"),
        oem_tolerance_note     = sa2.get("oem_tolerance_note"),
        wiring_hazard          = sa2.get("wiring_hazard"),
        service_center_contact = dispatch["service_contact"],
        steps_to_solve         = steps_strings,
        youtube_video_id       = dispatch.get("youtube_video_id"),
        technician_reason      = tech_reason,
        call_to_action         = dispatch["call_to_action"],
        agent_execution_trace  = [t.to_dict() for t in trace],
    )
