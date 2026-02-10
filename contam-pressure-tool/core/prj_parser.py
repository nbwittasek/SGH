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
        if "levels plus icon data" in line.lower() or "levels" in line.lower() and "icon" in line.lower():
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
