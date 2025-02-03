import importlib
import pkgutil

from .framework import Context
from .framework import _action_registry as ALL_ACTIONS

# Register and re-export all the action functions
for loader, module_name, is_pkg in pkgutil.iter_modules(__path__):
    if module_name.endswith('_actions') or module_name.endswith('_action'):
        module = importlib.import_module(f"{__name__}.{module_name}")

        # Re-export all items that don't start with "_"
        for item_name in dir(module):
            if not item_name.startswith("_"):
                globals()[item_name] = getattr(module, item_name)

