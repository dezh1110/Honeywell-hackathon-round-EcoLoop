"""
File-parsing helpers the MCP server exposes as agentic tools:
  - reading zone/thermostat objects out of an IDF
  - turning a raw EnergyPlus .err file into structured, LLM-readable events

Kept dependency-free (no `eppy` requirement) so the MCP server can run even in
environments where EnergyPlus itself isn't installed (e.g. this diagnostic
path is also unit-testable in CI without a full EnergyPlus install).
"""
from __future__ import annotations

import re
from pathlib import Path

from app.telemetry.models import EnergyPlusRuntimeError

_ERR_LINE_RE = re.compile(r"^\*\*\s*(Warning|Severe|Fatal)\s*\*\*\s*(.*)$", re.IGNORECASE)

_ZONE_OBJECT_RE = re.compile(r"^\s*Zone\s*,", re.IGNORECASE)


def parse_err_file(err_path: str | Path) -> list[EnergyPlusRuntimeError]:
    """Parse an EnergyPlus `.err` file into structured warning/severe/fatal events.

    EnergyPlus error lines look like:
        ** Warning ** Weather file location will be used ...
        ** Severe  ** GetZoneData: Errors found in Zone ...
        **  Fatal  ** Errors found in getting input. Program terminates.
    """
    path = Path(err_path)
    if not path.exists():
        return []

    events: list[EnergyPlusRuntimeError] = []
    for raw_line in path.read_text(errors="ignore").splitlines():
        match = _ERR_LINE_RE.match(raw_line.strip())
        if not match:
            continue
        severity_raw, message = match.groups()
        severity = severity_raw.strip().lower()
        if severity not in ("warning", "severe", "fatal"):
            continue
        events.append(
            EnergyPlusRuntimeError(
                severity=severity,  # type: ignore[arg-type]
                message=message.strip(),
                raw_line=raw_line.strip(),
            )
        )
    return events


def summarize_errors(errors: list[EnergyPlusRuntimeError], max_items: int = 10) -> str:
    """Compact text digest for the LLM's context window (not the raw file)."""
    # Defensive coercion: smaller/quantized LLMs occasionally emit tool-call
    # arguments with the right value but the wrong JSON type (e.g. "10"
    # instead of 10), which previously crashed this function with
    # `TypeError: slice indices must be integers` deep inside a live
    # decision cycle -- found by actually running this against llama3.2:3b,
    # not a hypothetical. Falls back to the default rather than raising.
    try:
        max_items = int(max_items)
    except (TypeError, ValueError):
        max_items = 10

    if not errors:
        return "No warnings, severe errors, or fatal errors in the last run."

    counts = {"warning": 0, "severe": 0, "fatal": 0}
    for e in errors:
        counts[e.severity] += 1

    lines = [f"{counts['fatal']} fatal, {counts['severe']} severe, {counts['warning']} warning."]
    # Prioritize fatal > severe > warning when truncating.
    ordered = sorted(errors, key=lambda e: {"fatal": 0, "severe": 1, "warning": 2}[e.severity])
    for e in ordered[:max_items]:
        lines.append(f"[{e.severity.upper()}] {e.message}")
    return "\n".join(lines)


def list_zone_names(idf_path: str | Path) -> list[str]:
    """Extract `Zone,` object names from an IDF without a full parser."""
    path = Path(idf_path)
    if not path.exists():
        return []
    names: list[str] = []
    text = path.read_text(errors="ignore")
    for obj in re.split(r";", text):
        obj = obj.strip()
        if not _ZONE_OBJECT_RE.match(obj):
            continue
        fields = [f.strip() for f in obj.split(",")]
        if len(fields) >= 2:
            names.append(fields[1])
    return names


def _parse_idf_objects(text: str) -> dict[str, list[list[str]]]:
    """Minimal IDF parser: strips `!` comments, splits on `;` into objects,
    and groups each object's fields (including its Name as fields[0]) by
    object type. Good enough for cross-reference checks; not a substitute
    for EnergyPlus's own input processor."""
    cleaned_lines = []
    for line in text.splitlines():
        idx = line.find("!")
        cleaned_lines.append(line[:idx] if idx != -1 else line)
    cleaned = "\n".join(cleaned_lines)

    by_type: dict[str, list[list[str]]] = {}
    for raw_obj in cleaned.split(";"):
        raw_obj = raw_obj.strip()
        if not raw_obj:
            continue
        fields = [f.strip() for f in raw_obj.split(",")]
        obj_type, rest = fields[0], fields[1:]
        if not obj_type:
            continue
        by_type.setdefault(obj_type, []).append(rest)
    return by_type


def validate_idf_references(idf_path: str | Path) -> list[str]:
    """Cross-reference check catching the most common hand-authored-IDF
    mistakes: a name referenced in one object (a zone, schedule,
    construction, equipment list, EMS sensor/actuator/program, ...) that
    doesn't match any object actually defined with that name, and supply-air
    node names that disagree between `ZoneHVAC:EquipmentConnections` and
    `ZoneHVAC:IdealLoadsAirSystem` for the same zone.

    This does NOT replace validating with EnergyPlus/IDF Editor -- it can't
    catch unit mismatches, invalid choice-keys, or anything the real IDD
    schema would reject. It exists to keep this repo's IDF from silently
    rotting (a renamed zone, a typo'd schedule) between the times someone
    actually runs it through EnergyPlus.
    """
    path = Path(idf_path)
    if not path.exists():
        return [f"IDF file not found: {idf_path}"]

    by_type = _parse_idf_objects(path.read_text(errors="ignore"))
    errors: list[str] = []

    def names(obj_type: str) -> set[str]:
        return {f[0] for f in by_type.get(obj_type, []) if f and f[0]}

    zone_names = names("Zone")
    schedule_names = names("Schedule:Compact")
    construction_names = names("Construction")
    equip_list_names = names("ZoneHVAC:EquipmentList")
    ideal_loads_names = names("ZoneHVAC:IdealLoadsAirSystem")
    electric_equip_names = names("ElectricEquipment")
    program_names = names("EnergyManagementSystem:Program")
    sensor_names = names("EnergyManagementSystem:Sensor")
    actuator_names = names("EnergyManagementSystem:Actuator")
    thermostat_names = names("ThermostatSetpoint:DualSetpoint")

    def check_ref(obj_type: str, field_idx: int, valid_names: set[str], what: str) -> None:
        for f in by_type.get(obj_type, []):
            if len(f) > field_idx and f[field_idx] and f[field_idx] not in valid_names:
                errors.append(f"{obj_type} '{f[0]}': references unknown {what} '{f[field_idx]}'")

    check_ref("People", 1, zone_names, "zone")
    check_ref("Lights", 1, zone_names, "zone")
    check_ref("ElectricEquipment", 1, zone_names, "zone")
    check_ref("ZoneControl:Thermostat", 1, zone_names, "zone")
    check_ref("ZoneHVAC:IdealLoadsAirSystem", 1, schedule_names, "schedule")

    for f in by_type.get("BuildingSurface:Detailed", []):
        if len(f) > 3 and f[3] not in zone_names:
            errors.append(f"BuildingSurface:Detailed '{f[0]}': unknown zone '{f[3]}'")
        if len(f) > 2 and f[2] not in construction_names:
            errors.append(f"BuildingSurface:Detailed '{f[0]}': unknown construction '{f[2]}'")

    for f in by_type.get("ThermostatSetpoint:DualSetpoint", []):
        for idx in (1, 2):
            if len(f) > idx and f[idx] not in schedule_names:
                errors.append(f"ThermostatSetpoint:DualSetpoint '{f[0]}': unknown schedule '{f[idx]}'")

    for f in by_type.get("ZoneControl:Thermostat", []):
        if len(f) > 4 and f[4] not in thermostat_names:
            errors.append(f"ZoneControl:Thermostat '{f[0]}': unknown thermostat object '{f[4]}'")

    for f in by_type.get("ZoneHVAC:EquipmentConnections", []):
        if len(f) > 1 and f[1] not in equip_list_names:
            errors.append(f"ZoneHVAC:EquipmentConnections '{f[0]}': unknown equipment list '{f[1]}'")

    for f in by_type.get("ZoneHVAC:EquipmentList", []):
        if len(f) > 3 and f[3] not in ideal_loads_names:
            errors.append(f"ZoneHVAC:EquipmentList '{f[0]}': unknown equipment object '{f[3]}'")

    for f in by_type.get("EnergyManagementSystem:Sensor", []):
        if len(f) > 1 and f[1] not in ideal_loads_names:
            errors.append(f"EnergyManagementSystem:Sensor '{f[0]}': unknown key value '{f[1]}'")

    for f in by_type.get("EnergyManagementSystem:Actuator", []):
        if len(f) > 1 and f[1] not in electric_equip_names:
            errors.append(f"EnergyManagementSystem:Actuator '{f[0]}': unknown component '{f[1]}'")

    all_ems_names = sensor_names | actuator_names
    for f in by_type.get("EnergyManagementSystem:Program", []):
        body = " ".join(f[1:])
        tokens = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", body)) - {"SET"}
        unknown = tokens - all_ems_names
        if unknown:
            errors.append(f"EnergyManagementSystem:Program '{f[0]}': unknown EMS variables {sorted(unknown)}")

    for f in by_type.get("EnergyManagementSystem:ProgramCallingManager", []):
        for prog in f[2:]:
            if prog and prog not in program_names:
                errors.append(f"EnergyManagementSystem:ProgramCallingManager '{f[0]}': unknown program '{prog}'")

    econn_supply = {f[0]: f[2] for f in by_type.get("ZoneHVAC:EquipmentConnections", []) if len(f) > 2}
    ideal_supply = {f[0]: f[2] for f in by_type.get("ZoneHVAC:IdealLoadsAirSystem", []) if len(f) > 2}
    for zone, supply_node in econn_supply.items():
        prefix = zone.replace("ZONE ", "Zone")
        matches = [name for name in ideal_supply if name.startswith(prefix)]
        if not matches:
            continue
        for m in matches:
            if ideal_supply[m] != supply_node:
                errors.append(
                    f"Node mismatch: {zone} EquipmentConnections supply node '{supply_node}' "
                    f"vs {m} '{ideal_supply[m]}'"
                )

    return errors
