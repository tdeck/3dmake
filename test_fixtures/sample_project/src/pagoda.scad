use <3dmake/preview.scad>

reduction = 4;

for (i = [0: 3]) {
    translate([0, 0, i*10]) {
        xy_preview_plane("level", i);
        cylinder(d1=16 - i*reduction, d2=20 - i*reduction, h=10, $fn=4);
    }
}

xz_preview_plane("diagonal_front");
rotate([0, 0, 45]) xz_preview_plane("face_front");
