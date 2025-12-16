# This script extracts settings from a 3MF flie (assumed to be sliced by Bambu Studio)
# by parsing the sliced GCode. It then translates those settings to the equivalent PrusaSlicer
# settings, then prints them as INI lines.
# TODO It may be possible to pull these from JSON or something.
import zipfile
import re
import sys

SAME_KEYS = [
    'bed_custom_model',
    'bed_custom_texture',
    'bridge_angle',
    'bridge_speed',
    'brim_type',
    'brim_width',
    'default_acceleration',
    'default_filament_profile',
    'default_print_profile',
    'draft_shield',
    'elefant_foot_compensation',
    'ensure_vertical_shell_thickness',
    'extruder_colour',
    'extruder_offset',
    'filament_colour',
    'filament_cost',
    'filament_density',
    'filament_diameter',
    'filament_max_volumetric_speed',
    'filament_minimal_purge_on_wipe_tower',
    'filament_notes',
    'filament_settings_id',
    'filament_soluble',
    'filament_type',
    'filament_vendor',
    'full_fan_speed_layer',
    'fuzzy_skin',
    'fuzzy_skin_thickness',
    'gcode_flavor',
    'host_type',
    'interface_shells',
    'ironing_spacing',
    'ironing_speed',
    'ironing_type',
    'layer_height',
    'machine_max_acceleration_e',
    'machine_max_acceleration_extruding',
    'machine_max_acceleration_retracting',
    'machine_max_acceleration_travel',
    'machine_max_acceleration_x',
    'machine_max_acceleration_y',
    'machine_max_acceleration_z',
    'machine_max_jerk_e',
    'machine_max_jerk_x',
    'machine_max_jerk_y',
    'machine_max_jerk_z',
    'machine_min_extruding_rate',
    'machine_min_travel_rate',
    'max_layer_height',
    'min_bead_width',
    'min_feature_size',
    'min_layer_height',
    'mmu_segmented_region_interlocking_depth',
    'mmu_segmented_region_max_width',
    'nozzle_diameter',
    'ooze_prevention',
    'post_process',
    'print_settings_id',
    'printer_model',
    'printer_notes',
    'printer_settings_id',
    'printer_technology',
    'printer_variant',
    'raft_contact_distance',
    'raft_expansion',
    'raft_first_layer_density',
    'raft_first_layer_expansion',
    'raft_layers',
    'resolution',
    'retract_before_wipe',
    'retract_length_toolchange',
    'retract_lift_above',
    'retract_lift_below',
    'retract_restart_extra',
    'retract_restart_extra_toolchange',
    'seam_position',
    'silent_mode',
    'single_extruder_multi_material',
    'skirt_distance',
    'skirt_height',
    'slice_closing_radius',
    'slicing_mode',
    'small_perimeter_speed',
    'standby_temperature_delta',
    'template_custom_gcode',
    'thick_bridges',
    'travel_acceleration',
    'travel_speed',
    'travel_speed_z',
    'use_firmware_retraction',
    'use_relative_e_distances',
    'wall_distribution_count',
    'wall_transition_angle',
    'wall_transition_filter_deviation',
    'wall_transition_length',
    'wipe',
    'wipe_tower_no_sparse_layers',
    'wipe_tower_rotation_angle',
    'wipe_tower_x',
    'wipe_tower_y',
]

# Maps Bamboo Studio keys to PrusaSlicer keys
MAPPED_KEYS = {
  # === EXACT VALUE FORMAT MATCHES ===
  # These have identical value formats and can be directly mapped

  # Temperature (single numeric values)
  'nozzle_temperature': 'temperature',
  'nozzle_temperature_initial_layer': 'first_layer_temperature',
  'hot_plate_temp': 'bed_temperature',
  'hot_plate_temp_initial_layer': 'first_layer_bed_temperature',

  # Layer height (single numeric)
  'initial_layer_print_height': 'first_layer_height',

  # Counts (single integers)
  'wall_loops': 'perimeters',
  'top_shell_layers': 'top_solid_layers',
  'bottom_shell_layers': 'bottom_solid_layers',
  'skirt_loops': 'skirts',

  # Infill (compatible formats)
  'sparse_infill_density': 'fill_density',  # Both use percentage
  'sparse_infill_pattern': 'fill_pattern',  # Both use pattern names

  # Cooling (single numeric)
  'fan_max_speed': 'max_fan_speed',
  'fan_min_speed': 'min_fan_speed',

  # Basic line width (single numeric)
  'line_width': 'extrusion_width',

  # Support settings (single numerics)
  'support_threshold_angle': 'support_material_threshold',
  'support_interface_top_layers': 'support_material_interface_layers',
  'support_interface_bottom_layers': 'support_material_bottom_interface_layers',
  'support_object_xy_distance': 'support_material_xy_spacing',
  'support_bottom_z_distance': 'support_material_bottom_contact_distance',

  # Pattern settings (strings)
  # TODO these pattern names may need to be translated
  #'top_surface_pattern': 'top_fill_pattern',
  #'bottom_surface_pattern': 'bottom_fill_pattern',

  # === MULTI-MATERIAL FORMAT (comma-separated values) ===
  # These work in PrusaSlicer but Bambu uses "value,value" while Prusa often uses single values
  # Include these if you want multi-material compatibility or plan to extract first value

  # Speeds (Bambu: "200,200" / Prusa: "200")
  'outer_wall_speed': 'external_perimeter_speed',
  'inner_wall_speed': 'perimeter_speed',
  'sparse_infill_speed': 'infill_speed',
  'internal_solid_infill_speed': 'solid_infill_speed',
  'top_surface_speed': 'top_solid_infill_speed',
  'gap_infill_speed': 'gap_fill_speed',
  'initial_layer_speed': 'first_layer_speed',
  'support_speed': 'support_material_speed',
  'support_interface_speed': 'support_material_interface_speed',

  # Line widths (same multi-material format issue)
  'outer_wall_line_width': 'external_perimeter_extrusion_width',
  'inner_wall_line_width': 'perimeter_extrusion_width',
  'sparse_infill_line_width': 'infill_extrusion_width',
  'internal_solid_infill_line_width': 'solid_infill_extrusion_width',
  'top_surface_line_width': 'top_infill_extrusion_width',
  'support_line_width': 'support_material_extrusion_width',

  # Retraction (multi-material format)
  'retraction_length': 'retract_length',
  'retraction_speed': 'retract_speed',
  'z_hop': 'retract_lift',
}


def extract_gcode_from_3mf(archive_path, gcode_path):
    """Extract GCODE text from a 3mf archive."""
    with zipfile.ZipFile(archive_path, 'r') as zf:
        # Try with and without trailing space
        try:
            gcode_bytes = zf.read(gcode_path)
        except KeyError:
            # Try with trailing space
            gcode_bytes = zf.read(gcode_path + ' ')
        return gcode_bytes.decode('utf-8')


def parse_settings_from_gcode(gcode_text):
    """Parse settings key-value pairs from GCODE comments.

    Settings are typically in format:
    ; key = value

    Returns a dict of key: value pairs.
    """
    settings = {}

    # Match lines that start with semicolon, have a key, equals sign, and value
    # Common patterns: "; key = value" or ";key = value"
    pattern = re.compile(r'^\s*;\s*([a-zA-Z_]+)\s*=\s*(.*)$')

    for line in gcode_text.splitlines():
        match = pattern.match(line)
        if not match:
            continue
        key = match.group(1)
        value = match.group(2).strip()
        settings[key] = value

    return settings


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 3mf_settings_extractor.py <path_to_3mf_file> [gcode_path_in_archive]", file=sys.stderr)
        print("\nExtracts settings from Bambu Studio 3mf files and maps them to PrusaSlicer format.", file=sys.stderr)
        print("\nDefault gcode_path_in_archive: Metadata/plate_1.gcode", file=sys.stderr)
        sys.exit(1)

    archive_path = sys.argv[1]
    gcode_path = sys.argv[2] if len(sys.argv) > 2 else 'Metadata/plate_1.gcode'

    # Build key mappings: MAPPED_KEYS takes precedence, then identity mapping for SAME_KEYS
    key_mappings = {**{k: k for k in SAME_KEYS}, **MAPPED_KEYS}

    # Extract and parse settings
    try:
        gcode_text = extract_gcode_from_3mf(archive_path, gcode_path)
        settings = parse_settings_from_gcode(gcode_text)
    except FileNotFoundError:
        print(f"Error: File not found: {archive_path}", file=sys.stderr)
        sys.exit(1)
    except KeyError as e:
        print(f"Error: Could not find '{gcode_path}' in archive", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Map and output settings
    output_count = 0
    for bambu_key, bambu_value in sorted(settings.items()):
        if bambu_key in key_mappings:
            prusa_key = key_mappings[bambu_key]
            print(f"{prusa_key} = {bambu_value}")
            output_count += 1

    # Print summary to stderr so it doesn't interfere with output redirection
    print(f"\n# Extracted {output_count} mapped settings from {len(settings)} total settings", file=sys.stderr)
    unmapped_count = len(settings) - output_count
    if unmapped_count > 0:
        print(f"# {unmapped_count} settings were not mapped (not in SAME_KEYS or MAPPED_KEYS)", file=sys.stderr)


if __name__ == '__main__':
    main()
