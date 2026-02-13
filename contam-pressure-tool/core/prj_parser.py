"""CONTAM PRJ file parser.

Parses CONTAM 3.x project files to extract building geometry, zones,
air handling systems, flow elements, and airflow paths.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class Level:
    index: int              # 1-based
    name: str               # e.g., "P3", "L1", "EM-Level"
    ref_height: float       # meters
    delta_height: float     # meters
    num_icons: int
    icon_header_line: int   # line number of "!icn col row  #" for this level
    level_def_line: int     # line number of the level definition line


@dataclass
class Zone:
    id: int                 # Z# (1-based, unique)
    name: str               # e.g., "Stair_1" (NOT unique across levels)
    level_num: int          # l# field
    level_name: str         # resolved from levels table
    volume: float           # m^3
    temperature: float      # Kelvin
    line_num: int           # line number in PRJ file


@dataclass
class FlowElement:
    id: int                 # element ID (1-based)
    name: str               # e.g., "Door-Stair1-S2V"
    elem_type: str          # e.g., "plr_conn", "plr_shaft"
    line_num: int           # first line of this element


@dataclass
class AirflowPath:
    id: int                 # P# (1-based)
    flags: int              # f field
    from_zone: int          # n# (-1 = ambient)
    to_zone: int            # m# (-1 = ambient)
    flow_elem_id: int       # e# (references FlowElement.id)
    flow_elem_name: str     # resolved from flow elements table
    ahs: int                # a# field
    level_num: int          # l# field (1-based)
    multiplier: float       # mult field
    fahs: float             # AHS flow rate
    icon_type: int          # icn field
    direction: int          # dir field
    line_num: int           # line number in PRJ file


@dataclass
class AHSystem:
    id: int                 # AHS ID
    name: str               # e.g., "SUPPLY", "RETURN"
    return_zone: int        # zr#
    supply_zone: int        # zs#
    return_path: int        # pr#
    supply_path: int        # ps#
    exhaust_path: int       # px#
    line_num: int           # line number in PRJ file


@dataclass
class ParsedModel:
    filepath: str
    version: str            # e.g., "ContamW 3.4.0.0 0"
    project_name: str       # e.g., "5407 Wilshire"
    levels: List[Level] = field(default_factory=list)
    zones: List[Zone] = field(default_factory=list)
    flow_elements: List[FlowElement] = field(default_factory=list)
    airflow_paths: List[AirflowPath] = field(default_factory=list)
    ahs_systems: List[AHSystem] = field(default_factory=list)
    weather_line_num: int = -1
    output_config_line_num: int = -1
    raw_lines: List[str] = field(default_factory=list)


def check_keywords(line: str, keyword: str) -> bool:
    """Check if keyword exists in line after removing all spaces."""
    return keyword in line.replace(" ", "")


def parse_prj_file(filepath: str) -> ParsedModel:
    """Parse a CONTAM PRJ file and extract all relevant sections.

    Args:
        filepath: Path to the .prj file

    Returns:
        ParsedModel with all parsed sections

    Raises:
        FileNotFoundError: If the PRJ file doesn't exist
        ValueError: If the file format is invalid
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"PRJ file not found: {filepath}")

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    if len(lines) < 3:
        raise ValueError(f"PRJ file too short ({len(lines)} lines): {filepath}")

    model = ParsedModel(
        filepath=str(path.resolve()),
        version=lines[0].strip(),
        project_name=lines[1].strip(),
        raw_lines=lines,
    )

    # Build level name lookup (populated during level parsing)
    level_name_map: dict[int, str] = {}

    # Build flow element name lookup (populated during element parsing)
    elem_name_map: dict[int, str] = {}

    # Parse all sections
    _parse_weather(lines, model)
    _parse_output_config(lines, model)
    _parse_levels(lines, model, level_name_map)
    _parse_zones(lines, model, level_name_map)
    _parse_flow_elements(lines, model, elem_name_map)
    _parse_airflow_paths(lines, model, elem_name_map)
    _parse_ahs(lines, model)

    return model


def _parse_weather(lines: List[str], model: ParsedModel) -> None:
    """Parse weather data section."""
    for i, line in enumerate(lines):
        if check_keywords(line, "!TaPbWsWdrh"):
            # Data is the next line
            if i + 1 < len(lines):
                model.weather_line_num = i + 1
            return


def _parse_output_config(lines: List[str], model: ParsedModel) -> None:
    """Parse output configuration section."""
    for i, line in enumerate(lines):
        if check_keywords(line, "!listdoDlgpfsavezfsavezcsave"):
            if i + 1 < len(lines):
                model.output_config_line_num = i + 1
            return


def _parse_levels(
    lines: List[str],
    model: ParsedModel,
    level_name_map: dict,
) -> None:
    """Parse levels and icon data."""
    # Find the levels count line: "N ! levels plus icon data:"
    level_count = 0
    levels_start = -1
    for i, line in enumerate(lines):
        if "levels plus icon data" in line.lower() or ("levels" in line.lower() and "icon" in line.lower()):
            parts = line.strip().split()
            if parts and parts[0].isdigit():
                level_count = int(parts[0])
                levels_start = i + 1
                break

    if level_count == 0 or levels_start < 0:
        return

    # Parse levels by looking for icon header lines
    i = levels_start
    level_idx = 0
    while i < len(lines) and level_idx < level_count:
        if check_keywords(lines[i], "icncolrow#"):
            icon_header_line = i
            # The level definition line is the line BEFORE the icon header
            # but we need to skip any comment lines, so scan back
            def_line = icon_header_line - 1
            while def_line >= levels_start and lines[def_line].strip().startswith("!"):
                def_line -= 1

            if def_line >= levels_start:
                level_def_line = def_line
                parts = lines[level_def_line].split()
                # Format: level_index refHt delHt num_icons u_flag1 u_flag2 level_name
                if len(parts) >= 7:
                    level_index = int(parts[0])
                    ref_height = float(parts[1])
                    delta_height = float(parts[2])
                    num_icons = int(parts[3])
                    level_name = parts[-1]  # Last field is the name

                    level = Level(
                        index=level_index,
                        name=level_name,
                        ref_height=ref_height,
                        delta_height=delta_height,
                        num_icons=num_icons,
                        icon_header_line=icon_header_line,
                        level_def_line=level_def_line,
                    )
                    model.levels.append(level)
                    level_name_map[level_index] = level_name
                    level_idx += 1

            # Skip past the icon data lines
            i = icon_header_line + 1 + (model.levels[-1].num_icons if model.levels else 0)
        else:
            i += 1


def _parse_zones(
    lines: List[str],
    model: ParsedModel,
    level_name_map: dict,
) -> None:
    """Parse zones section."""
    # Find zones count line
    zone_count = 0
    zones_start = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.endswith("! zones:") or stripped.endswith("!zones:"):
            parts = stripped.split()
            if parts and parts[0].isdigit():
                zone_count = int(parts[0])
                break

    if zone_count == 0:
        return

    # Find the header line
    for i, line in enumerate(lines):
        if check_keywords(line, "!Z#") and check_keywords(line, "name"):
            zones_start = i + 1
            break

    if zones_start < 0:
        return

    # Parse zone data lines
    count = 0
    i = zones_start
    while i < len(lines) and count < zone_count:
        line = lines[i].strip()
        if line == "-999":
            break
        parts = line.split()
        if len(parts) >= 11 and parts[0].lstrip("-").isdigit():
            try:
                zone_id = int(parts[0])
                level_num = int(parts[5])
                volume = float(parts[7])
                temperature = float(parts[8])
                name = parts[10]
                level_name = level_name_map.get(level_num, f"Level-{level_num}")

                zone = Zone(
                    id=zone_id,
                    name=name,
                    level_num=level_num,
                    level_name=level_name,
                    volume=volume,
                    temperature=temperature,
                    line_num=i,
                )
                model.zones.append(zone)
                count += 1
            except (ValueError, IndexError):
                pass
        i += 1


def _parse_flow_elements(
    lines: List[str],
    model: ParsedModel,
    elem_name_map: dict,
) -> None:
    """Parse flow elements section (3 lines per element)."""
    # Find flow elements count line
    elem_count = 0
    for i, line in enumerate(lines):
        if check_keywords(line, "!flowelements:"):
            parts = line.strip().split()
            if parts and parts[0].isdigit():
                elem_count = int(parts[0])
            break

    if elem_count == 0:
        return

    # Find the start of element data: look for the line after "! flow elements:"
    elems_start = -1
    for i, line in enumerate(lines):
        if check_keywords(line, "!flowelements:"):
            elems_start = i + 1
            break

    if elems_start < 0:
        return

    # Each element = 3 lines
    i = elems_start
    count = 0
    while i < len(lines) - 2 and count < elem_count:
        line1 = lines[i].strip()
        if line1 == "-999":
            break

        parts = line1.split()
        if len(parts) >= 4 and parts[0].isdigit():
            elem_id = int(parts[0])
            elem_type = parts[2]
            elem_name = parts[3] if len(parts) >= 4 else parts[2]

            element = FlowElement(
                id=elem_id,
                name=elem_name,
                elem_type=elem_type,
                line_num=i,
            )
            model.flow_elements.append(element)
            elem_name_map[elem_id] = elem_name
            count += 1
            i += 3  # Skip 3 lines per element
        else:
            i += 1

    # Also handle case where element format is: id icon_num type name
    # parts[0]=id, parts[1]=icon, parts[2]=type, parts[3]=name


def _parse_airflow_paths(
    lines: List[str],
    model: ParsedModel,
    elem_name_map: dict,
) -> None:
    """Parse airflow paths section."""
    # Find paths count line
    path_count = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if "flow paths:" in stripped.lower() or check_keywords(line, "!flowpaths:"):
            parts = stripped.split()
            if parts and parts[0].isdigit():
                path_count = int(parts[0])
            break

    if path_count == 0:
        return

    # Find the header line
    paths_start = -1
    for i, line in enumerate(lines):
        if check_keywords(line, "!P#") and check_keywords(line, "n#") and check_keywords(line, "m#"):
            paths_start = i + 1
            break

    if paths_start < 0:
        return

    # Parse path data lines
    count = 0
    i = paths_start
    while i < len(lines) and count < path_count:
        line = lines[i].strip()
        if line == "-999":
            break
        parts = line.split()
        if len(parts) >= 22 and parts[0].lstrip("-").isdigit():
            try:
                path_id = int(parts[0])
                flags = int(parts[1])
                from_zone = int(parts[2])
                to_zone = int(parts[3])
                flow_elem_id = int(parts[4])
                ahs = int(parts[7])
                level_num = int(parts[10])
                multiplier = float(parts[14])
                fahs = float(parts[18])
                icon_type = int(parts[21])
                direction = int(parts[22]) if len(parts) > 22 else 0
                flow_elem_name = elem_name_map.get(flow_elem_id, f"Element-{flow_elem_id}")

                path = AirflowPath(
                    id=path_id,
                    flags=flags,
                    from_zone=from_zone,
                    to_zone=to_zone,
                    flow_elem_id=flow_elem_id,
                    flow_elem_name=flow_elem_name,
                    ahs=ahs,
                    level_num=level_num,
                    multiplier=multiplier,
                    fahs=fahs,
                    icon_type=icon_type,
                    direction=direction,
                    line_num=i,
                )
                model.airflow_paths.append(path)
                count += 1
            except (ValueError, IndexError):
                pass
        i += 1


def _parse_ahs(lines: List[str], model: ParsedModel) -> None:
    """Parse AHS (Air Handling Systems) section."""
    # Find AHS count line
    ahs_count = 0
    ahs_count_line = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        if "simple ahs:" in stripped.lower() or check_keywords(line, "!simpleAHS:"):
            parts = stripped.split()
            if parts and parts[0].isdigit():
                ahs_count = int(parts[0])
                ahs_count_line = i
            break

    if ahs_count == 0:
        return

    # Find the header line
    ahs_start = -1
    for i in range(ahs_count_line, min(ahs_count_line + 5, len(lines))):
        if check_keywords(lines[i], "!#zr#zs#"):
            ahs_start = i + 1
            break

    if ahs_start < 0:
        # Try right after the count line
        ahs_start = ahs_count_line + 1
        # Skip any comment lines
        while ahs_start < len(lines) and lines[ahs_start].strip().startswith("!"):
            ahs_start += 1

    # Parse AHS entries (2 lines per entry: data + blank)
    i = ahs_start
    count = 0
    while i < len(lines) and count < ahs_count:
        line = lines[i].strip()
        if line == "-999":
            break
        if not line:
            i += 1
            continue
        parts = line.split()
        if len(parts) >= 7 and parts[0].lstrip("-").isdigit():
            try:
                ahs_id = int(parts[0])
                return_zone = int(parts[1])
                supply_zone = int(parts[2])
                return_path = int(parts[3])
                supply_path = int(parts[4])
                exhaust_path = int(parts[5])
                # Name is the last field (skip the flags field at index 6)
                name = parts[7] if len(parts) >= 8 else parts[6]
                if name == "-1" and len(parts) >= 8:
                    name = parts[7]

                ahs = AHSystem(
                    id=ahs_id,
                    name=name,
                    return_zone=return_zone,
                    supply_zone=supply_zone,
                    return_path=return_path,
                    supply_path=supply_path,
                    exhaust_path=exhaust_path,
                    line_num=i,
                )
                model.ahs_systems.append(ahs)
                count += 1
            except (ValueError, IndexError):
                pass
        i += 1


def get_zone_display_name(zone: Zone) -> str:
    """Get display name for a zone: 'ZoneName (Zone #ID, Level LevelName)'"""
    return f"{zone.name} (Zone #{zone.id}, Level {zone.level_name})"


def get_zones_by_level(model: ParsedModel, level_num: int) -> List[Zone]:
    """Get all zones at a specific level."""
    return [z for z in model.zones if z.level_num == level_num]


def get_zones_by_name(model: ParsedModel, name: str) -> List[Zone]:
    """Get all zones with a specific name (across all levels)."""
    return [z for z in model.zones if z.name == name]


def find_flow_element_by_name(model: ParsedModel, name: str) -> Optional[FlowElement]:
    """Find a flow element by its name."""
    for elem in model.flow_elements:
        if elem.name == name:
            return elem
    return None


def find_paths_by_element_name(
    model: ParsedModel, element_name: str
) -> List[AirflowPath]:
    """Find all airflow paths that use a specific flow element name."""
    elem = find_flow_element_by_name(model, element_name)
    if elem is None:
        return []
    return [p for p in model.airflow_paths if p.flow_elem_id == elem.id]


def find_ahs_by_name(model: ParsedModel, name: str) -> Optional[AHSystem]:
    """Find an AHS by its name (case-insensitive)."""
    for ahs in model.ahs_systems:
        if ahs.name.lower() == name.lower():
            return ahs
    return None


def get_max_path_id(model: ParsedModel) -> int:
    """Get the maximum path ID in the model."""
    if not model.airflow_paths:
        return 0
    return max(p.id for p in model.airflow_paths)


# ---------------------------------------------------------------------------
# Auto-detection / suggestions engine
# ---------------------------------------------------------------------------

import re


def _normalize_stair_key(name: str) -> str:
    """Normalize a stair zone name to a canonical key for grouping.

    Handles inconsistencies like Stair_1/Stair1, Stair_4/Stair4, etc.
    Returns a lowercase key like 'stair1', 'stair2', 'stair4'.
    """
    # Remove underscores, hyphens, spaces and lowercase
    clean = name.replace("_", "").replace("-", "").replace(" ", "").lower()
    # Extract the stair identifier: "stair" + number(s)
    m = re.match(r"(stair|stwr|egress|exitstair)(\d+)", clean)
    if m:
        return f"stair{m.group(2)}"
    return clean


def _detect_stair_zone_groups(model: ParsedModel) -> List[dict]:
    """Detect stair zone groups by finding zone names that repeat across levels.

    Uses normalized name matching to group variants like Stair_1/Stair1,
    Stair_4/Stair4, etc. as the same logical stairwell.
    Excludes vestibule zones (e.g., ST1_v, S4_V, Stair2V).
    Returns list of dicts: {name, zones: [{zone_id, level_num, level_name, volume}]}
    """
    # Match stair zones but NOT vestibule patterns
    stair_keywords = re.compile(
        r"(?i)(stair|stwr|egress|exit[_\-]?stair)"
    )
    # Exclude vestibule patterns:
    #   _v or -v at end, vest anywhere, _v word boundary, _v/,
    #   ST#_v, Stair2V_L3, Stair2V2_L3, ST4.VEST, ST6.Vest, etc.
    vestibule_exclude = re.compile(
        r"(?i)([_\-]v$|vest|_v\b|_v/|^st\d*[_\-]?v$|v/l\d"
        r"|(?:stair|stwr|st)\d*v\d*[_\-]"
        r"|(?:stair|stwr|st)\d*\.v)"
    )

    # Group zones by normalized key
    key_groups: dict[str, dict[str, any]] = {}
    for z in model.zones:
        if stair_keywords.search(z.name) and not vestibule_exclude.search(z.name):
            key = _normalize_stair_key(z.name)
            if key not in key_groups:
                key_groups[key] = {"names": set(), "zones": []}
            key_groups[key]["names"].add(z.name)
            key_groups[key]["zones"].append(z)

    # A stair must span at least 2 levels to be a real stair
    results = []
    for key in sorted(key_groups.keys()):
        group = key_groups[key]
        zones = group["zones"]
        if len(zones) >= 2:
            # Use the most common name variant as the canonical label
            name_counts: dict[str, int] = {}
            for z in zones:
                name_counts[z.name] = name_counts.get(z.name, 0) + 1
            canonical_name = max(name_counts, key=name_counts.get)

            results.append({
                "name": canonical_name,
                "normalized_key": key,
                "all_names": sorted(group["names"]),
                "zones": [
                    {
                        "zone_id": z.id,
                        "zone_name": z.name,
                        "level_num": z.level_num,
                        "level_name": z.level_name,
                        "volume": z.volume,
                    }
                    for z in sorted(zones, key=lambda zz: zz.level_num)
                ],
            })
    return results


def _detect_corridor_zone_groups(model: ParsedModel) -> List[dict]:
    """Detect corridor zone groups by finding zone names with corridor keywords.

    Uses case-insensitive grouping so 'Corridor' and 'corridor' merge into
    one group.  The most common spelling is used as the canonical name.
    """
    corr_keywords = re.compile(
        r"(?i)(corridor|corr|hallway|lobby)"
    )

    # Group by lowercased name so case variants merge
    key_groups: dict[str, dict] = {}
    for z in model.zones:
        if corr_keywords.search(z.name):
            key = z.name.lower()
            if key not in key_groups:
                key_groups[key] = {"names": {}, "zones": []}
            key_groups[key]["names"][z.name] = key_groups[key]["names"].get(z.name, 0) + 1
            key_groups[key]["zones"].append(z)

    results = []
    for key in sorted(key_groups.keys()):
        group = key_groups[key]
        zones = group["zones"]
        if len(zones) >= 2:
            # Use the most common spelling as the canonical name
            canonical = max(group["names"], key=group["names"].get)
            results.append({
                "name": canonical,
                "zones": [
                    {
                        "zone_id": z.id,
                        "zone_name": z.name,
                        "level_num": z.level_num,
                        "level_name": z.level_name,
                        "volume": z.volume,
                    }
                    for z in sorted(zones, key=lambda zz: zz.level_num)
                ],
            })
    return results


def _detect_vestibule_zones(model: ParsedModel, stair_groups: List[dict]) -> dict:
    """Detect vestibule zones associated with each stair.

    For each stair group, looks for vestibule zones by:
    1. Name patterns: ST1_v, ST2_V, Stair2V/L43, etc.
    2. Connectivity: zones connected to stair zones via S2V flow elements.

    Returns: {stair_key: [{zone_id, zone_name, level_num, level_name}]}
    """
    # Build stair number -> stair key mapping
    stair_num_map: dict[str, str] = {}
    for sg in stair_groups:
        m = re.search(r"(\d+)", sg["normalized_key"])
        if m:
            stair_num_map[m.group(1)] = sg["normalized_key"]

    vest_results: dict[str, List[dict]] = {sg["normalized_key"]: [] for sg in stair_groups}

    # Pattern 1: Name-based vestibule detection
    # Matches: ST1_v, ST2_V, Stair1_V, Stair3_V, ST4.VEST, ST6.Vest
    vest_pattern = re.compile(
        r"(?i)(st|stair|stwr)[\-_.]?(\d+)[\-_.]?(v|vest|vestibule)"
    )
    # Also match patterns like "Stair2V/L43", "Stair2V_L3"
    vest_pattern2 = re.compile(
        r"(?i)(stair|st|stwr)[\-_.]?(\d+)\s*v"
    )

    for z in model.zones:
        m = vest_pattern.search(z.name) or vest_pattern2.search(z.name)
        if m:
            stair_num = m.group(2)
            stair_key = stair_num_map.get(stair_num)
            if stair_key and stair_key in vest_results:
                vest_results[stair_key].append({
                    "zone_id": z.id,
                    "zone_name": z.name,
                    "level_num": z.level_num,
                    "level_name": z.level_name,
                })

    # Pattern 2: Connectivity-based — find zones connected via S2V paths
    for sg in stair_groups:
        paths = _detect_path_elements_for_stair(model, sg["name"], sg.get("all_names", []))
        s2v_elem_name = paths.get("s2v", "")
        if not s2v_elem_name:
            continue

        elem = find_flow_element_by_name(model, s2v_elem_name)
        if not elem:
            continue

        # Find all airflow paths using this S2V element
        stair_zone_ids = {z["zone_id"] for z in sg["zones"]}
        for p in model.airflow_paths:
            if p.flow_elem_id == elem.id:
                # S2V path connects stair to vestibule
                # The "to" zone that is NOT a stair zone is the vestibule
                vest_zone_id = None
                if p.from_zone in stair_zone_ids and p.to_zone not in stair_zone_ids:
                    vest_zone_id = p.to_zone
                elif p.to_zone in stair_zone_ids and p.from_zone not in stair_zone_ids:
                    vest_zone_id = p.from_zone

                if vest_zone_id is not None:
                    # Find the zone
                    for z in model.zones:
                        if z.id == vest_zone_id and z.level_num == p.level_num:
                            # Avoid duplicates
                            existing_ids = {v["zone_id"] for v in vest_results[sg["normalized_key"]]}
                            if z.id not in existing_ids:
                                vest_results[sg["normalized_key"]].append({
                                    "zone_id": z.id,
                                    "zone_name": z.name,
                                    "level_num": z.level_num,
                                    "level_name": z.level_name,
                                })

    # Sort by level
    for key in vest_results:
        vest_results[key].sort(key=lambda v: v["level_num"])

    return vest_results


def _detect_path_elements_for_stair(
    model: ParsedModel, stair_name: str, all_names: List[str] = None
) -> dict:
    """Try to match flow element names to a stair.

    Looks for naming patterns like:
        Door-Stair1-S2V, Door-Stair1-V2C, Door-Stair1-EXT
        Door-Stair2S2V2, Door-Stair2V2C2
    Handles multiple name variants (e.g., Stair_1 and Stair1).
    """
    # Build all normalization variants
    names = [stair_name]
    if all_names:
        names.extend(all_names)

    variants = set()
    for n in names:
        clean = n.replace("_", "").replace("-", "").replace(" ", "")
        variants.add(clean.lower())
        variants.add(n.lower())
        variants.add(n.replace("_", "").lower())
    # Also extract just the stair number to match patterns like "Door-Stair1-S2V"
    m = re.search(r"(\d+)", stair_name)
    if m:
        num = m.group(1)
        variants.add(f"stair{num}")

    result = {"s2v": "", "v2c": "", "ext": "", "s2v2": "", "v2c2": "", "s2c": ""}

    path_patterns = {
        "s2v": re.compile(r"(?i)s2v(?!2)"),
        "v2c": re.compile(r"(?i)v2c(?!2)"),
        "ext": re.compile(r"(?i)(ext|exterior)"),
        "s2v2": re.compile(r"(?i)s2v2"),
        "v2c2": re.compile(r"(?i)v2c2"),
        "s2c": re.compile(r"(?i)s2c(?!2)"),  # stair-to-corridor (no vestibule)
    }

    # Build a set of element IDs that are actually referenced by airflow paths
    used_elem_ids = {p.flow_elem_id for p in model.airflow_paths}

    for elem in model.flow_elements:
        # Skip elements that exist but are not referenced by any airflow path
        if elem.id not in used_elem_ids:
            continue

        elem_clean = elem.name.replace("_", "").replace("-", "").replace(" ", "").lower()
        # Check if this element name contains any variant of the stair name
        matches_stair = any(v in elem_clean for v in variants)
        if not matches_stair:
            continue

        for path_key, pattern in path_patterns.items():
            if pattern.search(elem.name) and not result[path_key]:
                result[path_key] = elem.name

    return result


def _detect_corridor_path_element(model: ParsedModel) -> str:
    """Detect the corridor floor leakage flow element.

    Looks for element names containing FLR, LK, Measured, floor, leak,
    FLR.AVG, FLOOR_AVE, etc.
    """
    patterns = [
        re.compile(r"(?i)flr.*lk.*measur"),
        re.compile(r"(?i)floor.*leak.*measur"),
        re.compile(r"(?i)flr.*measur"),
        re.compile(r"(?i)corr.*leak"),
        re.compile(r"(?i)floor.*leak"),
        re.compile(r"(?i)flr[\._]*(avg|ave)"),
        re.compile(r"(?i)floor[\._]*(avg|ave)"),
    ]

    for elem in model.flow_elements:
        for pat in patterns:
            if pat.search(elem.name):
                return elem.name
    return ""


def _detect_supply_ahs(model: ParsedModel) -> Optional[AHSystem]:
    """Detect the supply AHS (for stair pressurization)."""
    for ahs in model.ahs_systems:
        if "supply" in ahs.name.lower() or "press" in ahs.name.lower():
            return ahs
    # Fallback: return AHS with highest ID (commonly the supply)
    if model.ahs_systems:
        return max(model.ahs_systems, key=lambda a: a.id)
    return None


def _detect_return_ahs(model: ParsedModel) -> Optional[AHSystem]:
    """Detect the return/exhaust AHS (for corridor depressurization)."""
    for ahs in model.ahs_systems:
        if "return" in ahs.name.lower() or "exhaust" in ahs.name.lower():
            return ahs
    # Fallback: return AHS with lowest ID
    if model.ahs_systems:
        return min(model.ahs_systems, key=lambda a: a.id)
    return None


def _detect_ahs_for_stair(model: ParsedModel, stair_zones: List[dict]) -> Optional[int]:
    """Detect which AHS is connected to stair zones via airflow paths.

    Traces supply paths (icon_type 128) connected to stair zones
    and returns the AHS ID used.
    """
    stair_zone_ids = {z["zone_id"] for z in stair_zones}

    # Look for airflow paths connected to stair zones that have an AHS
    ahs_counts: dict[int, int] = {}
    for p in model.airflow_paths:
        if p.ahs > 0 and (p.from_zone in stair_zone_ids or p.to_zone in stair_zone_ids):
            ahs_counts[p.ahs] = ahs_counts.get(p.ahs, 0) + 1

    if ahs_counts:
        return max(ahs_counts, key=ahs_counts.get)
    return None


def _detect_ahs_for_corridor(model: ParsedModel, corridor_zones: List[dict]) -> Optional[int]:
    """Detect which AHS is connected to corridor zones via airflow paths."""
    corr_zone_ids = {z["zone_id"] for z in corridor_zones}

    ahs_counts: dict[int, int] = {}
    for p in model.airflow_paths:
        if p.ahs > 0 and (p.from_zone in corr_zone_ids or p.to_zone in corr_zone_ids):
            ahs_counts[p.ahs] = ahs_counts.get(p.ahs, 0) + 1

    if ahs_counts:
        return max(ahs_counts, key=ahs_counts.get)
    return None


def _detect_roof_level_for_stair(
    stair_zones: List[dict], model: ParsedModel
) -> dict:
    """Find the topmost level where a stair exists for roof depressurization."""
    if not stair_zones:
        return {}
    # The last zone in the list (sorted by level_num) is the topmost
    top = stair_zones[-1]
    return {
        "zone_id": top["zone_id"],
        "level_num": top["level_num"],
        "level_name": top["level_name"],
    }


def _detect_weather_from_model(model: ParsedModel) -> dict:
    """Extract current weather settings from the model."""
    from .units import kelvin_to_f, ms_to_mph

    if model.weather_line_num < 0 or model.weather_line_num >= len(model.raw_lines):
        return {"temp_f": 70.0, "wind_mph": 0.0, "wind_dir": 270.0}

    parts = model.raw_lines[model.weather_line_num].split()
    if len(parts) < 4:
        return {"temp_f": 70.0, "wind_mph": 0.0, "wind_dir": 270.0}

    try:
        temp_k = float(parts[0])
        wind_ms = float(parts[2])
        wind_dir = float(parts[3])
        return {
            "temp_f": round(kelvin_to_f(temp_k), 1),
            "wind_mph": round(ms_to_mph(wind_ms), 1),
            "wind_dir": round(wind_dir, 0),
        }
    except (ValueError, IndexError):
        return {"temp_f": 70.0, "wind_mph": 0.0, "wind_dir": 270.0}


def auto_detect_config(model: ParsedModel) -> dict:
    """Analyze a parsed model and generate suggested configuration.

    Performs comprehensive auto-detection of stairs, corridors, vestibules,
    AHS assignments, flow path elements, and weather. Uses normalized name
    matching, connectivity analysis, and volume heuristics to produce a
    high-confidence configuration ready to apply.

    Returns a dict with:
        stairs: [{label, zone_name, all_names, zones, vestibules, paths, roof, ahs_id}]
        corridors: [{label, zone_name, zones, path_name, ahs_id}]
        supply_ahs: {id, name} or null
        return_ahs: {id, name} or null
        roof_configs: [{stair_label, zone_id, level_num, level_name}]
        weather: {temp_f, wind_mph, wind_dir}
        confidence: str ("high", "medium", "low")
    """
    stair_groups = _detect_stair_zone_groups(model)
    corridor_groups = _detect_corridor_zone_groups(model)
    supply_ahs = _detect_supply_ahs(model)
    return_ahs = _detect_return_ahs(model)
    corr_path = _detect_corridor_path_element(model)
    weather = _detect_weather_from_model(model)
    vestibule_map = _detect_vestibule_zones(model, stair_groups)

    # Build stair suggestions
    stairs = []
    for sg in stair_groups:
        paths = _detect_path_elements_for_stair(
            model, sg["name"], sg.get("all_names", [])
        )
        roof = _detect_roof_level_for_stair(sg["zones"], model)
        vest_key = sg.get("normalized_key", "")
        vestibules = vestibule_map.get(vest_key, [])

        # Detect per-stair AHS via connectivity
        stair_ahs_id = _detect_ahs_for_stair(model, sg["zones"])
        # Fall back to global supply AHS
        if stair_ahs_id is None and supply_ahs:
            stair_ahs_id = supply_ahs.id

        stairs.append({
            "label": sg["name"],
            "zone_name": sg["name"],
            "all_names": sg.get("all_names", [sg["name"]]),
            "normalized_key": sg.get("normalized_key", ""),
            "zones": sg["zones"],
            "vestibules": vestibules,
            "paths": paths,
            "roof": roof,
            "ahs_id": stair_ahs_id,
        })

    # Build corridor suggestions
    corridors = []
    for i, cg in enumerate(corridor_groups):
        corr_ahs_id = _detect_ahs_for_corridor(model, cg["zones"])
        if corr_ahs_id is None and return_ahs:
            corr_ahs_id = return_ahs.id

        corridors.append({
            "label": f"Corridor_{i + 1}",
            "zone_name": cg["name"],
            "zones": cg["zones"],
            "path_name": corr_path,
            "ahs_id": corr_ahs_id,
        })

    # Roof configs
    roof_configs = []
    for stair in stairs:
        if stair["roof"]:
            roof_configs.append({
                "stair_label": stair["label"],
                **stair["roof"],
            })

    # Confidence scoring — more signals = higher confidence
    has_stairs = len(stairs) > 0
    has_corridors = len(corridors) > 0
    has_ahs = supply_ahs is not None
    has_paths = any(
        s["paths"]["s2v"] or s["paths"]["s2c"] for s in stairs
    )
    has_vestibules = any(len(s["vestibules"]) > 0 for s in stairs)
    has_corr_path = bool(corr_path)
    score = sum([has_stairs, has_corridors, has_ahs, has_paths, has_vestibules, has_corr_path])
    confidence = "high" if score >= 4 else "medium" if score >= 2 else "low"

    # Build detailed detection log for user feedback
    detection_details = []
    for s in stairs:
        detail = f"Stair '{s['label']}': {len(s['zones'])} levels"
        if s["vestibules"]:
            detail += f", {len(s['vestibules'])} vestibule zones"
        if s["paths"]["s2v"]:
            detail += f", S2V={s['paths']['s2v']}"
        if s["paths"]["v2c"]:
            detail += f", V2C={s['paths']['v2c']}"
        if s["paths"]["s2c"]:
            detail += f", S2C={s['paths']['s2c']}"
        if len(s.get("all_names", [])) > 1:
            detail += f" (name variants: {', '.join(s['all_names'])})"
        detection_details.append(detail)
    for c in corridors:
        detail = f"Corridor '{c['zone_name']}': {len(c['zones'])} levels"
        if c["path_name"]:
            detail += f", path={c['path_name']}"
        detection_details.append(detail)

    return {
        "stairs": stairs,
        "corridors": corridors,
        "supply_ahs": {"id": supply_ahs.id, "name": supply_ahs.name} if supply_ahs else None,
        "return_ahs": {"id": return_ahs.id, "name": return_ahs.name} if return_ahs else None,
        "corridor_path_element": corr_path,
        "roof_configs": roof_configs,
        "weather": weather,
        "confidence": confidence,
        "detection_details": detection_details,
        "summary": {
            "stairs_detected": len(stairs),
            "corridors_detected": len(corridors),
            "vestibules_detected": sum(len(s["vestibules"]) for s in stairs),
            "stair_names": [s["label"] for s in stairs],
            "corridor_names": [c["zone_name"] for c in corridors],
        },
    }
