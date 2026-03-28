$THREEDMAKE_PREVIEW_PLANE = undef;
module xy_preview_plane(name) {
    MARKER = "___[3DMAKE]___";
    SIZE = 1000000;
    HEIGHT = 1;

    if ($THREEDMAKE_PREVIEW_PLANE == undef) {
        echo(MARKER, "preview_plane_option", name);
    } else if ($THREEDMAKE_PREVIEW_PLANE == name) {
        echo(MARKER, "selected_preview_plane", name);
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

module xz_preview_plane(name) {
    rotate([90, 0, 0]) xy_preview_plane(name);
}

module yz_preview_plane(name) {
    rotate([0, 90, 0]) xy_preview_plane(name);
}
