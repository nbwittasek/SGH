"""CONTAM PRJ file modifier.

Injects pressurization/depressurization airflows into a copy of a base
CONTAM PRJ model for each analysis run.

Key fixes v3:
- Creates a dedicated flow element for tool-generated paths
- All new paths use type=0 (standard) with valid flow element reference
- AHS internal paths created properly in the path section
- Icon placement collision detection with warnings
"""

import re
from typing import List, Tuple
import logging

from .prj_parser import check_keywords
from .units import f_to_kelvin, mph_to_ms, scfm_to_kgs

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Section-index helpers
# ---------------------------------------------------------------------------

def _find_line_by_keyword(lines, keyword, start=0):
    for i in range(start, len(lines)):
        if check_keywords(lines[i], keyword):
            return i
    return -1

def _find_icon_headers(lines):
    return [i for i, line in enumerate(lines) if check_keywords(line, "icncolrow#")]

def _find_path_section(lines):
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

def _find_path_terminator(lines, first_data_line):
    for i in range(first_data_line, len(lines)):
        if lines[i].strip() == "-999":
            return i
    return len(lines)

def _get_path_count(lines, count_line):
    parts = lines[count_line].strip().split()
    return int(parts[0]) if parts and parts[0].isdigit() else 0

def _set_path_count(lines, count_line, new_count):
    """Replace the leading integer on a count line with new_count."""
    lines[count_line] = re.sub(r'^\s*\d+', f'{new_count:>5}',
                                lines[count_line], count=1)

def _find_ahs_section(lines):
    count_line = -1
    for i, line in enumerate(lines):
        if "simple ahs" in line.lower() and "!" in line:
            count_line = i
            break
    if count_line < 0:
        return -1, -1
    for i in range(count_line + 1, min(count_line + 200, len(lines))):
        if lines[i].strip() == "-999":
            return count_line, i
    return count_line, -1

def _find_zone_section(lines):
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
    first_data = count_line + 1
    while first_data < len(lines) and lines[first_data].strip().startswith("!"):
        first_data += 1
    for i in range(first_data, len(lines)):
        if lines[i].strip() == "-999":
            return count_line, first_data, i
    return count_line, first_data, len(lines)

def _get_max_path_id(lines):
    _, _, first = _find_path_section(lines)
    mx = 0
    if first >= 0:
        term = _find_path_terminator(lines, first)
        for i in range(first, term):
            p = lines[i].split()
            if p and p[0].lstrip("-").isdigit():
                pid = int(p[0])
                if pid > mx:
                    mx = pid
    return mx


# ---------------------------------------------------------------------------
# Flow element section helpers
# ---------------------------------------------------------------------------

def _find_flow_element_section(lines):
    """Find flow element section: (count_line, terminator_line)."""
    count_line = -1
    for i, line in enumerate(lines):
        stripped = line.strip().lower()
        if 'flow elements' in stripped and '!' in stripped:
            parts = line.strip().split()
            if parts and parts[0].isdigit():
                count_line = i
                break
    if count_line < 0:
        return -1, -1
    for i in range(count_line + 1, len(lines)):
        if lines[i].strip() == '-999':
            return count_line, i
    return count_line, -1


def _get_max_element_id(lines):
    """Find the highest flow element ID."""
    cl, term = _find_flow_element_section(lines)
    if cl < 0:
        return 0
    mx = 0
    for i in range(cl + 1, term):
        parts = lines[i].strip().split()
        if len(parts) >= 4 and parts[0].isdigit():
            eid = int(parts[0])
            if eid > mx:
                mx = eid
    return mx


TOOL_ELEMENT_NAME = "TOOL_PRESS_DUCT"


def ensure_tool_flow_element(lines):
    """Create a flow element for tool-generated paths if not present.

    Creates a plr_conn (power law connection) element with large opening
    characteristics. Returns the element ID.
    """
    cl, term = _find_flow_element_section(lines)
    if cl < 0:
        logger.warning("No flow element section found in PRJ")
        return 1  # fallback

    # Check if our element already exists
    for i in range(cl + 1, term):
        if TOOL_ELEMENT_NAME in lines[i]:
            parts = lines[i].strip().split()
            if parts and parts[0].isdigit():
                return int(parts[0])

    # Create new element
    new_id = _get_max_element_id(lines) + 1
    # plr_conn type 23: power law connection (large duct)
    # Coefficients: lam=1e-05  turb=0.01  expt=0.5  dTurb=0.01  expt2=0.65  u_P=1
    # These represent a very large opening with minimal resistance
    new_elem = [
        f"{new_id} 23 plr_conn {TOOL_ELEMENT_NAME}\n",
        f"Large duct element for pressurization tool paths\n",
        f" 1.0e-05 0.01 0.5 0.01 0.65 1\n",
    ]
    for j, el in enumerate(new_elem):
        lines.insert(term + j, el)

    # Update count
    old_count = int(lines[cl].strip().split()[0])
    lines[cl] = re.sub(r'^\s*\d+', f'{old_count + 1:>5}',
                        lines[cl], count=1)

    logger.info("Created flow element %d (%s)", new_id, TOOL_ELEMENT_NAME)
    return new_id

# ---------------------------------------------------------------------------
# Output mode & weather
# ---------------------------------------------------------------------------

def set_output_mode(lines):
    idx = _find_line_by_keyword(lines, "!listdoDlgpfsavezfsavezcsave")
    if idx >= 0 and idx + 1 < len(lines):
        lines[idx + 1] = "   2     1      1      1      0\n"

def set_weather(lines, temp_f, wind_mph, wind_dir):
    idx = _find_line_by_keyword(lines, "!TaPbWsWdrh")
    if idx < 0 or idx + 1 >= len(lines):
        return
    data_line = idx + 1
    raw = lines[data_line]
    ci = raw.find("!")
    if ci >= 0:
        data_str, comment = raw[:ci], " " + raw[ci:].rstrip("\n")
    else:
        data_str, comment = raw, ""
    parts = data_str.split()
    if len(parts) < 5:
        return
    parts[0] = f"{f_to_kelvin(temp_f):.3f}"
    parts[2] = f"{mph_to_ms(wind_mph):.3f}"
    parts[3] = f"{wind_dir:.1f}"
    lines[data_line] = " ".join(parts) + comment + "\n"

# ---------------------------------------------------------------------------
# Path format detection & creation
# ---------------------------------------------------------------------------

def _detect_path_field_count(lines):
    """Count fields in existing path lines to match format."""
    _, _, first = _find_path_section(lines)
    if first < 0:
        return 30
    term = _find_path_terminator(lines, first)
    for i in range(first, min(first + 10, term)):
        parts = lines[i].split()
        if parts and parts[0].lstrip("-").isdigit() and len(parts) >= 23:
            return len(parts)
    return 30

def _format_path_line(path_id, from_zone, to_zone, ahs_id, level_num,
                       flow_kgs, icon_type, direction, field_count=30,
                       flow_elem=1, path_flag=0):
    """Format a new airflow path line matching CONTAM 3.4 format.

    path_flag encodes the path type as a bitmask:
        0  = standard two-way airflow path (uses flow element e#)
        8  = AHS supply/return delivery path (e# forced to 0)
        16 = AHS recirculation path (e# forced to 0)
        32 = AHS outdoor-air intake path (e# forced to 0)
        64 = AHS exhaust-to-ambient path (e# forced to 0)
    """
    # AHS paths (flag != 0) never reference a flow element;
    # they use the Fahs field for their flow specification.
    elem = 0 if path_flag != 0 else flow_elem

    # Infrastructure paths (f=16/32/64) use waz=-1
    waz = "-1" if path_flag in (16, 32, 64) else "0"

    core = [
        str(path_id),       # P#
        str(path_flag),      # f  (path flag / type bitmask)
        str(from_zone),      # n# (from zone)
        str(to_zone),        # m# (to zone)
        str(elem),           # e# (flow element; 0 for AHS paths)
        "0",                 # f# (filter)
        "0",                 # w# (wind)
        str(ahs_id),         # a# (AHS)
        "0",                 # s# (schedule)
        "0",                 # c# (control)
        str(level_num),      # l#
        "0.000",             # X
        "0.000",             # Y
        "0.000",             # relHt
        "1",                 # mult
        "0",                 # wPset
        "0",                 # wPmod
        waz,                 # wazm (-1 for infra paths)
        f"{flow_kgs:.6e}",   # Fahs (AHS design flow rate)
        "0",                 # Xmax
        "0",                 # Xmin
        str(icon_type),      # icn
        str(direction),      # dir
    ]
    # Trailing fields after dir:  clr  u_X1  u_X2  cfd  cfd_name  cfd_ptype  ???
    # Original script uses:       -1   0     0     0    1         0          0   (for delivery)
    # ContamW generates:          -1   1     1     1    1         0          0   (for infrastructure)
    if path_flag in (16, 32, 64):
        # Infrastructure (created by AHS system internally)
        trail = ["-1", "1", "1", "1", "1", "0", "0"]
    elif path_flag == 8:
        # AHS delivery paths (supply/return to building zones)
        trail = ["-1", "0", "0", "0", "1", "0", "0"]
    else:
        # Standard airflow paths
        trail = ["-1", "0", "0", "0", "0", "0", "0"]
    return "  " + "  ".join(core) + "  " + "  ".join(trail) + "\n"

def _format_icon_line(icon_type, col, row, ref):
    return f"  {icon_type}  {col}  {row}  {ref}\n"

def _increment_icon_count(lines, level_def_line):
    """Increment the 4th field (icon count) on a level definition line."""
    parts = lines[level_def_line].split()
    if len(parts) >= 4:
        old = int(parts[3])
        # Replace only the 4th whitespace-separated field
        # Pattern: match first 3 fields then capture the 4th integer
        lines[level_def_line] = re.sub(
            r'^(\s*\S+\s+\S+\s+\S+\s+)(\d+)',
            lambda m: m.group(1) + str(old + 1),
            lines[level_def_line],
            count=1,
        )

# ---------------------------------------------------------------------------
# Icon collision detection
# ---------------------------------------------------------------------------

def _get_occupied(lines, icon_header_line, num_icons):
    occ = set()
    start = icon_header_line + 1
    for j in range(num_icons):
        idx = start + j
        if idx < len(lines):
            p = lines[idx].split()
            if len(p) >= 3:
                try:
                    occ.add((int(p[1]), int(p[2])))
                except (ValueError, IndexError):
                    pass
    return occ

def find_free_position(lines, icon_header_line, num_icons, zone_col, zone_row):
    """Find unoccupied position near a zone icon.
    Returns (col, row, success).
    """
    occupied = _get_occupied(lines, icon_header_line, num_icons)
    offsets = [
        (-1, 0), (1, 0), (0, -1), (0, 1),
        (-2, 0), (2, 0), (0, -2), (0, 2),
        (-1, -1), (1, -1), (-1, 1), (1, 1),
        (-3, 0), (3, 0), (-1, -2), (1, -2),
    ]
    for dc, dr in offsets:
        c, r = zone_col + dc, zone_row + dr
        if c > 0 and r > 0 and (c, r) not in occupied:
            return c, r, True
    fb = zone_col - 1 if zone_col > 1 else zone_col + 1
    return fb, zone_row, False

# ---------------------------------------------------------------------------
# Add pressurization/depressurization path at a level
# ---------------------------------------------------------------------------

def add_pressurization_at_level(
    lines, level_icon_header_line, level_def_line, num_icons_at_level,
    stair_zone_id, supply_zone_id, ahs_id, level_num,
    flow_rate_scfm, icon_type=128, icon_col=1, icon_row=1,
    next_path_id=1, direction=2, field_count=30, flow_elem=1,
):
    """Add a pressurization or depressurization path at a specific level.
    Returns (lines_added, warnings_list).
    """
    warnings = []
    flow_kgs = scfm_to_kgs(flow_rate_scfm)

    # Check icon placement
    if icon_col <= 1 and icon_row <= 1:
        warnings.append(
            f"Level {level_num}: Icon at default (1,1) — "
            f"use Auto-Populate to place near zone"
        )
    else:
        occupied = _get_occupied(lines, level_icon_header_line, num_icons_at_level)
        if (icon_col, icon_row) in occupied:
            nc, nr, ok = find_free_position(
                lines, level_icon_header_line, num_icons_at_level,
                icon_col, icon_row,
            )
            if not ok:
                warnings.append(
                    f"Level {level_num}: No free position near ({icon_col},{icon_row}), "
                    f"placed at ({nc},{nr}) — may overlap"
                )
            else:
                warnings.append(
                    f"Level {level_num}: ({icon_col},{icon_row}) occupied, "
                    f"moved to ({nc},{nr})"
                )
            icon_col, icon_row = nc, nr

    # Use the icon_type passed from config (128=supply fan, 129=exhaust fan)
    # This controls both the level sketchpad icon AND the path line's icn field.
    contam_icon = icon_type

    # 1. Insert icon
    insert_pos = level_icon_header_line + 1 + num_icons_at_level
    lines.insert(insert_pos, _format_icon_line(contam_icon, icon_col, icon_row, next_path_id))

    # 2. Increment icon count
    _increment_icon_count(lines, level_def_line)

    # 3. Insert path (after icon insertion shifted lines by 1)
    _, _, fd = _find_path_section(lines)
    pt = _find_path_terminator(lines, fd)

    # AHS delivery paths (a# != 0) MUST use path_flag=8 and e#=0.
    # CONTAM rejects regular paths (f=0) with AHS associations.
    pf = 8 if ahs_id != 0 else 0

    if direction == 5:
        new_path = _format_path_line(
            next_path_id, stair_zone_id, supply_zone_id,
            ahs_id, level_num, flow_kgs, contam_icon, direction,
            field_count=field_count, flow_elem=flow_elem, path_flag=pf,
        )
    else:
        new_path = _format_path_line(
            next_path_id, supply_zone_id, stair_zone_id,
            ahs_id, level_num, flow_kgs, contam_icon, direction,
            field_count=field_count, flow_elem=flow_elem, path_flag=pf,
        )
    lines.insert(pt, new_path)

    # 4. Update path count
    cl, _, _ = _find_path_section(lines)
    if cl >= 0:
        old_c = _get_path_count(lines, cl)
        _set_path_count(lines, cl, old_c + 1)

    return 2, warnings

# ---------------------------------------------------------------------------
# AHS system creation
# ---------------------------------------------------------------------------

def ensure_ahs_systems(lines, field_count=30, flow_elem=1):
    """Create SUPPLY and RETURN AHS systems if none exist.
    Creates zones, internal paths, and AHS definitions.
    Returns (supply_ahs_id, return_ahs_id).
    """
    ahs_cl, ahs_tl = _find_ahs_section(lines)
    if ahs_cl < 0:
        return 0, 0, 0, 0

    parts = lines[ahs_cl].strip().split()
    ahs_count = int(parts[0]) if parts and parts[0].isdigit() else 0

    if ahs_count > 0:
        supply_id, return_id = 0, 0
        supply_from_zone, return_to_zone = 0, 0
        for i in range(ahs_cl + 1, ahs_tl):
            line = lines[i].strip()
            if not line or line.startswith("!"):
                continue
            p = line.split()
            if len(p) >= 7:
                aid = int(p[0])
                zr = int(p[1])   # return zone
                zs = int(p[2])   # supply zone
                name = p[-1] if len(p) >= 8 else p[6]
                if "supply" in name.lower() or "press" in name.lower():
                    supply_id = aid
                    supply_from_zone = zs  # air comes FROM supply zone
                elif "return" in name.lower() or "exhaust" in name.lower():
                    return_id = aid
                    return_to_zone = zr    # air goes TO return zone
        if not supply_id and ahs_count >= 2:
            supply_id = 2
        if not return_id and ahs_count >= 1:
            return_id = 1
        return supply_id, return_id, supply_from_zone, return_to_zone

    # --- Create new AHS ---

    # Max zone ID
    zcl, zf, zt = _find_zone_section(lines)
    max_zid = 0
    if zf >= 0:
        for i in range(zf, zt):
            p = lines[i].strip().split()
            if p and p[0].lstrip("-").isdigit():
                zid = int(p[0])
                if zid > max_zid:
                    max_zid = zid

    # Max path ID
    max_pid = _get_max_path_id(lines)

    # Assign IDs
    s_rec = max_zid + 1
    s_sup = max_zid + 2
    r_rec = max_zid + 3
    r_sup = max_zid + 4

    sp_ret = max_pid + 1
    sp_sup = max_pid + 2
    sp_exh = max_pid + 3
    rp_ret = max_pid + 4
    rp_sup = max_pid + 5
    rp_exh = max_pid + 6

    s_ahs = 1
    r_ahs = 2

    lvl_pos = re_extract_level_positions(lines)
    ahs_lvl = lvl_pos[0]["level_index"] if lvl_pos else 1

    # 1. Add 4 AHS zones
    _, _, zt2 = _find_zone_section(lines)
    new_zones = [
        f"  {s_rec} 10  0  0  0  {ahs_lvl}  0.000  0 293.15 0 SUPPLY(Rec) -1 1 3 1 1 0 0 0\n",
        f"  {s_sup} 10  0  0  0  {ahs_lvl}  0.000  0 293.15 0 SUPPLY(Sup) -1 1 3 1 1 0 0 0\n",
        f"  {r_rec} 10  0  0  0  {ahs_lvl}  0.000  0 293.15 0 RETURN(Rec) -1 1 3 1 1 0 0 0\n",
        f"  {r_sup} 10  0  0  0  {ahs_lvl}  0.000  0 293.15 0 RETURN(Sup) -1 1 3 1 1 0 0 0\n",
    ]
    for i, zl in enumerate(new_zones):
        lines.insert(zt2 + i, zl)
    zcl2, _, _ = _find_zone_section(lines)
    old_zc = int(lines[zcl2].strip().split()[0])
    lines[zcl2] = re.sub(r'^\s*\d+', f'{old_zc + 4:>5}',
                          lines[zcl2], count=1)

    # 2. Add 6 AHS internal paths
    # IMPORTANT: Infrastructure paths must have ahs_id=0.
    # They are referenced FROM the AHS definition (as pr#, ps#, px#),
    # NOT assigned TO an AHS via the a# field.
    # Flag bitmask: 16=recirc(rec↔sup), 32=OA-intake(ambient→sup), 64=exhaust(rec→ambient)
    # All AHS infrastructure paths use e#=0 (no flow element).
    _, _, pf = _find_path_section(lines)
    pt2 = _find_path_terminator(lines, pf)
    ahs_paths = [
        # SUPPLY system infra — dir=6 = AHS internal direction
        _format_path_line(sp_ret, s_rec, s_sup, 0, ahs_lvl, 0.0, 0, 6, field_count, flow_elem=0, path_flag=16),  # pr#: recirc rec→sup
        _format_path_line(sp_sup, -1,    s_sup, 0, ahs_lvl, 0.0, 0, 6, field_count, flow_elem=0, path_flag=32),  # ps#: OA ambient→sup
        _format_path_line(sp_exh, s_rec, -1,    0, ahs_lvl, 0.0, 0, 6, field_count, flow_elem=0, path_flag=64),  # px#: exhaust rec→ambient
        # RETURN system infra
        _format_path_line(rp_ret, r_rec, r_sup, 0, ahs_lvl, 0.0, 0, 6, field_count, flow_elem=0, path_flag=16),  # pr#: recirc rec→sup
        _format_path_line(rp_sup, -1,    r_sup, 0, ahs_lvl, 0.0, 0, 6, field_count, flow_elem=0, path_flag=32),  # ps#: OA ambient→sup
        _format_path_line(rp_exh, r_rec, -1,    0, ahs_lvl, 0.0, 0, 6, field_count, flow_elem=0, path_flag=64),  # px#: exhaust rec→ambient
    ]
    for i, pl in enumerate(ahs_paths):
        lines.insert(pt2 + i, pl)
    pcl, _, _ = _find_path_section(lines)
    if pcl >= 0:
        old_pc = _get_path_count(lines, pcl)
        _set_path_count(lines, pcl, old_pc + 6)

    # 3. Add AHS definitions
    acl2, atl2 = _find_ahs_section(lines)
    ahs_defs = [
        f"! # zr# zs# pr# ps# px# color name\n",
        f"  {s_ahs} {s_rec} {s_sup} {sp_ret} {sp_sup} {sp_exh} -1 SUPPLY\n",
        f"\n",
        f"  {r_ahs} {r_rec} {r_sup} {rp_ret} {rp_sup} {rp_exh} -1 RETURN\n",
        f"\n",
    ]
    for i, al in enumerate(ahs_defs):
        lines.insert(atl2 + i, al)
    acl3, _ = _find_ahs_section(lines)
    lines[acl3] = re.sub(r'^\s*\d+', '    2',
                          lines[acl3], count=1)

    logger.info(
        "Created AHS: SUPPLY(id=%d,z=%d/%d,p=%d/%d/%d) "
        "RETURN(id=%d,z=%d/%d,p=%d/%d/%d)",
        s_ahs, s_rec, s_sup, sp_ret, sp_sup, sp_exh,
        r_ahs, r_rec, r_sup, rp_ret, rp_sup, rp_exh,
    )
    # Return: (supply_ahs_id, return_ahs_id, supply_from_zone, return_to_zone)
    # supply_from_zone = AHS supply zone (zs#) — FROM zone for pressurization paths
    # return_to_zone = AHS return zone (zr#) — TO zone for depressurization paths
    return s_ahs, r_ahs, s_sup, r_rec

# ---------------------------------------------------------------------------
# Validation & repair
# ---------------------------------------------------------------------------

def validate_and_repair_paths(lines):
    """Validate path section and repair issues. Returns warning messages."""
    msgs = []
    cl, hl, fd = _find_path_section(lines)
    if fd < 0:
        return ["WARNING: No path section found"]

    term = _find_path_terminator(lines, fd)

    # Collect paths
    entries = []
    for i in range(fd, term):
        p = lines[i].split()
        if p and p[0].lstrip("-").isdigit():
            entries.append((i, int(p[0]), lines[i]))

    path_ids = set(pid for _, pid, _ in entries)

    # Fix count
    declared = _get_path_count(lines, cl)
    actual = len(entries)
    if declared != actual:
        msgs.append(f"REPAIRED: Path count {declared}->{actual}")
        _set_path_count(lines, cl, actual)

    # Sort check
    ids = [pid for _, pid, _ in entries]
    if ids != sorted(ids):
        msgs.append("REPAIRED: Re-sorted paths by ID")
        entries.sort(key=lambda x: x[1])
        # Remove old, insert sorted
        for i in sorted([e[0] for e in entries], reverse=True):
            del lines[i]
        _, _, fd2 = _find_path_section(lines)
        t2 = _find_path_terminator(lines, fd2)
        for j, (_, _, text) in enumerate(entries):
            lines.insert(t2 + j, text)

    # Check icon->path references
    lvls = re_extract_level_positions(lines)
    orphans = []
    for lp in lvls:
        ih = lp["icon_header_line"]
        ni = lp["num_icons"]
        for j in range(ni):
            idx = ih + 1 + j
            if idx < len(lines):
                p = lines[idx].split()
                if len(p) >= 4:
                    try:
                        ref = int(p[3])
                        if ref > 0 and ref not in path_ids:
                            orphans.append((lp["level_index"], ref))
                    except (ValueError, IndexError):
                        pass
    if orphans:
        ms = [f"L{l}->P{p}" for l, p in orphans[:10]]
        msgs.append(f"WARNING: {len(orphans)} orphaned icon refs: {', '.join(ms)}")

    return msgs


def validate_prj_structure(lines):
    """Full structural validation. Returns list of issues."""
    issues = []

    # Zone count
    zcl, zf, zt = _find_zone_section(lines)
    if zcl >= 0:
        declared = int(lines[zcl].strip().split()[0])
        actual = sum(1 for i in range(zf, zt)
                     if lines[i].strip().split()
                     and lines[i].strip().split()[0].lstrip("-").isdigit())
        if declared != actual:
            issues.append(f"Zone count: declared={declared}, actual={actual}")

    # Path count
    pcl, _, pf = _find_path_section(lines)
    if pcl >= 0 and pf >= 0:
        declared = int(lines[pcl].strip().split()[0])
        pt = _find_path_terminator(lines, pf)
        actual = sum(1 for i in range(pf, pt)
                     if lines[i].strip().split()
                     and lines[i].strip().split()[0].lstrip("-").isdigit())
        if declared != actual:
            issues.append(f"Path count: declared={declared}, actual={actual}")

    # AHS path references
    acl, atl = _find_ahs_section(lines)
    if acl >= 0:
        ac = int(lines[acl].strip().split()[0])
        if ac > 0:
            _, _, pf2 = _find_path_section(lines)
            pt2 = _find_path_terminator(lines, pf2) if pf2 >= 0 else 0
            pids = set()
            for i in range(pf2, pt2):
                p = lines[i].split()
                if p and p[0].lstrip("-").isdigit():
                    pids.add(int(p[0]))
            for i in range(acl + 1, atl):
                line = lines[i].strip()
                if not line or line.startswith("!"):
                    continue
                p = line.split()
                if len(p) >= 7 and p[0].isdigit():
                    name = p[-1] if len(p) >= 8 else f"AHS#{p[0]}"
                    for fi, fn in [(3, "return"), (4, "supply"), (5, "exhaust")]:
                        rp = int(p[fi])
                        if rp > 0 and rp not in pids:
                            issues.append(
                                f"AHS '{name}' {fn} path refs missing P#{rp}"
                            )

    # Zone reference validation: check that all paths reference existing zones
    if zcl >= 0:
        zone_ids = set()
        zone_ids.add(-1)  # ambient zone
        zone_ids.add(0)
        for i in range(zf, zt):
            p = lines[i].strip().split()
            if p and p[0].lstrip("-").isdigit():
                zone_ids.add(int(p[0]))

        _, _, pf3 = _find_path_section(lines)
        pt3 = _find_path_terminator(lines, pf3) if pf3 >= 0 else 0
        for i in range(pf3, pt3):
            p = lines[i].split()
            if p and len(p) >= 10 and p[0].lstrip("-").isdigit():
                pid = int(p[0])
                try:
                    from_z = int(p[2])
                    to_z = int(p[3])
                    if from_z not in zone_ids:
                        issues.append(
                            f"Path P{pid}: from_zone {from_z} does not exist"
                        )
                    if to_z not in zone_ids:
                        issues.append(
                            f"Path P{pid}: to_zone {to_z} does not exist"
                        )
                except (ValueError, IndexError):
                    pass

    return issues

# ---------------------------------------------------------------------------
# Re-extract level positions
# ---------------------------------------------------------------------------

def re_extract_level_positions(lines):
    icon_headers = _find_icon_headers(lines)
    levels = []
    for ih in icon_headers:
        dl = ih - 1
        while dl >= 0 and lines[dl].strip().startswith("!"):
            dl -= 1
        if dl < 0:
            continue
        parts = lines[dl].split()
        if len(parts) >= 7:
            levels.append({
                "level_index": int(parts[0]),
                "level_name": parts[-1],
                "icon_header_line": ih,
                "level_def_line": dl,
                "num_icons": int(parts[3]),
            })
    return levels

# ---------------------------------------------------------------------------
# High-level: Build complete modified PRJ
# ---------------------------------------------------------------------------

def build_modified_prj(
    base_lines, temp_f, wind_mph, wind_dir,
    stair_configs, corridor_configs, roof_configs,
    fire_floor_level_num, ahs_systems=None,
):
    """Build a complete modified PRJ file for one analysis run.
    Returns (modified_lines, warnings_list).
    """
    lines = list(base_lines)
    all_warnings = []
    fc = _detect_path_field_count(lines)

    # Step 1-2: Output mode & weather
    set_output_mode(lines)
    set_weather(lines, temp_f, wind_mph, wind_dir)

    # Step 2a: Ensure we have a flow element for our paths
    fe = ensure_tool_flow_element(lines)

    # Step 2b: Ensure AHS (now creates internal paths too)
    # Returns: (supply_ahs_id, return_ahs_id, supply_from_zone, return_to_zone)
    supply_ahs_id, return_ahs_id, ahs_supply_zone, ahs_return_zone = ensure_ahs_systems(
        lines, field_count=fc, flow_elem=fe
    )

    # Max path ID now includes AHS internal paths
    next_pid = _get_max_path_id(lines) + 1

    # Step 3: Stair pressurization — all levels
    # Supply paths: air FROM AHS supply zone TO stair zone
    # IMPORTANT: Always use the AHS supply zone returned by ensure_ahs_systems.
    # The frontend's supply_zone may reference a zone that doesn't exist yet
    # (e.g., from a stale AHS config or a model without pre-existing AHS).
    for sc in stair_configs:
        for le in sc["levels"]:
            if le.get("ahs_id", 0) == 0 and supply_ahs_id:
                le["ahs_id"] = supply_ahs_id
        for le in sc["levels"]:
            zid = le.get("zone_id", 0)
            fr = le.get("flow_rate", 0)
            if zid == 0 or fr == 0:
                continue
            lps = re_extract_level_positions(lines)
            lnum = le["level_num"]
            lp = next((l for l in lps if l["level_index"] == lnum), None)
            if not lp:
                continue
            # For supply: supply_zone_id = AHS supply zone (where air comes from)
            # Always use the verified AHS supply zone, not the frontend value
            sz = ahs_supply_zone if ahs_supply_zone else le.get("supply_zone", 0)
            _, w = add_pressurization_at_level(
                lines, lp["icon_header_line"], lp["level_def_line"],
                lp["num_icons"], stair_zone_id=zid,
                supply_zone_id=sz,
                ahs_id=le.get("ahs_id", 0),
                level_num=lnum, flow_rate_scfm=fr,
                icon_type=le.get("icon_type", 128),
                icon_col=le.get("icon_col", 1),
                icon_row=le.get("icon_row", 1),
                next_path_id=next_pid, direction=2, field_count=fc,
                flow_elem=fe,
            )
            for x in w:
                all_warnings.append(f"[{sc.get('label','Stair')}] {x}")
            next_pid += 1

    # Step 4: Roof stair depressurization
    # Return paths: air FROM building zone TO AHS return zone
    for rc in roof_configs:
        zid = rc.get("zone_id", 0)
        fr = rc.get("flow_rate", 0)
        if zid == 0 or fr == 0:
            continue
        lps = re_extract_level_positions(lines)
        lnum = rc["level_num"]
        lp = next((l for l in lps if l["level_index"] == lnum), None)
        if not lp:
            continue
        aid = rc.get("ahs_id", 0)
        if aid == 0 and return_ahs_id:
            aid = return_ahs_id
        # For return: exhaust_zone = AHS return zone (where air goes to)
        # Always use the verified AHS return zone, not the frontend value
        ez = ahs_return_zone if ahs_return_zone else rc.get("exhaust_zone", 0)
        _, w = add_pressurization_at_level(
            lines, lp["icon_header_line"], lp["level_def_line"],
            lp["num_icons"], stair_zone_id=zid,
            supply_zone_id=ez,
            ahs_id=aid, level_num=lnum, flow_rate_scfm=fr,
            icon_type=rc.get("icon_type", 129),
            icon_col=rc.get("icon_col", 1),
            icon_row=rc.get("icon_row", 1),
            next_path_id=next_pid, direction=5, field_count=fc,
            flow_elem=fe,
        )
        for x in w:
            all_warnings.append(f"[Roof] {x}")
        next_pid += 1

    # Step 5: Corridor/floor depressurization at fire floor ONLY
    # Return paths: air FROM building zone TO AHS return zone
    for cc in corridor_configs:
        for le in cc["levels"]:
            if le.get("level_num", 0) != fire_floor_level_num:
                continue
            zid = le.get("zone_id", 0)
            fr = le.get("flow_rate", 0)
            if zid == 0 or fr == 0:
                continue
            lps = re_extract_level_positions(lines)
            lp = next((l for l in lps if l["level_index"] == le["level_num"]), None)
            if not lp:
                continue
            aid = le.get("ahs_id", 0)
            if aid == 0 and return_ahs_id:
                aid = return_ahs_id
            # For return: exhaust_zone = AHS return zone (where air goes to)
            # Always use the verified AHS return zone, not the frontend value
            ez = ahs_return_zone if ahs_return_zone else le.get("exhaust_zone", 0)
            _, w = add_pressurization_at_level(
                lines, lp["icon_header_line"], lp["level_def_line"],
                lp["num_icons"], stair_zone_id=zid,
                supply_zone_id=ez,
                ahs_id=aid, level_num=le["level_num"], flow_rate_scfm=fr,
                icon_type=le.get("icon_type", 129),
                icon_col=le.get("icon_col", 1),
                icon_row=le.get("icon_row", 1),
                next_path_id=next_pid, direction=5, field_count=fc,
                flow_elem=fe,
            )
            for x in w:
                all_warnings.append(f"[{cc.get('label','Corridor')}] {x}")
            next_pid += 1

    # Step 6: Validate & repair
    repair = validate_and_repair_paths(lines)
    all_warnings.extend(repair)

    # Step 7: Structural validation
    issues = validate_prj_structure(lines)
    for iss in issues:
        all_warnings.append(f"VALIDATION: {iss}")

    return lines, all_warnings
