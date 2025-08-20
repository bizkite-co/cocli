from behave import Given, When, Then
from pathlib import Path
import subprocess
import os
import pexpect
import re

@Given('a cocli data directory with no companies')
def step_impl(context):
    context.data_dir = Path("./test_data/empty_data")
    context.data_dir.mkdir(parents=True, exist_ok=True)
    (context.data_dir / "companies").mkdir(parents=True, exist_ok=True)
    (context.data_dir / "people").mkdir(parents=True, exist_ok=True)
    context.env = os.environ.copy()
    context.env["COCLI_DATA_HOME"] = str(context.data_dir)

@Given('a cocli data directory with a company named "{company_name}"')
def step_impl(context, company_name):
    context.data_dir = Path(f"./test_data/{company_name.replace(' ', '_')}")
    context.data_dir.mkdir(parents=True, exist_ok=True)
    (context.data_dir / "companies").mkdir(parents=True, exist_ok=True)
    (context.data_dir / "people").mkdir(parents=True, exist_ok=True)
    company_path = context.data_dir / "companies" / company_name
    company_path.mkdir(exist_ok=True)
    (company_path / "_index.md").write_text(f"---\nname: {company_name}\n---\n\n# {company_name}\n")
    context.env = os.environ.copy()
    context.env["COCLI_DATA_HOME"] = str(context.data_dir)
    context.companies = [company_name]

@Given('a cocli data directory with companies {company_list}')
def step_impl(context, company_list):
    companies = re.findall(r'"([^"]*)"', company_list)
    context.data_dir = Path("./test_data/multiple_companies")
    context.data_dir.mkdir(parents=True, exist_ok=True)
    (context.data_dir / "companies").mkdir(parents=True, exist_ok=True)
    (context.data_dir / "people").mkdir(parents=True, exist_ok=True)
    for company in companies:
        company_path = context.data_dir / "companies" / company
        company_path.mkdir(exist_ok=True)
        (company_path / "_index.md").write_text(f"---\nname: {company}\n---\n\n# {company}\n")
    context.env = os.environ.copy()
    context.env["COCLI_DATA_HOME"] = str(context.data_dir)
    context.companies = companies

@Given('"{company_name}" has an _index.md file with YAML frontmatter and markdown content')
def step_impl(context, company_name):
    company_path = context.data_dir / "companies" / company_name
    index_md_content = """---
name: Example Corp
type: Software
---
This is some markdown content.
"""
    (company_path / "_index.md").write_text(index_md_content)

@Given('"{company_name}" has a tags.lst file with tags "{tags}"')
def step_impl(context, company_name, tags):
    company_path = context.data_dir / "companies" / company_name
    (company_path / "tags.lst").write_text(tags)

@Given('"{company_name}" has recent meetings within the last 6 months')
def step_impl(context, company_name):
    company_path = context.data_dir / "companies" / company_name
    meetings_dir = company_path / "meetings"
    meetings_dir.mkdir(exist_ok=True)
    # Create a dummy meeting file
    (meetings_dir / "2025-01-15-meeting.md").write_text("Meeting notes.")

@Given('"{company_name}" has no _index.md file')
def step_impl(context, company_name):
    # Ensure no _index.md file exists for this company
    company_path = context.data_dir / "companies" / company_name
    if (company_path / "_index.md").exists():
        (company_path / "_index.md").unlink()

@When('the user runs "cocli find"')
def step_impl(context):
    original_cocli_data_home = os.environ.get("COCLI_DATA_HOME")
    try:
        os.environ["COCLI_DATA_HOME"] = str(context.data_dir)
        command = ["uv", "run", "cocli", "find"]
        context.result = subprocess.run(command, capture_output=True, text=True, env=os.environ)
    finally:
        if original_cocli_data_home is not None:
            os.environ["COCLI_DATA_HOME"] = original_cocli_data_home
        else:
            if "COCLI_DATA_HOME" in os.environ:
                del os.environ["COCLI_DATA_HOME"]

@When('the user runs "cocli find {query}"')
def step_impl(context, query):
    original_cocli_data_home = os.environ.get("COCLI_DATA_HOME")
    try:
        os.environ["COCLI_DATA_HOME"] = str(context.data_dir)
        command = ["uv", "run", "cocli", "find", query]
        context.result = subprocess.run(command, capture_output=True, text=True, env=os.environ)
    finally:
        if original_cocli_data_home is not None:
            os.environ["COCLI_DATA_HOME"] = original_cocli_data_home
        else:
            if "COCLI_DATA_HOME" in os.environ:
                del os.environ["COCLI_DATA_HOME"]

@When('the user runs "cocli find" and interactively selects "{selection}" using arrow keys')
def step_impl(context, selection):
    original_cocli_data_home = os.environ.get("COCLI_DATA_HOME")
    os.environ["COCLI_DATA_HOME"] = str(context.data_dir)
    command = ["uv", "run", "cocli", "find"]
    child = pexpect.spawn(" ".join(command), env=os.environ, encoding='utf-8')
    child.expect(".*") # Expect initial output

    # Navigate to the selection
    for i, company in enumerate(context.companies):
        if company == selection:
            for _ in range(i):
                child.sendcontrol('j') # Send 'j' for down arrow
            break
    child.sendline('') # Press Enter to select
    child.expect(pexpect.EOF)
    context.result = child
    if original_cocli_data_home is not None:
        os.environ["COCLI_DATA_HOME"] = original_cocli_data_home
    else:
        del os.environ["COCLI_DATA_HOME"]
    if original_cocli_data_home is not None:
        os.environ["COCLI_DATA_HOME"] = original_cocli_data_home
    else:
        del os.environ["COCLI_DATA_HOME"]

@When('the user runs "cocli find" and interactively selects "{selection}" using \'j\' key')
def step_impl(context, selection):
    original_cocli_data_home = os.environ.get("COCLI_DATA_HOME")
    os.environ["COCLI_DATA_HOME"] = str(context.data_dir)
    command = ["uv", "run", "cocli", "find"]
    child = pexpect.spawn(" ".join(command), env=os.environ, encoding='utf-8')
    child.expect(".*") # Expect initial output

    # Navigate to the selection
    for i, company in enumerate(context.companies):
        if company == selection:
            for _ in range(i):
                child.send('j') # Send 'j' for down
            break
    child.sendline('') # Press Enter to select
    child.expect(pexpect.EOF)
    context.result = child
    if original_cocli_data_home is not None:
        os.environ["COCLI_DATA_HOME"] = original_cocli_data_home
    else:
        del os.environ["COCLI_DATA_HOME"]
    if original_cocli_data_home is not None:
        os.environ["COCLI_DATA_HOME"] = original_cocli_data_home
    else:
        del os.environ["COCLI_DATA_HOME"]

@Then('the command should exit')
def step_impl(context):
    if isinstance(context.result, subprocess.CompletedProcess):
        assert context.result.returncode != 0
    elif isinstance(context.result, pexpect.spawn):
        assert context.result.exitstatus != 0

@Then('the command should exit successfully')
def step_impl(context):
    if isinstance(context.result, subprocess.CompletedProcess):
        assert context.result.returncode == 0, f"Command failed with error: {context.result.stderr}"
    elif isinstance(context.result, pexpect.spawn):
        assert context.result.exitstatus == 0, f"Command failed with error: {context.result.before}"

@Then('the output should display find help')
def step_impl(context):
    if isinstance(context.result, subprocess.CompletedProcess):
        assert "Usage: cocli find" in context.result.stdout
    elif isinstance(context.result, pexpect.spawn):
        assert "Usage: cocli find" in context.result.before

@Then('the output should indicate "{message}"')
def step_impl(context, message):
    if isinstance(context.result, subprocess.CompletedProcess):
        assert message in context.result.stdout
    elif isinstance(context.result, pexpect.spawn):
        assert message in context.result.before

@Then('the output should display a selectable list containing {company_list}')
def step_impl(context, company_list):
    companies = re.findall(r'"([^"]*)"', company_list)
    output = context.result.stdout if isinstance(context.result, subprocess.CompletedProcess) else context.result.before
    for company in companies:
        assert company in output, f"'{company}' not found in output: {output}"

@Then('the output should display details for "{company_name}"')
def step_impl(context, company_name):
    output = context.result.stdout if isinstance(context.result, subprocess.CompletedProcess) else context.result.before
    assert f"--- Company Details ---" in output
    assert f"name: {company_name}" in output

@Then('the output should display "--- Company Details ---"')
def step_impl(context):
    output = context.result.stdout if isinstance(context.result, subprocess.CompletedProcess) else context.result.before
    assert "--- Company Details ---" in output

@Then('the output should display "--- Tags ---"')
def step_impl(context):
    output = context.result.stdout if isinstance(context.result, subprocess.CompletedProcess) else context.result.before
    assert "--- Tags ---" in output

@Then('the output should display tags "{tags}"')
def step_impl(context, tags):
    assert tags in context.result.stdout

@Then('the output should display "--- Recent Meetings ---"')
def step_impl(context):
    assert "--- Recent Meetings ---" in context.result.stdout

@Then('the output should display recent meeting dates and names')
def step_impl(context):
    assert "2025-01-15-meeting.md" in context.result.stdout

@Then('the output should display "To view all meetings: cocli view-meetings {company_name}"')
def step_impl(context, company_name):
    assert f"To view all meetings: cocli view-meetings {company_name}" in context.result.stdout

@Then('the output should display "To add a new meeting: cocli add-meeting {company_name}"')
def step_impl(context, company_name):
    assert f"To add a new meeting: cocli add-meeting {company_name}" in context.result.stdout
@Given('the user selects "{selection}" from the find selection list')
def step_impl(context, selection):
    original_cocli_data_home = os.environ.get("COCLI_DATA_HOME")
    try:
        os.environ["COCLI_DATA_HOME"] = str(context.data_dir)
        command = ["uv", "run", "cocli", "find"]
        child = pexpect.spawn(" ".join(command), env=os.environ, encoding='utf-8')
        child.expect(".*") # Expect initial output

        # Navigate to the selection
        for i, company in enumerate(context.companies):
            if company == selection:
                for _ in range(i):
                    child.sendcontrol('j') # Send 'j' for down arrow
                break
        child.sendline('') # Press Enter to select
        child.expect(pexpect.EOF)
        context.result = child
    finally:
        if original_cocli_data_home is not None:
            os.environ["COCLI_DATA_HOME"] = original_cocli_data_home
        else:
            if "COCLI_DATA_HOME" in os.environ:
                del os.environ["COCLI_DATA_HOME"]
