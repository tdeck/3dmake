def throw_subprogram_error(program_type: str, exit_code: int, debug: bool):
    if debug:
        print(f"Subprogram exited with return code {exit_code}")
    raise RuntimeError(
        f"The {program_type} program reported an error. "
        "There should be more info above this line."
    )
