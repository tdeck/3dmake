from string import Template

SLICE_INFO_CONFIG_TEMPLATE = Template(
'''<?xml version="1.0" encoding="UTF-8"?>
<config>
  <header>
    <header_item key="X-BBL-Client-Type" value="slicer"/>
    <header_item key="X-BBL-Client-Version" value="02.00.03.54"/>
  </header>
  <plate>
    <metadata key="index" value="1"/>
    <metadata key="extruder_type" value="0"/>
    <metadata key="nozzle_volume_type" value="0"/>
    <metadata key="printer_model_id" value="$printer_model_id"/>
    <metadata key="nozzle_diameters" value="$nozzle_diameters"/>
    <metadata key="timelapse_type" value="0"/>
    <metadata key="prediction" value="$predicted_seconds"/>
    <metadata key="weight" value="$predicted_grams"/>
    <metadata key="outside" value="false"/>
    <metadata key="support_used" value="$supports_used"/>
    <metadata key="label_object_enabled" value="false"/>
    <metadata key="filament_maps" value="1"/>
    <object identify_id="52" name="Model" skipped="false" />
    <filament id="1" tray_info_idx="GFA00" type="PLA" color="#00AE42" used_m="0.13" used_g="0.41" />
    <warning msg="bed_temperature_too_high_than_filament" level="3" error_code ="1000C001"  />
    <layer_filament_lists>
      <layer_filament_list filament_list="0" layer_ranges="0 3" />
    </layer_filament_lists>
  </plate>
</config>''') # Whitespace around the doc will break Bambu Connect
