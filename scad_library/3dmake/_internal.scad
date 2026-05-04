module _3dm_log_scalar(tag, value) {
    MARKER = "___[3DMAKE]___";

    echo(MARKER, str(tag), str(value));
}
