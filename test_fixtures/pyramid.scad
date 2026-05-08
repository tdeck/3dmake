// Simple pyramid test model for 3dmake tests
module pyramid(size = 10, height = 15) {
    linear_extrude(height = height, scale = 0) {
        square(size, center = true);
    }
}

pyramid();