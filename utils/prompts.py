from typing import List, Tuple, Any, Optional
from prompt_toolkit import prompt

def yes_or_no(question: str) -> bool:
    answer = prompt(f"{question} (y or n): ").strip()
    return answer == 'y'

def option_select(prompt_msg: str, options: List[Tuple[str, Any]], allow_none=False) -> Optional[Any]:
    while True:
        print(prompt_msg)
        index_to_opts: Dict[int, Any] = {}
        for i, (option_key, option_value) in enumerate(options):
            index_to_opts[i + 1] = option_value
            print(f"{i + 1}: {option_key}")

        res = prompt("Choose an option number, or type AGAIN to re-print the list: ").strip()

        if allow_none and res == '':
            return None
        if res.isdigit() and int(res) in index_to_opts:
            return index_to_opts[int(res)]
        elif res.lower() == 'again':
            continue
        else:
            print("That is not a valid option")
            continue
