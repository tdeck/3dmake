'''
Since 3DMake's end-to-end tests are run in a shell subprocess, we sometimes
need a way to mock certain things without being able to access the loaded
classes. This is a basic way to do that.
'''
import os

def in_test_mode() -> bool:
    return bool(os.environ.get('_3DMAKE_TEST_MODE', None))

def test_flag_set(name: str) -> bool:
    return name in os.environ.get('_3DMAKE_TEST_FLAGS', '').split(',')
