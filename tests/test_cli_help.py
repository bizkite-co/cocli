import subprocess
from pytest_bdd import scenario, when, then, parsers

@scenario('../features/cli_help.feature', 'Display help when no arguments are provided')
def test_display_help_no_args():
    pass

@when('the user runs "cocli" with no arguments', target_fixture="cli_result")
def run_cocli_no_args():
    # We expect an error, so we don't check for success
    result = subprocess.run(['cocli'], capture_output=True, text=True)
    return result

@then('the command should exit with an error')
def check_exit_code(cli_result):
    assert cli_result.returncode != 0

@then(parsers.parse('the output should contain "{text}"'))
def check_output_contains(cli_result, text):
    assert text in cli_result.stdout or text in cli_result.stderr
