from typing import Any, Union

def throw_subprogram_error(program_type: str, exit_code: int, debug: bool):
    if debug:
        print(f"Subprogram exited with return code {exit_code}")
    raise RuntimeError(
        f"The {program_type} program reported an error. "
        "There should be more info above this line."
    )

def check_if_value_in_options(thing_name: str, value: str, options: Union[list[str], dict[str, Any]]) -> None:
    if value not in options:
        opt_names = options if isinstance(options, list) else options.keys()
        raise RuntimeError(f"No {thing_name} named {value}, options are {', '.join(opt_names)}")
