import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from cocli.tui.app import CocliApp
from cocli.tui.widgets.campaign_selection import CampaignSelection
from cocli.tui.widgets.prospect_menu import ProspectMenu
from textual.widgets import ListView
from conftest import wait_for_screen, wait_for_widget

@pytest.mark.asyncio
@patch('cocli.tui.widgets.campaign_selection.get_all_campaign_dirs')
async def test_j_moves_down_in_campaign_list(mock_get_all_campaign_dirs):
    """Test that 'j' moves the highlight down in the CampaignSelection ListView."""
    # Arrange
    mock_campaign_a = MagicMock(spec=Path)
    mock_campaign_a.name = 'campaign_a'
    mock_campaign_b = MagicMock(spec=Path)
    mock_campaign_b.name = 'campaign_b'
    mock_get_all_campaign_dirs.return_value = [mock_campaign_b, mock_campaign_a]

    app = CocliApp()
    async with app.run_test() as driver:
        # Act
        await driver.press("space", "a")
        campaign_screen = await wait_for_widget(driver, CampaignSelection)
        list_view = campaign_screen.query_one(ListView)
        list_view.focus()

        # Assert initial state
        assert list_view.index == 0

        # Act
        await driver.press("j")

        # Assert final state
        assert list_view.index == 1


@pytest.mark.asyncio
@patch('cocli.tui.widgets.campaign_selection.get_all_campaign_dirs')
async def test_k_moves_up_in_campaign_list(mock_get_all_campaign_dirs):
    """Test that 'k' moves the highlight up in the CampaignSelection ListView."""
    # Arrange
    mock_campaign_a = MagicMock(spec=Path)
    mock_campaign_a.name = 'campaign_a'
    mock_campaign_b = MagicMock(spec=Path)
    mock_campaign_b.name = 'campaign_b'
    mock_get_all_campaign_dirs.return_value = [mock_campaign_b, mock_campaign_a]

    app = CocliApp()
    async with app.run_test() as driver:
        # Act
        await driver.press("space", "a")
        campaign_screen = await wait_for_widget(driver, CampaignSelection)
        list_view = campaign_screen.query_one(ListView)
        list_view.focus()
        list_view.index = 1  # Start at the second item

        # Assert initial state
        assert list_view.index == 1

        # Act
        await driver.press("k")

        # Assert final state
        assert list_view.index == 0


@pytest.mark.asyncio
@patch('cocli.tui.widgets.campaign_selection.get_all_campaign_dirs')
async def test_l_selects_item_in_campaign_list(mock_get_all_campaign_dirs, mocker):
    """Test that 'l' selects an item in the CampaignSelection ListView."""
    # Arrange
    mock_campaign_a = MagicMock(spec=Path)
    mock_campaign_a.name = 'campaign_a'
    mock_get_all_campaign_dirs.return_value = [mock_campaign_a]

    app = CocliApp()
    async with app.run_test() as driver:
        # Act
        await driver.press("space", "a")
        campaign_screen = await wait_for_widget(driver, CampaignSelection)
        list_view = campaign_screen.query_one(ListView)
        list_view.focus()
        spy = mocker.spy(campaign_screen, "post_message")

        await driver.press("l")

        # Assert that a CampaignSelected message was posted
        found_message = False
        for call in spy.call_args_list:
            message = call.args[0]
            if isinstance(message, CampaignSelection.CampaignSelected):
                assert message.campaign_name == 'campaign_a'
                found_message = True
                break
        assert found_message, "CampaignSelected message was not posted"


@pytest.mark.asyncio
@patch('cocli.tui.widgets.campaign_selection.get_all_campaign_dirs')
async def test_enter_selects_item_in_campaign_list(mock_get_all_campaign_dirs, mocker):
    """Test that 'enter' selects an item in the CampaignSelection ListView."""
    # Arrange
    mock_campaign_a = MagicMock(spec=Path)
    mock_campaign_a.name = 'campaign_a'
    mock_get_all_campaign_dirs.return_value = [mock_campaign_a]

    app = CocliApp()
    async with app.run_test() as driver:
        # Act
        await driver.press("space", "a")
        campaign_screen = await wait_for_widget(driver, CampaignSelection)
        list_view = campaign_screen.query_one(ListView)
        list_view.focus()
        spy = mocker.spy(campaign_screen, "post_message")

        await driver.press("enter")

        # Assert that a CampaignSelected message was posted
        found_message = False
        for call in spy.call_args_list:
            message = call.args[0]
            if isinstance(message, CampaignSelection.CampaignSelected):
                assert message.campaign_name == 'campaign_a'
                found_message = True
                break
        assert found_message, "CampaignSelected message was not posted"








@pytest.mark.asyncio


async def test_j_moves_down_in_prospect_menu():


    """Test that 'j' moves the highlight down in the ProspectMenu ListView."""


    app = CocliApp()


    async with app.run_test() as driver:


        await driver.press("space", "s")


        prospect_screen = await wait_for_screen(driver, ProspectMenu)


        list_view = prospect_screen.query_one(ListView)





        assert list_view.index == 0


        await driver.press("j")


        assert list_view.index == 1








@pytest.mark.asyncio


async def test_k_moves_up_in_prospect_menu():


    """Test that 'k' moves the highlight up in the ProspectMenu ListView."""


    app = CocliApp()


    async with app.run_test() as driver:


        await driver.press("space", "s")


        prospect_screen = await wait_for_screen(driver, ProspectMenu)


        list_view = prospect_screen.query_one(ListView)


        list_view.index = 1





        assert list_view.index == 1


        await driver.press("k")


        assert list_view.index == 0



