import pytest
from pytest_bdd import scenario, given, when, then, parsers
import toml

from cocli.main import app

import shlex

@pytest.fixture
def temp_data_dir(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "campaigns").mkdir()
    # Create a dummy config-template.toml
    config_template = {
        'campaign': {'name': '', 'tag': '', 'domain': '', 'company-slug': ''},
        'workflows': [],
        'import': {'format': ''},
        'google_maps': {'email': '', 'one_password_path': ''},
        'prospecting': {'locations': [], 'tools': [], 'queries': []}
    }
    with open(data_dir / "campaigns" / "config-template.toml", 'w') as f:
        toml.dump(config_template, f)
    yield data_dir

@scenario('../features/campaign.feature', 'User creates a new campaign')
def test_create_campaign():
    pass

@given('a cocli data directory', target_fixture="data_dir")
def data_dir(temp_data_dir, mocker):
    mocker.patch('cocli.commands.campaign.mgmt.get_cocli_base_dir', return_value=temp_data_dir)
    return temp_data_dir

@when(parsers.parse('the user runs "{command}"'), target_fixture="cli_result")
def run_command(runner, command):
    args = shlex.split(command)
    result = runner.invoke(app, args[1:]) # Skip 'cocli'
    return result

@then('the command should exit successfully')
def command_exits_successfully(cli_result):
    assert cli_result.exit_code == 0

@then(parsers.parse('a directory for the campaign "{campaign_slug}" should exist in the campaigns folder'))
def campaign_dir_exists(data_dir, campaign_slug):
    campaign_dir = data_dir / "campaigns" / campaign_slug
    assert campaign_dir.is_dir()

@then(parsers.parse('a "{filename}" file should exist in the campaign directory "{campaign_slug}"'))
def file_exists_in_campaign_dir(data_dir, filename, campaign_slug):
    file_path = data_dir / "campaigns" / campaign_slug / filename
    assert file_path.is_file()

@then(parsers.parse('the "{filename}" file in the campaign directory "{campaign_slug}" should contain \'{content}\''))
def file_contains_content(data_dir, filename, campaign_slug, content):
    file_path = data_dir / "campaigns" / campaign_slug / filename
    with open(file_path, 'r') as f:
        file_content = f.read()
    assert content in file_content
