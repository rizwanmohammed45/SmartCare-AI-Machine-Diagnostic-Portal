"""
manuals.py — Smart Appliance Diagnostic System
================================================
Authoritative multi-brand service manual registry.

Brands  : LG, Samsung, Bosch, Whirlpool, IFB
Coverage: error codes, safety voltage ratings, OEM tolerances,
          step-by-step resolutions, image URLs, YouTube IDs,
          official customer care phone numbers.

Used by:
  • backend/agents.py  → DocumentUnderstandingSubagent RAG lookup
  • main.py            → /api/diagnose endpoint manual context
"""

from __future__ import annotations
from typing import Optional

# ── SVG step-image factory ────────────────────────────────────────────────────

def _svg(step: int, label: str, bg: str = "#dbeafe", fg: str = "#1d4ed8") -> str:
    """Return a data-URI SVG tile with step number and wrapped label text."""
    safe = label.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    words = safe.split()
    lines, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 > 24:
            lines.append(cur.strip()); cur = w
        else:
            cur += (" " if cur else "") + w
    if cur:
        lines.append(cur.strip())

    y_start = 72 - (len(lines) - 1) * 9
    text_els = "".join(
        f'<text x="100" y="{y_start + i * 18}" font-size="11" fill="{fg}" '
        f'text-anchor="middle" font-family="system-ui,sans-serif">{l}</text>'
        for i, l in enumerate(lines)
    )
    return (
        "data:image/svg+xml;utf8,"
        '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="120" '
        f'viewBox="0 0 200 120"><rect width="200" height="120" rx="10" fill="{bg}"/>'
        f'<text x="100" y="38" font-size="26" font-weight="bold" fill="{fg}" '
        f'text-anchor="middle" font-family="system-ui,sans-serif">Step {step}</text>'
        f'<line x1="30" y1="46" x2="170" y2="46" stroke="{fg}" stroke-width="1.5" '
        f'stroke-dasharray="4 3" opacity=".4"/>{text_els}</svg>'
    )


def _steps(*instructions: str, bg: str = "#dbeafe", fg: str = "#1d4ed8") -> list[dict]:
    return [
        {"step_number": i + 1, "instruction": inst,
         "image_url": _svg(i + 1, inst, bg, fg)}
        for i, inst in enumerate(instructions)
    ]


# ── Master registry ───────────────────────────────────────────────────────────

APPLIANCE_REGISTRY: dict = {

    # ══════════════════════════════════════════════════════════════════════════
    # LG Electronics  |  Toll-free: 1800-315-9999
    # Motor: LG Direct Drive, 240 V AC → 310 V DC inverter bus
    # Safety note: capacitors hold charge 5–10 min post power-off
    # ══════════════════════════════════════════════════════════════════════════
    "LG": {
        "service_contact": {"brand": "LG Electronics", "phone": "1800-315-9999"},
        "safety_voltage": "310 V DC inverter bus — capacitors hold lethal charge 5–10 min after power-off.",
        "models": {
            "FHM1207ZDL": {
                "name": "LG Front Load 7 kg Direct Drive",
                "type": "Front Load Washer",
                "capacity_kg": 7,
                "motor_type": "LG Direct Drive BLDC",
                "inverter_voltage_v": 310,
                "error_codes": {
                    "OE": {
                        "title": "Drain Error",
                        "description": "Water did not drain within the 15-minute OEM cycle window.",
                        "severity": "LOW",
                        "root_cause": (
                            "Blocked pump filter, kinked drain hose, or standpipe height "
                            "above the 100 cm OEM maximum."
                        ),
                        "oem_tolerance": "Drain time must be < 15 min from tub full.",
                        "can_user_solve": True,
                        "steps_to_solve": _steps(
                            "Power off and unplug the machine.",
                            "Place a towel and shallow tray under the filter access cap (bottom-front).",
                            "Unscrew the filter cap counter-clockwise; let water drain into tray.",
                            "Remove lint, coins, and debris from the filter housing.",
                            "Reinsert and tighten the filter cap.",
                            "Check drain hose for kinks; standpipe must be 60–100 cm.",
                            "Plug in and run a Spin Only cycle to confirm fix.",
                        ),
                        "youtube_video_id": "LkCeqi1fFRs",
                        "technician_reason": None,
                    },
                    "UE": {
                        "title": "Unbalanced Load",
                        "description": "Drum detects uneven load; high-speed spin suspended.",
                        "severity": "LOW",
                        "root_cause": (
                            "Single heavy item or mixed heavy/light load; "
                            "machine may be on an unlevel surface."
                        ),
                        "oem_tolerance": "Drum vibration must be < 2 mm at 1200 RPM.",
                        "can_user_solve": True,
                        "steps_to_solve": _steps(
                            "Open the door and redistribute laundry evenly.",
                            "Add 1–2 towels if washing a single bulky item.",
                            "Ensure load does not exceed 7 kg.",
                            "Check all four levelling feet are in firm floor contact.",
                            "Restart the spin cycle.",
                        ),
                        "youtube_video_id": "jFu7kQfHKns",
                        "technician_reason": None,
                    },
                    "dE": {
                        "title": "Door Lock Error",
                        "description": "Door not detected as fully locked before/during cycle.",
                        "severity": "LOW",
                        "root_cause": (
                            "Door not latched, worn gasket, or foreign object in the seal."
                        ),
                        "oem_tolerance": "Lock solenoid must engage within 3 s of Start press.",
                        "can_user_solve": True,
                        "steps_to_solve": _steps(
                            "Inspect door seal for trapped clothing or debris.",
                            "Firmly push door until you hear a click.",
                            "Check door hinge screws are tight.",
                            "Run a short Rinse+Spin cycle to confirm.",
                        ),
                        "youtube_video_id": None,
                        "technician_reason": (
                            "If dE persists after the door closes properly, "
                            "the lock solenoid has failed — do not force the door open."
                        ),
                    },
                    "LE": {
                        "title": "Motor Overload / Inverter Fault",
                        "description": "Inverter motor shut down — abnormal current or winding resistance.",
                        "severity": "HIGH",
                        "root_cause": (
                            "Motor winding short-circuit, seized bearing, "
                            "or inverter control board failure."
                        ),
                        "oem_tolerance": "Motor current must not exceed 9 A RMS.",
                        "can_user_solve": False,
                        "steps_to_solve": _steps(
                            "Switch off and unplug immediately.",
                            "Wait 15 min for 310 V DC bus capacitors to discharge.",
                            "Do not open the rear panel — call LG certified engineer.",
                            bg="#fee2e2", fg="#991b1b",
                        ),
                        "youtube_video_id": None,
                        "technician_reason": (
                            "LE involves the 310 V DC inverter bus. "
                            "Capacitors retain lethal charge up to 10 min after power-off. "
                            "Certified discharge procedure required before any internal access."
                        ),
                    },
                },
            },
            "FHT1006SNL": {
                "name": "LG Front Load 10 kg ThinQ",
                "type": "Front Load Washer",
                "capacity_kg": 10,
                "motor_type": "LG Direct Drive BLDC",
                "inverter_voltage_v": 310,
                "error_codes": {
                    "OE": {
                        "title": "Drain Error",
                        "description": "Water did not drain within the 15-minute OEM cycle window.",
                        "severity": "LOW",
                        "root_cause": "Blocked pump filter or kinked drain hose.",
                        "oem_tolerance": "Drain time < 15 min from tub full.",
                        "can_user_solve": True,
                        "steps_to_solve": _steps(
                            "Power off and unplug the machine.",
                            "Place tray under filter cap (bottom-front panel).",
                            "Unscrew filter cap CCW; drain water.",
                            "Clean filter of debris, reinstall tightly.",
                            "Run Spin Only cycle to confirm.",
                        ),
                        "youtube_video_id": "LkCeqi1fFRs",
                        "technician_reason": None,
                    },
                },
            },
        },
    },

    # ══════════════════════════════════════════════════════════════════════════
    # Samsung Electronics  |  Toll-free: 1800-572-6786
    # Motor: EcoBubble BLDC with Hall sensors, 350 V DC inverter bus
    # Safety note: 400 V / 470 µF capacitors — arc-flash risk if bus bar touched
    # ══════════════════════════════════════════════════════════════════════════
    "SAMSUNG": {
        "service_contact": {"brand": "Samsung Electronics", "phone": "1800-572-6786"},
        "safety_voltage": "350 V DC inverter bus — capacitors hold lethal charge up to 10 min after power-off. Arc-flash risk if bus bar is touched.",
        "models": {
            "WW70T4020EE": {
                "name": "Samsung EcoBubble 7 kg Front Load",
                "type": "Front Load Washer",
                "capacity_kg": 7,
                "motor_type": "Samsung EcoBubble BLDC",
                "inverter_voltage_v": 350,
                "error_codes": {
                    "5E": {
                        "title": "Drain Error",
                        "description": "Machine cannot drain water within the cycle time.",
                        "severity": "LOW",
                        "root_cause": "Clogged debris filter, kinked drain hose, or faulty drain pump.",
                        "oem_tolerance": "Drain pump must clear tub in < 12 min.",
                        "can_user_solve": True,
                        "steps_to_solve": _steps(
                            "Turn off and unplug the washing machine.",
                            "Open the debris filter behind the lower access panel.",
                            "Unscrew emergency drain hose; drain water into a bowl.",
                            "Remove and clean the debris filter under running water.",
                            "Reinstall filter and run a rinse cycle.",
                        ),
                        "youtube_video_id": "4kqMqkKnTvs",
                        "technician_reason": None,
                    },
                    "4E": {
                        "title": "Water Supply Error",
                        "description": "Machine not receiving adequate water within fill timeout.",
                        "severity": "LOW",
                        "root_cause": "Tap closed, low water pressure, kinked inlet hose, or clogged mesh.",
                        "oem_tolerance": "Inlet fill to target level in < 13 min at rated pressure.",
                        "can_user_solve": True,
                        "steps_to_solve": _steps(
                            "Confirm the water tap is fully open.",
                            "Check inlet hose for kinks or sharp bends.",
                            "Unscrew inlet hose and clean the mesh filter.",
                            "Reconnect hose, turn on tap, and restart cycle.",
                        ),
                        "youtube_video_id": None,
                        "technician_reason": None,
                    },
                    "UB": {
                        "title": "Unbalanced Load",
                        "description": "Drum imbalance detected; high-speed spin prevented.",
                        "severity": "LOW",
                        "root_cause": "Load piled to one side or single heavy item.",
                        "oem_tolerance": "Eccentric mass < 250 g equivalent at drum centre.",
                        "can_user_solve": True,
                        "steps_to_solve": _steps(
                            "Pause the cycle and open the door.",
                            "Spread laundry evenly around the drum.",
                            "Resume cycle — machine will retry spin.",
                        ),
                        "youtube_video_id": None,
                        "technician_reason": None,
                    },
                    "3E": {
                        "title": "BLDC Motor / Hall Sensor Fault",
                        "description": "Motor hall sensor or BLDC winding fault detected.",
                        "severity": "HIGH",
                        "root_cause": "Hall sensor IC failure, motor winding short, or PCB motor driver failure.",
                        "oem_tolerance": "Hall sensor output must toggle within 50 ms of motor start.",
                        "can_user_solve": False,
                        "steps_to_solve": _steps(
                            "Power off and unplug immediately — do not restart.",
                            "Wait 15 min for 350 V DC inverter bus to discharge.",
                            "Do not open rear/bottom panel — arc-flash hazard.",
                            "Call Samsung service centre: 1800-572-6786.",
                            bg="#fee2e2", fg="#991b1b",
                        ),
                        "youtube_video_id": None,
                        "technician_reason": (
                            "3E requires hall sensor or motor replacement. "
                            "Samsung 350 V DC inverter capacitors retain lethal charge. "
                            "Only a Samsung-certified engineer with discharge tools may service this fault."
                        ),
                    },
                },
            },
            "WW90T684DLN": {
                "name": "Samsung EcoBubble 9 kg AddWash",
                "type": "Front Load Washer",
                "capacity_kg": 9,
                "motor_type": "Samsung EcoBubble BLDC",
                "inverter_voltage_v": 350,
                "error_codes": {
                    "3C": {
                        "title": "Motor Drive Circuit Fault",
                        "description": "Motor drive circuit short detected — inverter PCB fault.",
                        "severity": "HIGH",
                        "root_cause": (
                            "Short-circuit in BLDC motor drive IGBT, winding insulation "
                            "breakdown, or motor control PCB failure."
                        ),
                        "oem_tolerance": "IGBT gate drive voltage 12–15 V; Vce(sat) ≤ 3 V at rated current.",
                        "can_user_solve": False,
                        "steps_to_solve": _steps(
                            "Switch off and unplug immediately.",
                            "Do not restart — fire and arc-flash risk from shorted IGBT.",
                            "Wait 20 min before any handling — 350 V capacitors present.",
                            "Do not open any panels — contact Samsung authorised service.",
                            "Call Samsung: 1800-572-6786. Quote model WW90T684DLN + 3C.",
                            bg="#fee2e2", fg="#991b1b",
                        ),
                        "youtube_video_id": None,
                        "technician_reason": (
                            "3C is a motor drive short-circuit. The 350 V DC bus "
                            "capacitors (400 V / 470 µF) hold lethal charge and present "
                            "arc-flash risk. Requires Samsung-certified engineer with "
                            "approved discharge kit and IGBT replacement tooling."
                        ),
                    },
                    "5E": {
                        "title": "Drain Error",
                        "description": "Machine cannot drain water within the cycle time.",
                        "severity": "LOW",
                        "root_cause": "Clogged debris filter or kinked drain hose.",
                        "oem_tolerance": "Drain pump must clear tub in < 12 min.",
                        "can_user_solve": True,
                        "steps_to_solve": _steps(
                            "Unplug the machine.",
                            "Open the lower front access panel.",
                            "Unscrew the emergency drain hose; drain water into a bowl.",
                            "Remove and rinse the debris filter.",
                            "Reinstall filter, run Rinse+Spin to confirm.",
                        ),
                        "youtube_video_id": "4kqMqkKnTvs",
                        "technician_reason": None,
                    },
                    "UB": {
                        "title": "Unbalanced Load",
                        "description": "Drum imbalance detected; spin suspended.",
                        "severity": "LOW",
                        "root_cause": "Load piled to one side.",
                        "oem_tolerance": "Eccentric mass < 250 g equivalent.",
                        "can_user_solve": True,
                        "steps_to_solve": _steps(
                            "Open door and redistribute laundry.",
                            "Resume cycle.",
                        ),
                        "youtube_video_id": None,
                        "technician_reason": None,
                    },
                },
            },
        },
    },

    # ══════════════════════════════════════════════════════════════════════════
    # Bosch Home Appliances  |  Toll-free: 1800-266-1880
    # Motor: EcoSilence Drive brushless, 325 V DC inverter bus
    # Safety note: Aquastop solenoid 24 V DC; do not tilt if E23 active
    # ══════════════════════════════════════════════════════════════════════════
    "BOSCH": {
        "service_contact": {"brand": "Bosch Home Appliances", "phone": "1800-266-1880"},
        "safety_voltage": "325 V DC inverter bus — do not open rear panel without discharge. Aquastop: 24 V DC solenoid valve.",
        "models": {
            "WAJ2416SIN": {
                "name": "Bosch Series 4 Front Load 7 kg",
                "type": "Front Load Washer",
                "capacity_kg": 7,
                "motor_type": "Bosch EcoSilence Drive",
                "inverter_voltage_v": 325,
                "error_codes": {
                    "E18": {
                        "title": "Drain Pump Blocked",
                        "description": "Pump cannot clear water — blocked filter or impeller.",
                        "severity": "LOW",
                        "root_cause": "Foreign objects (coins, fibres) blocking pump impeller or drain hose.",
                        "oem_tolerance": "Drain pump head pressure > 0.8 bar at rated RPM.",
                        "can_user_solve": True,
                        "steps_to_solve": _steps(
                            "Switch off and unplug the machine.",
                            "Open the pump cover flap (bottom-right front panel).",
                            "Place a bowl under the flap; unscrew pump cap slowly.",
                            "Remove all debris from the impeller cavity.",
                            "Manually spin impeller — confirm free rotation.",
                            "Screw cap back firmly; run self-test (Start + Temp button).",
                        ),
                        "youtube_video_id": "D8P4Flu4MMQ",
                        "technician_reason": None,
                    },
                    "F21": {
                        "title": "Door Lock Fault",
                        "description": "Door interlock failed to engage before program start.",
                        "severity": "LOW",
                        "root_cause": "Worn door latch, misaligned door, or failed interlock relay.",
                        "oem_tolerance": "Interlock relay must switch < 2 s after door closure.",
                        "can_user_solve": True,
                        "steps_to_solve": _steps(
                            "Open and firmly re-close the door.",
                            "Inspect door seal for any obstructions.",
                            "Press Start — machine will retry locking.",
                            "If fault persists, call Bosch service.",
                        ),
                        "youtube_video_id": None,
                        "technician_reason": (
                            "Persistent F21 after door reset indicates interlock "
                            "relay failure — requires Bosch engineer."
                        ),
                    },
                    "E23": {
                        "title": "Aquastop / Active Leak Detected",
                        "description": "Aquastop float tripped — water in base pan.",
                        "severity": "HIGH",
                        "root_cause": "Hose connection leak, pump shaft seal failure, or tub gasket breach.",
                        "oem_tolerance": "Base pan float trips at > 0.5 L accumulated water.",
                        "can_user_solve": False,
                        "steps_to_solve": _steps(
                            "Switch off and unplug immediately — water near 325 V inverter.",
                            "Do not tilt or move the machine — base pan holds water.",
                            "Do not dry-vacuum inside — electrocution risk.",
                            "Call Bosch emergency service: 1800-266-1880.",
                            bg="#fee2e2", fg="#991b1b",
                        ),
                        "youtube_video_id": None,
                        "technician_reason": (
                            "E23/Aquastop indicates active water leakage inside the cabinet "
                            "adjacent to the 325 V DC inverter. DIY access presents "
                            "electrocution and short-circuit hazard."
                        ),
                    },
                    "E17": {
                        "title": "Water Inlet Timeout",
                        "description": "Machine did not fill to the required level in time.",
                        "severity": "LOW",
                        "root_cause": "Closed tap, low mains pressure (< 0.05 MPa), or blocked inlet mesh.",
                        "oem_tolerance": "Fill to NTC sensor target in < 15 min at rated pressure.",
                        "can_user_solve": True,
                        "steps_to_solve": _steps(
                            "Ensure tap behind machine is fully open.",
                            "Straighten any kinks in the inlet hose.",
                            "Remove inlet hose and rinse the mesh filter.",
                            "Reconnect and restart the program.",
                        ),
                        "youtube_video_id": None,
                        "technician_reason": None,
                    },
                },
            },
            "WAU28PH9GB": {
                "name": "Bosch Series 6 Front Load 9 kg i-DOS",
                "type": "Front Load Washer",
                "capacity_kg": 9,
                "motor_type": "Bosch EcoSilence Drive",
                "inverter_voltage_v": 325,
                "error_codes": {
                    "E18": {
                        "title": "Drain Pump Blocked",
                        "description": "Pump cannot clear water — impeller or hose blocked.",
                        "severity": "LOW",
                        "root_cause": "Debris in pump impeller cavity or kinked drain hose.",
                        "oem_tolerance": "Drain pump head pressure > 0.8 bar at rated RPM.",
                        "can_user_solve": True,
                        "steps_to_solve": _steps(
                            "Switch off and unplug the machine.",
                            "Open pump flap (bottom-right front).",
                            "Drain residual water into a bowl via emergency hose.",
                            "Unscrew pump cap, remove debris, spin impeller freely.",
                            "Refit cap; run self-test (Start + Temp).",
                        ),
                        "youtube_video_id": "D8P4Flu4MMQ",
                        "technician_reason": None,
                    },
                    "E23": {
                        "title": "Aquastop / Active Leak Detected",
                        "description": "Aquastop float tripped — water in base pan.",
                        "severity": "HIGH",
                        "root_cause": "Hose leak or pump seal failure — water in base adjacent to inverter.",
                        "oem_tolerance": "Base pan float trips at > 0.5 L accumulated water.",
                        "can_user_solve": False,
                        "steps_to_solve": _steps(
                            "Unplug immediately — water near 325 V inverter.",
                            "Do not tilt machine.",
                            "Call Bosch: 1800-266-1880.",
                            bg="#fee2e2", fg="#991b1b",
                        ),
                        "youtube_video_id": None,
                        "technician_reason": (
                            "Active leak adjacent to 325 V DC inverter. Electrocution hazard."
                        ),
                    },
                },
            },
        },
    },

    # ══════════════════════════════════════════════════════════════════════════
    # Whirlpool Corporation  |  Toll-free: 1800-208-1800
    # Motor: Direct Drive, 240 V AC; MCB at J12 connector
    # Safety note: capacitor discharge required before PCB removal
    # ══════════════════════════════════════════════════════════════════════════
    "WHIRLPOOL": {
        "service_contact": {"brand": "Whirlpool Corporation", "phone": "1800-208-1800"},
        "safety_voltage": "240 V AC mains to motor control board (MCB). Capacitor discharge required before any PCB removal.",
        "models": {
            "WHITEMAGIC75": {
                "name": "Whirlpool White Magic 7.5 kg",
                "type": "Top Load Washer",
                "capacity_kg": 7.5,
                "motor_type": "Whirlpool Direct Drive",
                "inverter_voltage_v": 240,
                "error_codes": {
                    "F8E1": {
                        "title": "Long Fill / No Water",
                        "description": "Water level sensor did not reach target within 13 min.",
                        "severity": "LOW",
                        "root_cause": "Low water pressure (< 14 PSI), closed supply valve, or clogged inlet.",
                        "oem_tolerance": "Inlet fill sensor must reach target in < 13 min.",
                        "can_user_solve": True,
                        "steps_to_solve": _steps(
                            "Verify the water supply valve is fully open.",
                            "Check inlet hose is not kinked.",
                            "Clean the inlet hose mesh filter.",
                            "Ensure water pressure is above 14 PSI (96 kPa).",
                            "Restart the cycle.",
                        ),
                        "youtube_video_id": None,
                        "technician_reason": None,
                    },
                    "F5E2": {
                        "title": "Door/Lid Switch Error",
                        "description": "Lid switch open signal detected mid-cycle.",
                        "severity": "LOW",
                        "root_cause": "Broken lid switch actuator tab or loose wiring harness at P5.",
                        "oem_tolerance": "Lid switch plunger must be depressed ≥ 3 mm.",
                        "can_user_solve": True,
                        "steps_to_solve": _steps(
                            "Press lid firmly shut — listen for click.",
                            "Inspect actuator tab on lid for cracks.",
                            "If tab broken, order WPW10131219 replacement part.",
                            "Run a test cycle with lid closed.",
                        ),
                        "youtube_video_id": "pX0mXf9CyBM",
                        "technician_reason": (
                            "Persistent F5E2 with intact lid actuator indicates "
                            "a failed switch assembly requiring replacement."
                        ),
                    },
                    "F0E2": {
                        "title": "Overloaded Drum",
                        "description": "Motor detects drum too heavy to rotate safely.",
                        "severity": "LOW",
                        "root_cause": "Load exceeds rated capacity (7.5 kg).",
                        "oem_tolerance": "Drum load must not exceed 7.5 kg.",
                        "can_user_solve": True,
                        "steps_to_solve": _steps(
                            "Cancel the cycle.",
                            "Remove items to bring load below 7.5 kg.",
                            "Restart the program.",
                        ),
                        "youtube_video_id": None,
                        "technician_reason": None,
                    },
                    "F7E1": {
                        "title": "Motor Speed Sensor Fault",
                        "description": "Basket speed sensor does not match commanded RPM.",
                        "severity": "HIGH",
                        "root_cause": "Faulty basket speed sensor, MCB failure, or drive belt slippage.",
                        "oem_tolerance": "Speed sensor AC output 200–600 mV at J2 during spin.",
                        "can_user_solve": False,
                        "steps_to_solve": _steps(
                            "Power off and unplug the machine.",
                            "Do not restart — risk of motor damage.",
                            "Note the error code and contact Whirlpool service.",
                            bg="#fee2e2", fg="#991b1b",
                        ),
                        "youtube_video_id": None,
                        "technician_reason": (
                            "F7E1 requires MCB or speed sensor replacement. "
                            "MCB replacement involves 240 V AC connections — "
                            "certified Whirlpool technician required."
                        ),
                    },
                },
            },
        },
    },

    # ══════════════════════════════════════════════════════════════════════════
    # IFB Industries  |  Toll-free: 1860-425-5678
    # Motor: IFB Senator BLDC, 300 V DC inverter bus (IGBT module)
    # Safety note: IGBT 300 V — no user-serviceable components
    # ══════════════════════════════════════════════════════════════════════════
    "IFB": {
        "service_contact": {"brand": "IFB Industries", "phone": "1860-425-5678"},
        "safety_voltage": "300 V DC IGBT inverter bus — no user-serviceable components inside motor module.",
        "models": {
            "SENATOR-WXSN": {
                "name": "IFB Senator Aqua SX 8 kg",
                "type": "Front Load Washer",
                "capacity_kg": 8,
                "motor_type": "IFB BLDC Inverter",
                "inverter_voltage_v": 300,
                "error_codes": {
                    "C1": {
                        "title": "Door Open / Not Locked",
                        "description": "Machine cannot start — door lock not confirmed.",
                        "severity": "LOW",
                        "root_cause": "Door not fully closed or latch spring worn.",
                        "oem_tolerance": "Door lock confirmation signal < 3 s after Start.",
                        "can_user_solve": True,
                        "steps_to_solve": _steps(
                            "Push door firmly until you hear a double-click.",
                            "Inspect the rubber door seal for obstructions.",
                            "Press Start — machine retries lock up to 3 times.",
                        ),
                        "youtube_video_id": None,
                        "technician_reason": (
                            "If C1 persists with a firmly closed door, "
                            "the latch solenoid or PCB door relay has failed."
                        ),
                    },
                    "C5": {
                        "title": "Drain Pump Error",
                        "description": "Pump running but water level not decreasing.",
                        "severity": "LOW",
                        "root_cause": "Blocked drain pump filter, kinked hose, or seized impeller.",
                        "oem_tolerance": "Pump must lower water level by 5 cm/min.",
                        "can_user_solve": True,
                        "steps_to_solve": _steps(
                            "Turn off and unplug machine.",
                            "Open front service panel (bottom).",
                            "Drain residual water using emergency hose.",
                            "Unscrew filter cap and remove debris.",
                            "Manually spin impeller to confirm it moves freely.",
                            "Reassemble and run a Drain+Spin cycle.",
                        ),
                        "youtube_video_id": "lZU8RQZYpAM",
                        "technician_reason": None,
                    },
                    "C7": {
                        "title": "Heater / NTC Thermistor Fault",
                        "description": "Water temperature did not rise during hot wash program.",
                        "severity": "HIGH",
                        "root_cause": "Failed heating element, NTC thermistor open-circuit, or PCB heater relay.",
                        "oem_tolerance": "Heater element resistance 22–28 Ω at 20 °C; NTC 10 kΩ at 25 °C.",
                        "can_user_solve": False,
                        "steps_to_solve": _steps(
                            "Cancel the cycle immediately.",
                            "Unplug the machine.",
                            "Do not use hot-wash programs until repaired.",
                            "Call IFB service centre: 1860-425-5678.",
                            bg="#fee2e2", fg="#991b1b",
                        ),
                        "youtube_video_id": None,
                        "technician_reason": (
                            "C7 requires heater element or thermistor replacement. "
                            "Heater circuit operates at 230 V mains — "
                            "electrocution risk without certified discharge."
                        ),
                    },
                    "C9": {
                        "title": "Motor Control / IGBT Fault",
                        "description": "BLDC motor driver IGBT overcurrent or overheat trip.",
                        "severity": "HIGH",
                        "root_cause": "IGBT module failure, seized drum bearing, or motor winding short.",
                        "oem_tolerance": "IGBT gate voltage 12–15 V; collector-emitter ≤ 5 V (on-state).",
                        "can_user_solve": False,
                        "steps_to_solve": _steps(
                            "Switch off and unplug immediately.",
                            "Allow 45 min cool-down — 300 V DC IGBT bus present.",
                            "Contact IFB service — no DIY access to inverter module.",
                            bg="#fee2e2", fg="#991b1b",
                        ),
                        "youtube_video_id": None,
                        "technician_reason": (
                            "C9 involves the 300 V DC IGBT inverter bus. "
                            "DIY repair poses lethal electrocution risk. "
                            "Certified IFB engineer required."
                        ),
                    },
                },
            },
        },
    },
}


# ── Public helpers ─────────────────────────────────────────────────────────────

def get_manual_context(brand: str, model: str) -> Optional[dict]:
    """
    Return {'service_contact', 'model_info', 'safety_voltage'} for brand/model.
    Fallback: brand known, model unknown → returns brand shell with empty error_codes.
    Returns None if brand is completely unknown.
    """
    brand_key = brand.strip().upper()
    model_key = model.strip().upper()

    brand_data = APPLIANCE_REGISTRY.get(brand_key)
    if brand_data is None:
        for k, v in APPLIANCE_REGISTRY.items():
            if brand_key in k or k in brand_key:
                brand_data = v
                break

    if brand_data is None:
        return None

    service_contact  = brand_data["service_contact"]
    safety_voltage   = brand_data.get("safety_voltage", "Unknown — treat as high-voltage hazard.")
    models           = brand_data.get("models", {})

    model_data = models.get(model_key) or models.get(model.strip())
    if model_data is None:
        for k, v in models.items():
            if k.upper() == model_key:
                model_data = v
                break

    if model_data is None:
        return {
            "service_contact": service_contact,
            "safety_voltage":  safety_voltage,
            "model_info": {
                "name": f"{brand_data['service_contact']['brand']} Washing Machine",
                "type": "Washer",
                "capacity_kg": None,
                "motor_type": "Unknown",
                "inverter_voltage_v": None,
                "error_codes": {},
            },
        }

    return {
        "service_contact": service_contact,
        "safety_voltage":  safety_voltage,
        "model_info":      model_data,
    }


def get_error_entry(brand: str, model: str, error_code: str) -> Optional[dict]:
    """
    Direct lookup of a specific error code entry.
    Returns the error_codes dict entry or None if not found.
    """
    ctx = get_manual_context(brand, model)
    if ctx is None:
        return None
    ec_up = error_code.strip().upper()
    codes = ctx["model_info"].get("error_codes", {})
    # Exact match first
    entry = codes.get(ec_up) or codes.get(error_code.strip())
    if entry:
        return entry
    # Case-insensitive scan
    for k, v in codes.items():
        if k.upper() == ec_up:
            return v
    return None
