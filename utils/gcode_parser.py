import re
from pathlib import Path
from dataclasses import dataclass

E_PATTERN = re.compile(r'E(-?\d*\.?\d+)')
X_PATTERN = re.compile(r'X(-?\d*\.?\d+)')
Y_PATTERN = re.compile(r'Y(-?\d*\.?\d+)')
Z_PATTERN = re.compile(r'Z(-?\d*\.?\d+)')
F_PATTERN = re.compile(r'F(\d+)')

@dataclass
class FeatureStats:
    length_mm: float = 0.0
    time_seconds: float = 0.0
    moves: int = 0

def parse_gcode_stats(gcode_path: Path) -> dict[str, FeatureStats]:
    """
    Parse G-code file and return filament usage by feature type
    Mostly Claude code so may have unknown bugs.
    """

    stats = {}
    current_type = "Unknown"

    # G-code parsing state
    current_x, current_y, current_z = 0.0, 0.0, 0.0
    current_e = 0.0
    current_feedrate = 1800  # Default feedrate mm/min
    absolute_extrusion = True  # Track extrusion mode (M82 vs M83) - default to absolute
    retraction_debt = 0.0  # Track how much filament was retracted and needs to be paid back

    with open(gcode_path, 'r') as f:
        for line in f:
            line = line.strip()

            # Skip empty lines (small optimization)
            if not line:
                continue

            # Track feature type changes
            if line.startswith(';TYPE:'):
                current_type = line[6:]  # Remove ';TYPE:'
                if current_type not in stats:
                    stats[current_type] = FeatureStats()

            # Handle extruder mode commands
            elif line.startswith('M82'):
                absolute_extrusion = True
            elif line.startswith('M83'):
                absolute_extrusion = False

            # Handle extruder resets
            elif line.startswith('G92 E'):
                e_match = E_PATTERN.search(line)
                if e_match:
                    current_e = float(e_match.group(1))
                    # Don't reset retraction debt - retractions before resets still need to be paid back

            # Parse G1 movement commands (extrusion)
            elif line.startswith('G1 ') and 'E' in line:
                # Extract coordinates and extrusion using pre-compiled patterns
                x_match = X_PATTERN.search(line)
                y_match = Y_PATTERN.search(line)
                z_match = Z_PATTERN.search(line)
                e_match = E_PATTERN.search(line)
                f_match = F_PATTERN.search(line)

                # Update position
                new_x = float(x_match.group(1)) if x_match else current_x
                new_y = float(y_match.group(1)) if y_match else current_y
                new_z = float(z_match.group(1)) if z_match else current_z

                # Update feedrate if specified
                if f_match:
                    current_feedrate = float(f_match.group(1))

                # Calculate movement distance
                distance = ((new_x - current_x)**2 + (new_y - current_y)**2 + (new_z - current_z)**2)**0.5

                # Calculate extrusion amount
                if e_match:
                    e_value = float(e_match.group(1))

                    if absolute_extrusion:
                        # In absolute mode, calculate delta from previous position
                        e_delta = e_value - current_e
                        current_e = e_value
                    else:
                        # In relative mode, the E value is the delta
                        e_delta = e_value

                    # Handle retraction/unretraction accounting
                    if e_delta < -0.0001:
                        # This is a retraction - track the debt
                        retraction_debt += abs(e_delta)
                    elif e_delta > 0.0001:
                        # This is positive extrusion - check if it's just paying back retraction debt
                        if retraction_debt > 0:
                            # Pay back retraction debt first
                            debt_payment = min(e_delta, retraction_debt)
                            retraction_debt -= debt_payment
                            productive_extrusion = e_delta - debt_payment
                        else:
                            # No debt, all extrusion is productive
                            productive_extrusion = e_delta

                        # Only count productive extrusion (not unretraction)
                        if productive_extrusion > 0.0001:
                            if current_type not in stats:
                                stats[current_type] = FeatureStats()

                            stats[current_type].length_mm += productive_extrusion
                            stats[current_type].moves += 1

                            # Estimate time (feedrate is in mm/min, convert to seconds)
                            if distance > 0:
                                move_time = (distance / current_feedrate) * 60
                                stats[current_type].time_seconds += move_time

                # Update current position
                current_x, current_y, current_z = new_x, new_y, new_z

    return stats

