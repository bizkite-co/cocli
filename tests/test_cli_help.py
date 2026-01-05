import subprocess
from pytest_bdd import scenario, when, then, parsers

@scenario('../features/cli_help.feature', 'Display help when no arguments are provided')
def test_display_help_no_args():
    pass

@when('the user runs "cocli" with no arguments', target_fixture="cli_result")
def run_cocli_no_args():
    # Use python -m cocli.main to support non-packaged environments
    import sys
    import os
    env = os.environ.copy()
    env["PYTHONPATH"] = "."
    result = subprocess.run([sys.executable, '-m', 'cocli.main'], capture_output=True, text=True, env=env)
    return result

@then('the command should exit with an error')
def check_exit_code(cli_result):
    assert cli_result.returncode != 0

@then(parsers.parse('the output should contain "{text}"'))
def check_output_contains(cli_result, text):
    assert text in cli_result.stdout or text in cli_result.stderr
