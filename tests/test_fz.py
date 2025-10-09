
import pytest
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock
import re
import subprocess
import time

from cocli.main import app  # Assuming your Typer app is in cocli.main
from cocli.core.config import get_companies_dir
from cocli.core.utils import slugify

runner = CliRunner()

@pytest.fixture
def setup_test_company(tmp_path):
    companies_dir = tmp_path / "companies"
    companies_dir.mkdir()
    company_name = "Test Company"
    company_slug = slugify(company_name)
    company_dir = companies_dir / company_slug
    company_dir.mkdir()
    index_path = company_dir / "_index.md"
    index_path.write_text(f"""---
name: {company_name}
domain: testcompany.com
---
This is a test company.
""")
    with patch('cocli.core.config.get_companies_dir', return_value=companies_dir):
        yield company_name, company_slug

def test_fz_select_company_and_view(setup_test_company):
    company_name, _ = setup_test_company

    with patch('cocli.commands.fz.get_cached_items', return_value=[{'display': f'COMPANY: {company_name}', 'type': 'company', 'name': company_name, 'domain': 'testcompany.com'}]):
        with patch('cocli.commands.fz.run_fzf') as mock_run_fzf:
            mock_run_fzf.return_value = f'COMPANY: {company_name}'

            with patch('cocli.commands.fz.view_company') as mock_view_company:
                result = runner.invoke(app, ["fz"])

                assert result.exit_code == 0
                mock_view_company.assert_called_once_with(company_name=company_name)
