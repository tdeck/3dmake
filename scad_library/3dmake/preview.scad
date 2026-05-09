use <_internal.scad>;

$THREEDMAKE_PREVIEW_PLANE = undef;
module xy_preview_plane(name, index=undef) {
    SIZE = 10000000;
    HEIGHT = 20;

    pname = (index != undef) ? str(name, "#", index) : name;

    if ($THREEDMAKE_PREVIEW_PLANE == undef) {
        _3dm_log_scalar("preview_plane_option", pname);
    } else if ($THREEDMAKE_PREVIEW_PLANE == pname) {
        _3dm_log_scalar("selected_preview_plane", pname);
        // This is a convex pentagon "pyramid" with a very wide base.
        // The apex points toward the viewer, and the short extra point
        // on the base indicates the +x direction.
        polyhedron(
            points=[ 
                // Base
                [SIZE, SIZE, 0],
                [-SIZE, SIZE, 0],
                [-SIZE, -SIZE, 0],
                [SIZE, -SIZE, 0],
                [SIZE + 1000, 0, 0], // +X direction indicator
                // Apex
                [0, 0, HEIGHT]
            ],
            faces=[ 
                // Pentagon base
                [0, 1, 2, 3, 4],
                // Triangle sides
                [1, 0, 5],
                [1, 5, 2],
                [5, 3, 2],
                [5, 4, 3],
                [0, 4, 5],
            ]
        );
    }
}

module xz_preview_plane(name, index=undef) {
    rotate([90, 0, 0]) xy_preview_plane(name, index);
}

module yz_preview_plane(name, index=undef) {
    rotate([0, 90, 0]) xy_preview_plane(name, index);
}
