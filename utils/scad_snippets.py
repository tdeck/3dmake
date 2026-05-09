NAMED_PROJECTION_CODE = {
    # These all receive the following vars:
    # stl_file, x_mid, y_mid, z_mid, x_size, y_size, z_size
    # Do not use // line comments in this code as line breaks will be removed
    '3sil': '''
        SPACING = 10;

        module model() {
            translate([-x_mid, -y_mid, -z_mid]) import(stl_file);
        }

        /* Top */
        translate([0, y_size/2 + z_size/2 + SPACING, 0]) projection() model();

        /* Left */
        translate([-x_size/2 - y_size/2 - SPACING, 0, 0]) projection() rotate([-90, 90, 0]) model();

        /* Front */
        projection() rotate([-90, 0, 0]) model();
    ''',
    'topsil': '''
        module model() {
            translate([-x_mid, -y_mid, -z_mid]) import(stl_file);
        }

        /* Top */
        projection() model();
    ''',
    'leftsil': '''
        module model() {
            translate([-x_mid, -y_mid, -z_mid]) import(stl_file);
        }

        /* Left */
        projection() rotate([-90, 90, 0]) model();
    ''',
    'rightsil': '''
        module model() {
            translate([-x_mid, -y_mid, -z_mid]) import(stl_file);
        }

        /* Right */
        projection() rotate([-90, -90, 0]) model();
    ''',
    'frontsil': '''
        module model() {
            translate([-x_mid, -y_mid, -z_mid]) import(stl_file);
        }

        /* Front */
        projection() rotate([-90, 0, 0]) model();
    ''',
    'backsil': '''
        module model() {
            translate([-x_mid, -y_mid, -z_mid]) import(stl_file);
        }

        /* Back */
        projection() rotate([-90, 180, 0]) model();
    '''
}

# Do not use // line comments in this code as line breaks will be removed
PREVIEW_PLANE_PROJECTION_CODE = '''
    module plane_aligned_model() {
        n_hat = normal_vector / norm(normal_vector);
        plane_right = right_vector / norm(right_vector);
        plane_up = cross(n_hat, plane_right); /* the +z dir (vertical planes) or +y dir (horizontal) */

        /* Build a rotation matrix with rows [plane_right, plane_up, n_hat].
           This maps: plane_right -> X, plane_up -> Y, n_hat -> Z.
           After this, projection(cut=true) cuts at z=0, which is the plane. */
        multmatrix([
            [plane_right[0], plane_right[1], plane_right[2], 0],
            [plane_up[0],    plane_up[1],    plane_up[2],    0],
            [n_hat[0],       n_hat[1],       n_hat[2],       0],
            [0,              0,              0,              1]
        ]) translate(-origin_vector) import(stl_file);
    }

    projection(cut=true) plane_aligned_model();
'''
