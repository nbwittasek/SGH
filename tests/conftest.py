"""Shared fixtures for end-to-end CONTAM simulation tests."""

import textwrap
from pathlib import Path

import pytest


@pytest.fixture
def tmp_project(tmp_path):
    """Create a temporary project directory."""
    proj = tmp_path / "test_project"
    proj.mkdir()
    return proj


def _build_prj_lines(
    *,
    num_levels=5,
    level_names=None,
    num_stairs=2,
    has_corridors=True,
    has_vestibules=True,
    has_floor_zones=False,
    has_ahs=True,
    has_flow_elements=True,
    num_flow_paths=0,
    temp_k=294.261,
    wind_ms=6.706,
    wind_dir=270.0,
):
    """Build a realistic synthetic CONTAM 3.4 PRJ file as a list of lines.

    Creates a building with `num_levels` levels, `num_stairs` stair shafts,
    corridors, vestibules, flow elements (S2V, V2C, EXT per stair),
    airflow paths, and AHS systems.
    """
    if level_names is None:
        level_names = [f"L{i+1}" for i in range(num_levels)]

    lines = []

    # -- Header --
    lines.append("ContamW 3.4.0.0 0\n")
    lines.append("TestBuilding_E2E\n")

    # -- Misc preamble (simplified) --
    lines.append("! project description\n")
    lines.append("Test building for end-to-end simulation\n")
    lines.append("! SketchPad\n")
    lines.append("50 80 0\n")

    # -- Weather --
    lines.append("! Ta Pb Ws Wd rh\n")
    lines.append(f"  {temp_k:.3f}  101325.0  {wind_ms:.3f}  {wind_dir:.1f}  0.5\n")

    # -- Output config --
    lines.append("! list doDlg pfsave zfsave zcsave\n")
    lines.append("   1     0      0      0      0\n")

    # -- Levels + Icon Data --
    # Each level has zones as icons plus a few path icons
    icons_per_level = 5  # base icon count
    lines.append(f"{num_levels} ! levels plus icon data:\n")

    # Zone IDs: assigned sequentially
    zone_id = 1
    zone_records = []  # (id, name, level_num, volume, temp_k)
    icon_data_by_level = {}  # level_index -> list of icon lines

    for li in range(num_levels):
        level_index = li + 1
        ref_ht = li * 3.5  # 3.5m per floor
        delta_ht = 3.5
        level_name = level_names[li]
        icon_lines = []

        # Stair zones
        for si in range(num_stairs):
            stair_name = f"Stair_{si+1}"
            zone_records.append((zone_id, stair_name, level_index, 50.0, temp_k))
            icon_lines.append(f"  6  {3 + si * 10}  3  {zone_id}\n")  # zone icon type 6
            zone_id += 1

        # Vestibule zones (one per stair)
        if has_vestibules:
            for si in range(num_stairs):
                vest_name = f"ST{si+1}_V"
                zone_records.append((zone_id, vest_name, level_index, 20.0, temp_k))
                icon_lines.append(f"  6  {5 + si * 10}  3  {zone_id}\n")
                zone_id += 1

        # Corridor zone
        if has_corridors:
            zone_records.append((zone_id, "Corridor", level_index, 200.0, temp_k))
            icon_lines.append(f"  6  20  3  {zone_id}\n")
            zone_id += 1

        # Floor zone
        if has_floor_zones:
            zone_records.append((zone_id, "Floor", level_index, 500.0, temp_k))
            icon_lines.append(f"  6  25  3  {zone_id}\n")
            zone_id += 1

        num_icons = len(icon_lines)
        icon_data_by_level[level_index] = icon_lines

        # Level definition line: index refHt delHt num_icons u1 u2 name
        lines.append(f"  {level_index}  {ref_ht:.3f}  {delta_ht:.3f}  {num_icons}  1  1  {level_name}\n")
        lines.append("! icn col row  #\n")
        lines.extend(icon_lines)

    # -- Zones --
    num_zones = len(zone_records)
    lines.append(f"{num_zones} ! zones:\n")
    lines.append("! Z# f  c  k  s  l#  relHt  Vol  T  P  name  color  u_Ht  u_V  u_T  u_P  cdaxis  cfd  cfd_name\n")
    for zid, zname, lnum, vol, tk in zone_records:
        lines.append(
            f"  {zid}  0  0  0  0  {lnum}  0.000  {vol:.1f}  {tk:.2f}  0  {zname}"
            f"  -1  1  3  1  1  0  0  0\n"
        )
    lines.append("-999\n")

    # -- Flow Elements --
    flow_elem_records = []  # (id, name, type)
    if has_flow_elements:
        eid = 1
        for si in range(num_stairs):
            sn = si + 1
            for suffix, etype in [("S2V", "plr_conn"), ("V2C", "plr_conn"), ("EXT", "plr_conn")]:
                name = f"Door-Stair{sn}-{suffix}"
                flow_elem_records.append((eid, name, etype))
                eid += 1
        # Corridor leakage element
        flow_elem_records.append((eid, "FLR.LK.Measured", "plr_conn"))
        eid += 1

    num_elems = len(flow_elem_records)
    lines.append(f"{num_elems} ! flow elements:\n")
    for feid, fname, fetype in flow_elem_records:
        # 3 lines per element
        lines.append(f"{feid} 23 {fetype} {fname}\n")
        lines.append(f"Flow element {fname}\n")
        lines.append(f" 1.0e-05 0.01 0.5 0.01 0.65 1\n")
    lines.append("-999\n")

    # -- Airflow Paths --
    # Create realistic paths connecting zones
    path_records = []
    pid = 1
    elem_name_map = {fe[0]: fe[1] for fe in flow_elem_records}

    if has_flow_elements and has_vestibules:
        for li in range(num_levels):
            level_index = li + 1
            for si in range(num_stairs):
                sn = si + 1
                # Find zone IDs for this stair and vestibule at this level
                stair_zid = None
                vest_zid = None
                corr_zid = None
                for zid, zname, lnum, vol, tk in zone_records:
                    if lnum == level_index:
                        if zname == f"Stair_{sn}":
                            stair_zid = zid
                        elif zname == f"ST{sn}_V":
                            vest_zid = zid
                        elif zname == "Corridor":
                            corr_zid = zid

                if stair_zid is None:
                    continue

                # S2V path: stair -> vestibule
                s2v_eid = next((e[0] for e in flow_elem_records if e[1] == f"Door-Stair{sn}-S2V"), None)
                if s2v_eid and vest_zid:
                    path_records.append((pid, 0, stair_zid, vest_zid, s2v_eid, 0, level_index, 1.0, 0.0, 75, 2))
                    pid += 1

                # V2C path: vestibule -> corridor
                v2c_eid = next((e[0] for e in flow_elem_records if e[1] == f"Door-Stair{sn}-V2C"), None)
                if v2c_eid and vest_zid and corr_zid:
                    path_records.append((pid, 0, vest_zid, corr_zid, v2c_eid, 0, level_index, 1.0, 0.0, 75, 2))
                    pid += 1

                # EXT path: stair -> ambient (-1)
                ext_eid = next((e[0] for e in flow_elem_records if e[1] == f"Door-Stair{sn}-EXT"), None)
                if ext_eid:
                    path_records.append((pid, 0, stair_zid, -1, ext_eid, 0, level_index, 1.0, 0.0, 75, 2))
                    pid += 1

            # Corridor leakage path
            corr_eid = next((e[0] for e in flow_elem_records if e[1] == "FLR.LK.Measured"), None)
            if corr_eid and corr_zid:
                path_records.append((pid, 0, corr_zid, -1, corr_eid, 0, level_index, 1.0, 0.0, 75, 2))
                pid += 1

    num_paths = len(path_records)
    lines.append(f"{num_paths} ! flow paths:\n")
    lines.append("! P# f  n#  m#  e#  f#  w#  a#  s#  c#  l#  X  Y  relHt  mult  wPset  wPmod  wazm  Fahs  Xmax  Xmin  icn  dir  clr  u_X1  u_X2  cfd  cfd_name  cfd_ptype  extra\n")
    for prec in path_records:
        pid_r, flag, from_z, to_z, eid, ahs, lnum, mult, fahs, icn, direction = prec
        lines.append(
            f"  {pid_r}  {flag}  {from_z}  {to_z}  {eid}  0  0  {ahs}  0  0  {lnum}"
            f"  0.000  0.000  0.000  {mult:.0f}  0  0  0  {fahs:.6e}  0  0  {icn}  {direction}"
            f"  -1  0  0  0  0  0  0\n"
        )
    lines.append("-999\n")

    # -- AHS --
    if has_ahs:
        # Create 2 AHS: SUPPLY and RETURN
        # Need supply/return zones
        s_rec = zone_id
        s_sup = zone_id + 1
        r_rec = zone_id + 2
        r_sup = zone_id + 3

        # AHS internal paths
        sp_ret = pid
        sp_sup = pid + 1
        sp_exh = pid + 2
        rp_ret = pid + 3
        rp_sup = pid + 4
        rp_exh = pid + 5

        lines.append("2 ! simple AHS:\n")
        lines.append("! # zr# zs# pr# ps# px# color name\n")
        lines.append(f"  1  {s_rec}  {s_sup}  {sp_ret}  {sp_sup}  {sp_exh}  -1  SUPPLY\n")
        lines.append("\n")
        lines.append(f"  2  {r_rec}  {r_sup}  {rp_ret}  {rp_sup}  {rp_exh}  -1  RETURN\n")
        lines.append("\n")

        # Add AHS zones to the zone section (we'll need to update zone count)
        # For simplicity, these zones are declared but their lines exist
        # The parser looks for the zone count line; we already wrote it above.
        # In a real file these zones would be in the zone section.
    else:
        lines.append("0 ! simple AHS:\n")
        lines.append("! # zr# zs# pr# ps# px# color name\n")

    lines.append("-999\n")

    # -- Trailing sections (simplified) --
    lines.append("0 ! contaminants:\n")
    lines.append("-999\n")
    lines.append("0 ! source/sinks:\n")
    lines.append("-999\n")
    lines.append("end file\n")

    return lines


@pytest.fixture
def five_level_prj(tmp_project):
    """Create a realistic 5-level, 2-stair building PRJ file."""
    lines = _build_prj_lines(
        num_levels=5,
        level_names=["B1", "L1", "L2", "L3", "Roof"],
        num_stairs=2,
        has_corridors=True,
        has_vestibules=True,
        has_floor_zones=False,
        has_ahs=True,
    )
    prj_path = tmp_project / "test_building.prj"
    prj_path.write_text("".join(lines), encoding="utf-8")
    return prj_path


@pytest.fixture
def ten_level_prj(tmp_project):
    """Create a 10-level, 2-stair building PRJ file."""
    lines = _build_prj_lines(
        num_levels=10,
        level_names=[f"L{i+1}" for i in range(10)],
        num_stairs=2,
        has_corridors=True,
        has_vestibules=True,
    )
    prj_path = tmp_project / "ten_level.prj"
    prj_path.write_text("".join(lines), encoding="utf-8")
    return prj_path


@pytest.fixture
def no_ahs_prj(tmp_project):
    """Create a building PRJ with no AHS systems."""
    lines = _build_prj_lines(
        num_levels=3,
        level_names=["L1", "L2", "L3"],
        num_stairs=1,
        has_corridors=True,
        has_vestibules=True,
        has_ahs=False,
    )
    prj_path = tmp_project / "no_ahs.prj"
    prj_path.write_text("".join(lines), encoding="utf-8")
    return prj_path


@pytest.fixture
def minimal_prj(tmp_project):
    """Create a minimal 2-level, 1-stair PRJ file."""
    lines = _build_prj_lines(
        num_levels=2,
        level_names=["L1", "L2"],
        num_stairs=1,
        has_corridors=True,
        has_vestibules=False,
        has_ahs=False,
        has_flow_elements=False,
    )
    prj_path = tmp_project / "minimal.prj"
    prj_path.write_text("".join(lines), encoding="utf-8")
    return prj_path


@pytest.fixture
def floor_zone_prj(tmp_project):
    """Create a PRJ with floor zones for depressurization."""
    lines = _build_prj_lines(
        num_levels=4,
        level_names=["L1", "L2", "L3", "L4"],
        num_stairs=1,
        has_corridors=True,
        has_vestibules=True,
        has_floor_zones=True,
        has_ahs=True,
    )
    prj_path = tmp_project / "floor_zones.prj"
    prj_path.write_text("".join(lines), encoding="utf-8")
    return prj_path


@pytest.fixture
def sample_xlog(tmp_project):
    """Create a synthetic CONTAM .xlog results file."""
    content = textwrap.dedent("""\
        CONTAM Results
        Project: TestBuilding_E2E
        Date: 2026-02-21

        Steady state results

        path  offset  dPmax  Fmax
           1    0.000   12.450    0.050
           2    0.000    8.300    0.030
           3    0.000   -5.200    0.020
           4    0.000   15.100    0.060
           5    0.000   10.750    0.040
           6    0.000   -3.800    0.015
           7    0.000    6.200    0.025
           8    0.000   11.900    0.045
           9    0.000    9.100    0.035
          10    0.000   -4.500    0.018
          11    0.000   13.200    0.052
          12    0.000    7.600    0.028
          13    0.000   -6.100    0.022
          14    0.000   14.800    0.058
          15    0.000   10.200    0.038
          16    0.000    2.500    0.010
          17    0.000    3.100    0.012
          18    0.000    4.700    0.019
          19    0.000    5.300    0.021
          20    0.000    8.800    0.033
    """)
    xlog_path = tmp_project / "test_results.xlog"
    xlog_path.write_text(content, encoding="utf-8")
    return xlog_path
