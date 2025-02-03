import sys
import subprocess
from typing import List, TextIO, Callable, Any, Dict, Optional
from dataclasses import dataclass, field
from pathlib import Path

from stl.mesh import Mesh

from utils.stream_wrappers import IndentStream
from coretypes import CommandOptions, FileSet, MeshMetrics

@dataclass(kw_only=True)
class Context:
    config_dir: Path
    options: Optional[CommandOptions]
    files: Optional[FileSet]
    explicit_overlay_arg: List[str]

    # These are attached by the measure-model step
    mesh: Optional[Mesh] = None
    mesh_metrics: Optional[MeshMetrics] = None


ActionName = str
ActionFunc = Callable[[Context, TextIO, TextIO], None] # stdout, verbose stdout

@dataclass(kw_only=True)
class Action:
    name: ActionName  # Must be unique
    gerund: Optional[str] = None # The -ing form of the name, if non-standard. E.g. "building"

    internal: bool = False
    isolated: bool  # True means the verb can't be run with other verbs
    needs_options: bool
    takes_input_file: bool
    implied_actions: List[ActionName] = field(default_factory=list)
    impl: ActionFunc

    def __call__(self, context: Context):
        debug_mode = self.needs_options and context.options.debug

        if self.isolated:
            # Isolated commands don't run in a pipeline so we don't indent their output
            return self.impl(context, sys.stdout, sys.stdout if debug_mode else subprocess.DEVNULL)
        else:
            if not self.internal:
                # I'm not sure what I should do if the internal action *does* produce output;
                # would be good to have a heading
                gerund_str = self.gerund or (self.name + 'ing')
                print(f"\n{gerund_str.title()}...")

            indent_stream = IndentStream(sys.stdout)
            return self.impl(context, indent_stream, indent_stream if debug_mode else subprocess.DEVNULL)

# This is populated whenever an action is declared with one of the action decorators
_action_registry: Dict[ActionName, Action] = {}

#
# Decorators
#
def _action_name(fn: Callable[..., Any]) -> str:
    return fn.__name__.replace('_', '-')

def _register_action(action: Action) -> Action:
    assert action.name not in _action_registry
    _action_registry[action.name] = action
    return action # For the caller's convenience

def isolated_action(
    func: Optional[ActionFunc] = None,
    needs_options:bool = False
):
    def wrap(func: ActionFunc) -> ActionFunc:
        return _register_action(Action(
            name=_action_name(func),
            isolated=True,
            takes_input_file=False,
            needs_options=needs_options,
            impl=func,
        ))

    if callable(func):
        return wrap(func)
    else:
        return wrap

def pipeline_action(
    func: Optional[ActionFunc] = None,
    gerund:Optional[str] = None,
    implied_actions: List[Action] = [],
    internal = False,  # Note: It would be better to call @internal_action for internal actions!
):
    # This is a little convenience thing we do so that the caller of pipeline_actions
    # needs to specify actions that actually exist, and we save them from calling .name
    implied_action_names = [a.name for a in implied_actions]

    def wrap(func: ActionFunc) -> ActionFunc:
        return _register_action(Action(
            name=_action_name(func),
            gerund=gerund,
            isolated=False,
            takes_input_file=True,
            needs_options=True,
            internal=internal,
            implied_actions=implied_action_names,
            impl=func,
        ))

    if callable(func):
        return wrap(func)
    else:
        return wrap

def internal_action(
    func: Optional[ActionFunc] = None,
    implied_actions: List[Action] = [],
):
    return pipeline_action(
        func=func,
        implied_actions=implied_actions,
        internal=True,
    )
