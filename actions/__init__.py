import importlib
import pkgutil
from collections import OrderedDict

from .framework import Context
import actions.setup_action as setup_action
import actions.new_action as new_action
import actions.help_action as help_action
import actions.version_action as version_action
import actions.edit_actions as edit_actions
import actions.build_action as build_action
import actions.measure_action as measure_action
import actions.info_action as info_action
import actions.orient_action as orient_action
import actions.preview_action as preview_action
import actions.slice_action as slice_action
import actions.print_action as print_action
import actions.library_actions as library_actions
import actions.list_config_actions as list_config_actions
import actions.image_action as image_action

_actions_in_order = [
    setup_action.setup,
    new_action.new,

    build_action.build,
    measure_action.measure_model,
    info_action.info,
    orient_action.orient,
    image_action.image,
    preview_action.preview,
    slice_action.slice,
    print_action.print,

    list_config_actions.list_profiles,
    list_config_actions.list_overlays,

    edit_actions.edit_model,
    edit_actions.edit_overlay,
    edit_actions.edit_profile,
    edit_actions.edit_global_config,

    library_actions.list_libraries,
    library_actions.install_libraries,

    help_action.help,
    version_action.version,
]

ALL_ACTIONS_IN_ORDER = OrderedDict()

for a in _actions_in_order:
    ALL_ACTIONS_IN_ORDER[a.name] = a
