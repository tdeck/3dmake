def should_print_openscad_log(line: str) -> bool:
    """
    Returns true if the log line matches an ERROR, WARNING, or TRACE pattern.

    OpenSCAD doesn't provide a good way to filter logs on the command line so we must resort to this.
    """

    ALLOWED_PREFIXES = [ # From printutils.cc, some of these may never appear
        'ERROR:',
        'WARNING:',
        'TRACE:',
        'FONT-WARNING:',
        'EXPORT-WARNING:',
        'EXPORT-ERROR:',
        'PARSER-ERROR:',
        'ECHO:', # Logs from within OpenSCAD code; this will need better handling for multi-line echos
    ]

    # This may be inefficient but the number of log lines should be low
    for prefix in ALLOWED_PREFIXES:
        if line.startswith(prefix):
            return True

    return False
