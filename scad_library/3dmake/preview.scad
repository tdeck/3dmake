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
        // This is a pyramid with a very wide base. The point points toward the viewer.
        polyhedron(
            points=[ 
                // Base
                [SIZE,SIZE,0],
                [SIZE,-SIZE,0],
                [-SIZE,-SIZE,0],
                [-SIZE,SIZE,0], 
                // Apex
                [0,0,HEIGHT]
            ],
            faces=[ 
                // Triangle sides
                [0,1,4],[1,2,4],[2,3,4],[3,0,4],
                // Square base
                [1,0,3],[2,1,3] 
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
