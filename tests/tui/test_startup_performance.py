import pytest
import time
import asyncio
import shutil
from cocli.tui.app import CocliApp

@pytest.mark.asyncio
async def test_startup_performance_non_blocking(mock_cocli_env, mocker):
    """
    Ensures that the App starts and becomes responsive within 5 seconds, 
    even if the cache is missing or large.
    """
    # Mock campaign to None
    mocker.patch('cocli.core.config.get_campaign', return_value=None)
    mocker.patch('cocli.application.search_service.get_campaign', return_value=None)

    # We use real services to test actual filesystem/DuckDB overhead
    # but we ensure NO company_cache exists to force the 'cold' path
    from cocli.core.cache import get_cache_path
    
    cache_dir = get_cache_path()
    if cache_dir.exists():
        if cache_dir.is_dir():
            shutil.rmtree(cache_dir)
        else:
            cache_dir.unlink()

    app = CocliApp()
    
    start_time = time.perf_counter()
    
    try:
        # We use a 5 second timeout for the entire 'run_test' context
        async with asyncio.timeout(5.0):
            async with app.run_test() as _:
                # App is considered 'started' once the first view is mounted
                # and driver is ready.
                elapsed = time.perf_counter() - start_time
                assert elapsed < 5.0, f"Startup took too long: {elapsed:.2f}s"
                
                # Check that we have a UI (MenuBar should be yielded first)
                from cocli.tui.app import MenuBar
                assert len(app.query(MenuBar)) == 1
                
    except asyncio.TimeoutError:
        pytest.fail("TUI failed to start within 5 seconds (Timed out)")

@pytest.mark.asyncio
async def test_data_load_performance(mock_cocli_env, mocker):
    """
    Ensures that at least one company is visible in the list within 10 seconds.
    """
    from cocli.tui.widgets.company_list import CompanyList
    from textual.widgets import ListView
    from cocli.core.paths import paths
    from cocli.core.cache import build_cache
    from slugify import slugify

    # Populate data
    for i in range(5):
        name = f"Test Co {i}"
        slug = slugify(name)
        comp_dir = paths.companies / slug
        comp_dir.mkdir(parents=True, exist_ok=True)
        (comp_dir / "_index.md").write_text(f"---\nname: {name}\nemail: test{i}@example.com\ntags: [test]\n---")
    
    # Mock campaign to None so search uses global cache
    mocker.patch('cocli.core.config.get_campaign', return_value=None)
    mocker.patch('cocli.application.search_service.get_campaign', return_value=None)
    
    build_cache()

    app = CocliApp()
    
    start_time = time.perf_counter()
    
    try:
        async with asyncio.timeout(10.0):
            async with app.run_test() as driver:
                # 1. Wait for CompanyList to be available
                while True:
                    lists = list(app.query(CompanyList))
                    if lists and lists[0].visible:
                        break
                    await driver.pause(0.1)
                    if time.perf_counter() - start_time > 10.0:
                        pytest.fail("CompanyList widget never appeared")

                # 2. Wait for ListView to have data
                list_view = app.query_one("#company_list_view", ListView)
                
                while len(list_view.children) == 0:
                    await driver.pause(0.2)
                    if time.perf_counter() - start_time > 10.0:
                        pytest.fail("No data loaded into ListView within 10 seconds")
                
                elapsed = time.perf_counter() - start_time
                assert len(list_view.children) > 0
                assert elapsed < 10.0, f"Data load took too long: {elapsed:.2f}s"
                
    except asyncio.TimeoutError:
        pytest.fail("Data load test timed out (10s limit)")
