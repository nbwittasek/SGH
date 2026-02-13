"""CONTAM PRJ file modifier.

Injects pressurization/depressurization airflows into a copy of a base
CONTAM PRJ model for each analysis run (one fire floor under one weather
scenario).
"""

from typing import List, Tuple

from .prj_parser import (
    AHSystem,
    check_keywords,
)
from .units import f_to_kelvin, mph_to_ms, scfm_to_kgs


# ---------------------------------------------------------------------------
# Section-index extraction helpers
# ---------------------------------------------------------------------------

def _find_line_by_keyword(lines: List[str], keyword: str, start: int = 0) -> int:
    """Find the first line containing keyword (spaces removed) starting from start."""
    for i in range(start, len(lines)):
        if check_keywords(lines[i], keyword):
            return i
    return -1


def _find_icon_headers(lines: List[str]) -> List[int]:
    """Return line numbers of all '!icn col row  #' headers."""
    return [i for i, line in enumerate(lines) if check_keywords(line, "icncolrow#")]


def _find_path_section(lines: List[str]) -> Tuple[int, int, int]:
    """Find path section boundaries.

    Returns:
        (count_line, header_line, first_data_line)
        count_line: line with 'N ! flow paths:'
        header_line: line with '! P#  f  n# ...'
        first_data_line: first actual path data line
    """
    count_line = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        if "flow paths:" in stripped.lower():
            parts = stripped.split()
            if parts and parts[0].isdigit():
                count_line = i
                break

    header_line = -1
    if count_line >= 0:
        for i in range(count_line, min(count_line + 5, len(lines))):
            if check_keywords(lines[i], "!P#") and check_keywords(lines[i], "n#"):
                header_line = i
                break

    first_data_line = header_line + 1 if header_line >= 0 else -1
    return count_line, header_line, first_data_line


def _find_path_terminator(lines: List[str], first_data_line: int) -> int:
    """Find the -999 terminator after path data."""
    for i in range(first_data_line, len(lines)):
        if lines[i].strip() == "-999":
            return i
    return len(lines)


def _get_path_count_from_line(lines: List[str], count_line: int) -> int:
    """Extract the path count from the count line."""
    parts = lines[count_line].strip().split()
    return int(parts[0]) if parts and parts[0].isdigit() else 0


def _update_path_count(lines: List[str], count_line: int, new_count: int) -> None:
    """Update the path count in the count line."""
    old_line = lines[count_line]
    parts = old_line.strip().split()
    if parts and parts[0].isdigit():
        old_count_str = parts[0]
        # Replace the first occurrence of the count
        lines[count_line] = old_line.replace(old_count_str, str(new_count), 1)


# ---------------------------------------------------------------------------
# Modification step 1: Set output mode
# ---------------------------------------------------------------------------

def set_output_mode(lines: List[str]) -> None:
    """Enable dump mode in the output configuration section."""
    idx = _find_line_by_keyword(lines, "!listdoDlgpfsavezfsavezcsave")
    if idx >= 0 and idx + 1 < len(lines):
        lines[idx + 1] = "   2     1      1      1      0\n"


# ---------------------------------------------------------------------------
# Modification step 2: Set weather data
# ---------------------------------------------------------------------------

def set_weather(lines: List[str], temp_f: float, wind_mph: float, wind_dir: float) -> None:
    """Set weather parameters in the PRJ file.

    Only modifies the FIRST weather data line (steady simulation).
    """
    idx = _find_line_by_keyword(lines, "!TaPbWsWdrh")
    if idx < 0 or idx + 1 >= len(lines):
        return

    data_line = idx + 1
    raw = lines[data_line]

    # Separate data from trailing comment (e.g., "! steady simulation")
    comment_idx = raw.find("!")
    if comment_idx >= 0:
        data_str = raw[:comment_idx]
        comment = " " + raw[comment_idx:].rstrip("\n")
    else:
        data_str = raw
        comment = ""

    parts = data_str.split()
    if len(parts) < 5:
        return

    # Replace: Ta (index 0), Ws (index 2), Wd (index 3)
    parts[0] = f"{f_to_kelvin(temp_f):.3f}"
    parts[2] = f"{mph_to_ms(wind_mph):.3f}"
    parts[3] = f"{wind_dir:.1f}"

    lines[data_line] = " ".join(parts) + comment + "\n"


# ---------------------------------------------------------------------------
# Modification step 3-5: Add pressurization/depressurization paths
# ---------------------------------------------------------------------------

def _format_new_icon_line(icon_type: int, icon_col: int, icon_row: int, path_id: int) -> str:
    """Format a new icon data line."""
    return f"  {icon_type}  {icon_col}  {icon_row}  {path_id}\n"


def _format_new_path_line(
    path_id: int,
    from_zone: int,
    to_zone: int,
    ahs_id: int,
    level_num: int,
    flow_rate_kgs: float,
    icon_type: int,
    direction: int,
) -> str:
    """Format a new airflow path line.

    Type 8 = constant flow path.
    """
    return (
        f"  {path_id}  8  {from_zone}  {to_zone}  0  0  0  {ahs_id}  0  0  {level_num}"
        f"  0.000  0.000  0.000 1 0 0 0 {flow_rate_kgs:.6f} 0 0  {icon_type} {direction}"
        f" -1 0 0 0 1 0 0\n"
    )


def _increment_icon_count(lines: List[str], level_def_line: int) -> None:
    """Increment the icon count in the level definition line."""
    parts = lines[level_def_line].split()
    if len(parts) >= 4:
        old_count = int(parts[3])
        new_count = old_count + 1
        # Replace in the original line preserving formatting
        lines[level_def_line] = lines[level_def_line].replace(
            f" {old_count} ", f" {new_count} ", 1
        )


def add_pressurization_at_level(
    lines: List[str],
    level_icon_header_line: int,
    level_def_line: int,
    num_icons_at_level: int,
    stair_zone_id: int,
    supply_zone_id: int,
    ahs_id: int,
    level_num: int,
    flow_rate_scfm: float,
    icon_type: int = 128,
    icon_col: int = 1,
    icon_row: int = 1,
    next_path_id: int = 1,
    direction: int = 2,
) -> int:
    """Add a pressurization (or depressurization) path at a specific level.

    Modifies lines in-place by inserting new icon and path lines.

    Args:
        lines: The PRJ file lines (modified in-place)
        level_icon_header_line: Line number of '!icn col row  #' for this level
        level_def_line: Line number of the level definition line
        num_icons_at_level: Current number of icons at this level
        stair_zone_id: Zone ID of the stair (or corridor) at this level
        supply_zone_id: Zone ID from AHS (supply zone for press., exhaust for depress.)
        ahs_id: AHS ID
        level_num: Level number (1-based)
        flow_rate_scfm: Flow rate in SCFM (converted to kg/s internally)
        icon_type: Icon type (128 for pressurization, 129 for depressurization)
        icon_col: Icon column position
        icon_row: Icon row position
        next_path_id: Path ID for the new path
        direction: 2 for supply/pressurization, 5 for exhaust/depressurization

    Returns:
        Number of lines added (for offset tracking)
    """
    flow_rate_kgs = scfm_to_kgs(flow_rate_scfm)

    # 1. Insert new icon after the existing icon data
    icon_insert_pos = level_icon_header_line + 1 + num_icons_at_level
    new_icon = _format_new_icon_line(icon_type, icon_col, icon_row, next_path_id)
    lines.insert(icon_insert_pos, new_icon)

    # 2. Increment icon count in level definition
    _increment_icon_count(lines, level_def_line)

    # 3. Find path section (after the icon insertion shifted lines by 1)
    _, _, first_data_line = _find_path_section(lines)
    path_term = _find_path_terminator(lines, first_data_line)

    # 4. Insert new path before the terminator
    if direction == 5:
        # Depressurization: from_zone=target, to_zone=exhaust
        new_path = _format_new_path_line(
            next_path_id, stair_zone_id, supply_zone_id,
            ahs_id, level_num, flow_rate_kgs, icon_type, direction,
        )
    else:
        # Pressurization: from_zone=supply, to_zone=target
        new_path = _format_new_path_line(
            next_path_id, supply_zone_id, stair_zone_id,
            ahs_id, level_num, flow_rate_kgs, icon_type, direction,
        )
    lines.insert(path_term, new_path)

    # 5. Update path count
    count_line, _, _ = _find_path_section(lines)
    if count_line >= 0:
        old_count = _get_path_count_from_line(lines, count_line)
        _update_path_count(lines, count_line, old_count + 1)

    return 2  # Added 2 lines total (1 icon + 1 path)


# ---------------------------------------------------------------------------
# AHS auto-creation (for base models with no AHS defined)
# ---------------------------------------------------------------------------

def _find_ahs_section(lines: List[str]) -> Tuple[int, int]:
    """Find the AHS section: returns (count_line, terminator_line)."""
    count_line = -1
    for i, line in enumerate(lines):
        if "simple ahs" in line.lower() and "!" in line:
            count_line = i
            break
    if count_line < 0:
        return -1, -1
    # Find the -999 terminator
    for i in range(count_line + 1, min(count_line + 20, len(lines))):
        if lines[i].strip() == "-999":
            return count_line, i
    return count_line, -1


def _find_zone_section(lines: List[str]) -> Tuple[int, int, int]:
    """Find zone section: (count_line, first_data_line, terminator_line)."""
    count_line = -1
    for i, line in enumerate(lines):
        stripped = line.strip().lower()
        if "zones:" in stripped and "!" in stripped:
            parts = line.strip().split()
            if parts and parts[0].isdigit():
                count_line = i
                break
    if count_line < 0:
        return -1, -1, -1
    # Skip comment lines
    first_data = count_line + 1
    while first_data < len(lines) and lines[first_data].strip().startswith("!"):
        first_data += 1
    # Find terminator
    for i in range(first_data, len(lines)):
        if lines[i].strip() == "-999":
            return count_line, first_data, i
    return count_line, first_data, len(lines)


def ensure_ahs_systems(lines: List[str]) -> Tuple[int, int]:
    """Create SUPPLY and RETURN AHS systems if none exist.

    Modifies the PRJ lines in-place to add:
      - 4 AHS zones: SUPPLY(Rec), SUPPLY(Sup), RETURN(Rec), RETURN(Sup)
      - 2 AHS definitions (SUPPLY, RETURN)

    Returns: (supply_ahs_id, return_ahs_id) — typically (1, 2)
    If AHS already exist, returns the IDs of existing supply/return.
    """
    ahs_count_line, ahs_term_line = _find_ahs_section(lines)
    if ahs_count_line < 0:
        return 0, 0

    # Check current AHS count
    parts = lines[ahs_count_line].strip().split()
    ahs_count = int(parts[0]) if parts and parts[0].isdigit() else 0

    if ahs_count > 0:
        # AHS already exist — find supply and return IDs
        supply_id = 0
        return_id = 0
        for i in range(ahs_count_line + 1, ahs_term_line):
            line = lines[i].strip()
            if not line or line.startswith("!"):
                continue
            p = line.split()
            if len(p) >= 7:
                ahs_id = int(p[0])
                name = p[-1] if len(p) >= 8 else p[6]
                if "supply" in name.lower() or "press" in name.lower():
                    supply_id = ahs_id
                elif "return" in name.lower() or "exhaust" in name.lower():
                    return_id = ahs_id
        # Fallback if names don't match
        if not supply_id and ahs_count >= 2:
            supply_id = 2
        if not return_id and ahs_count >= 1:
            return_id = 1
        return supply_id, return_id

    # --- Create new AHS systems ---

    # Find max zone ID
    zone_count_line, zone_first, zone_term = _find_zone_section(lines)
    max_zone_id = 0
    if zone_first >= 0:
        for i in range(zone_first, zone_term):
            p = lines[i].strip().split()
            if p and p[0].lstrip("-").isdigit():
                zid = int(p[0])
                if zid > max_zone_id:
                    max_zone_id = zid

    # Find max path ID
    path_count_line, _, path_first = _find_path_section(lines)
    max_path_id = 0
    if path_first >= 0:
        path_term = _find_path_terminator(lines, path_first)
        for i in range(path_first, path_term):
            p = lines[i].strip().split()
            if p and p[0].lstrip("-").isdigit():
                pid = int(p[0])
                if pid > max_path_id:
                    max_path_id = pid

    # Assign new IDs
    supply_rec_zid = max_zone_id + 1
    supply_sup_zid = max_zone_id + 2
    return_rec_zid = max_zone_id + 3
    return_sup_zid = max_zone_id + 4

    supply_ret_pid = max_path_id + 1
    supply_sup_pid = max_path_id + 2
    supply_exh_pid = max_path_id + 3
    return_ret_pid = max_path_id + 4
    return_sup_pid = max_path_id + 5
    return_exh_pid = max_path_id + 6

    supply_ahs_id = 1
    return_ahs_id = 2

    # Pick a level to place AHS zones on (middle level)
    level_positions = re_extract_level_positions(lines)
    mid_level = level_positions[len(level_positions) // 2]["level_index"] if level_positions else 1

    # 1. Insert AHS zone definitions before the zone terminator (-999)
    # Recalculate zone_term since lines haven't changed yet
    _, _, zone_term = _find_zone_section(lines)
    new_zones = [
        f"  {supply_rec_zid} 10   0   0   0  {mid_level}   0.000     0 293.15 0 SUPPLY(Rec) -1 1 3 1 1 0 0 0\n",
        f"  {supply_sup_zid} 10   0   0   0  {mid_level}   0.000     0 293.15 0 SUPPLY(Sup) -1 1 3 1 1 0 0 0\n",
        f"  {return_rec_zid} 10   0   0   0  {mid_level}   0.000     0 293.15 0 RETURN(Rec) -1 1 3 1 1 0 0 0\n",
        f"  {return_sup_zid} 10   0   0   0  {mid_level}   0.000     0 293.15 0 RETURN(Sup) -1 1 3 1 1 0 0 0\n",
    ]
    for i, zline in enumerate(new_zones):
        lines.insert(zone_term + i, zline)

    # Update zone count
    zone_count_line_new, _, _ = _find_zone_section(lines)
    old_zcount = int(lines[zone_count_line_new].strip().split()[0])
    lines[zone_count_line_new] = lines[zone_count_line_new].replace(
        str(old_zcount), str(old_zcount + 4), 1
    )

    # 2. Insert AHS definitions
    ahs_count_line_new, ahs_term_new = _find_ahs_section(lines)
    ahs_defs = [
        f"! # zr# zs# pr# ps# px# name\n",
        f"  {supply_ahs_id} {supply_rec_zid} {supply_sup_zid} {supply_ret_pid} {supply_sup_pid} {supply_exh_pid} -1 SUPPLY\n",
        f"\n",
        f"  {return_ahs_id} {return_rec_zid} {return_sup_zid} {return_ret_pid} {return_sup_pid} {return_exh_pid} -1 RETURN\n",
        f"\n",
    ]
    for i, aline in enumerate(ahs_defs):
        lines.insert(ahs_term_new + i, aline)

    # Update AHS count
    ahs_count_line_final, _ = _find_ahs_section(lines)
    lines[ahs_count_line_final] = lines[ahs_count_line_final].replace("0 !", "2 !", 1)

    return supply_ahs_id, return_ahs_id


# ---------------------------------------------------------------------------
# Re-extract level positions after modifications
# ---------------------------------------------------------------------------

def re_extract_level_positions(lines: List[str]) -> List[dict]:
    """Re-extract level icon header and definition line positions.

    Returns a list of dicts with keys:
        level_index, level_name, icon_header_line, level_def_line, num_icons
    """
    icon_headers = _find_icon_headers(lines)
    levels = []
    for ih in icon_headers:
        # Level def line is the line before the icon header (skip comments)
        def_line = ih - 1
        while def_line >= 0 and lines[def_line].strip().startswith("!"):
            def_line -= 1
        if def_line < 0:
            continue
        parts = lines[def_line].split()
        if len(parts) >= 7:
            levels.append({
                "level_index": int(parts[0]),
                "level_name": parts[-1],
                "icon_header_line": ih,
                "level_def_line": def_line,
                "num_icons": int(parts[3]),
            })
    return levels


# ---------------------------------------------------------------------------
# High-level modification: Build a complete modified PRJ
# ---------------------------------------------------------------------------

def build_modified_prj(
    base_lines: List[str],
    temp_f: float,
    wind_mph: float,
    wind_dir: float,
    stair_configs: List[dict],
    corridor_configs: List[dict],
    roof_configs: List[dict],
    fire_floor_level_num: int,
    ahs_systems: List[AHSystem],
) -> List[str]:
    """Build a complete modified PRJ file for one analysis run.

    Args:
        base_lines: Raw lines from the base PRJ file
        temp_f: Scenario temperature in Fahrenheit
        wind_mph: Scenario wind speed in mph
        wind_dir: Scenario wind direction in degrees
        stair_configs: List of stair pressurization configs, each dict:
            {
                "label": str,
                "levels": [
                    {"level_num": int, "zone_id": int, "flow_rate": float,
                     "ahs_id": int, "supply_zone": int, "icon_type": int,
                     "icon_col": int, "icon_row": int},
                    ...
                ]
            }
        corridor_configs: Same structure as stair_configs but for corridors
            Each level entry also has "exhaust_zone" instead of "supply_zone"
        roof_configs: List of roof stair depressurization configs:
            [{"zone_id": int, "level_num": int, "flow_rate": float,
              "ahs_id": int, "exhaust_zone": int, "icon_type": int,
              "icon_col": int, "icon_row": int}, ...]
        fire_floor_level_num: Level number for corridor depressurization
        ahs_systems: Parsed AHS systems list

    Returns:
        Modified PRJ file lines
    """
    lines = [line for line in base_lines]  # Shallow copy

    # Step 1: Set output mode
    set_output_mode(lines)

    # Step 2: Set weather
    set_weather(lines, temp_f, wind_mph, wind_dir)

    # Step 2b: Ensure AHS systems exist (creates SUPPLY + RETURN if missing)
    supply_ahs_id, return_ahs_id = ensure_ahs_systems(lines)

    # Track next path ID
    # Find max existing path ID
    _, _, first_data = _find_path_section(lines)
    max_path_id = 0
    if first_data >= 0:
        term = _find_path_terminator(lines, first_data)
        for i in range(first_data, term):
            parts = lines[i].split()
            if parts and parts[0].lstrip("-").isdigit():
                pid = int(parts[0])
                if pid > max_path_id:
                    max_path_id = pid
    next_path_id = max_path_id + 1

    # Step 3: Add stair pressurization at ALL levels
    # If stair configs have ahs_id=0, use the auto-created supply AHS
    for stair_cfg in stair_configs:
        for level_entry in stair_cfg["levels"]:
            if level_entry.get("ahs_id", 0) == 0 and supply_ahs_id:
                level_entry["ahs_id"] = supply_ahs_id
        for level_entry in stair_cfg["levels"]:
            zone_id = level_entry.get("zone_id", 0)
            flow_rate = level_entry.get("flow_rate", 0)
            if zone_id == 0 or flow_rate == 0:
                continue

            # Re-extract level positions (they shift after each modification)
            level_positions = re_extract_level_positions(lines)
            level_num = level_entry["level_num"]

            # Find this level's positions
            lpos = None
            for lp in level_positions:
                if lp["level_index"] == level_num:
                    lpos = lp
                    break
            if lpos is None:
                continue

            supply_zone = level_entry.get("supply_zone", 0)
            ahs_id = level_entry.get("ahs_id", 0)
            icon_type = level_entry.get("icon_type", 128)
            icon_col = level_entry.get("icon_col", 1)
            icon_row = level_entry.get("icon_row", 1)

            add_pressurization_at_level(
                lines,
                lpos["icon_header_line"],
                lpos["level_def_line"],
                lpos["num_icons"],
                stair_zone_id=zone_id,
                supply_zone_id=supply_zone,
                ahs_id=ahs_id,
                level_num=level_num,
                flow_rate_scfm=flow_rate,
                icon_type=icon_type,
                icon_col=icon_col,
                icon_row=icon_row,
                next_path_id=next_path_id,
                direction=2,
            )
            next_path_id += 1

    # Step 4: Add roof stair depressurization
    for roof_cfg in roof_configs:
        zone_id = roof_cfg.get("zone_id", 0)
        flow_rate = roof_cfg.get("flow_rate", 0)
        if zone_id == 0 or flow_rate == 0:
            continue

        level_positions = re_extract_level_positions(lines)
        level_num = roof_cfg["level_num"]

        lpos = None
        for lp in level_positions:
            if lp["level_index"] == level_num:
                lpos = lp
                break
        if lpos is None:
            continue

        exhaust_zone = roof_cfg.get("exhaust_zone", 0)
        ahs_id = roof_cfg.get("ahs_id", 0)
        if ahs_id == 0 and return_ahs_id:
            ahs_id = return_ahs_id
        icon_type = roof_cfg.get("icon_type", 129)
        icon_col = roof_cfg.get("icon_col", 1)
        icon_row = roof_cfg.get("icon_row", 1)

        add_pressurization_at_level(
            lines,
            lpos["icon_header_line"],
            lpos["level_def_line"],
            lpos["num_icons"],
            stair_zone_id=zone_id,
            supply_zone_id=exhaust_zone,
            ahs_id=ahs_id,
            level_num=level_num,
            flow_rate_scfm=flow_rate,
            icon_type=icon_type,
            icon_col=icon_col,
            icon_row=icon_row,
            next_path_id=next_path_id,
            direction=5,
        )
        next_path_id += 1

    # Step 5: Add corridor depressurization at fire floor ONLY
    for corr_cfg in corridor_configs:
        for level_entry in corr_cfg["levels"]:
            level_num = level_entry.get("level_num", 0)
            if level_num != fire_floor_level_num:
                continue

            zone_id = level_entry.get("zone_id", 0)
            flow_rate = level_entry.get("flow_rate", 0)
            if zone_id == 0 or flow_rate == 0:
                continue

            level_positions = re_extract_level_positions(lines)
            lpos = None
            for lp in level_positions:
                if lp["level_index"] == level_num:
                    lpos = lp
                    break
            if lpos is None:
                continue

            exhaust_zone = level_entry.get("exhaust_zone", 0)
            ahs_id = level_entry.get("ahs_id", 0)
            if ahs_id == 0 and return_ahs_id:
                ahs_id = return_ahs_id
            icon_type = level_entry.get("icon_type", 129)
            icon_col = level_entry.get("icon_col", 1)
            icon_row = level_entry.get("icon_row", 1)

            add_pressurization_at_level(
                lines,
                lpos["icon_header_line"],
                lpos["level_def_line"],
                lpos["num_icons"],
                stair_zone_id=zone_id,
                supply_zone_id=exhaust_zone,
                ahs_id=ahs_id,
                level_num=level_num,
                flow_rate_scfm=flow_rate,
                icon_type=icon_type,
                icon_col=icon_col,
                icon_row=icon_row,
                next_path_id=next_path_id,
                direction=5,
            )
            next_path_id += 1

    return lines
