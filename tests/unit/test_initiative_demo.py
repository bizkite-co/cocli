"""Shot-list resolution for initiative form-fill recordings."""

from __future__ import annotations

import pytest

from pathlib import Path

from cocli.application.initiative_demo import (
    _same_typed_value,
    format_value,
    lookup,
    passive_saved_selector,
    record_initiative_demo,
    resolve_steps,
)


def test_masked_percent_matches_the_typed_number() -> None:
    assert _same_typed_value("4", "4.0%")
    assert _same_typed_value("120000", "$120,000")
    assert not _same_typed_value("4", "40%")


def test_format_value_types_money_and_whole_decimals() -> None:
    assert format_value(120000.0, "money") == "120000"
    assert format_value(4.0, "decimal") == "4"
    assert format_value(6.5, "decimal") == "6.5"
    assert format_value(55, "integer") == "55"
    assert format_value(True, "yes_no") == "yes"
    assert format_value(False, "yes_no") == "no"


def test_lookup_reads_a_list_index() -> None:
    assert lookup({"passive_income": [{"description": "License income"}]}, "passive_income.0.description") == "License income"


def test_resolve_steps_reads_dotted_inputs() -> None:
    form = {
        "sections": [
            {
                "name": "client-information",
                "frame": {"start": "input[name='client.firstName']"},
                "steps": [
                    {
                        "action": "type",
                        "selector": "input[name='client.firstName']",
                        "value_from": "client.first_name",
                        "format": "text",
                    },
                    {"action": "radio", "name": "roadmap.strategy", "value": "OA"},
                    {"action": "click", "selector": "#add-asset"},
                    {
                        "action": "type",
                        "selector": "input[name='client.age']",
                        "value_from": "client.age",
                        "format": "integer",
                        "then": "stay",
                    },
                    {"action": "wait", "until": "enabled", "selector": "#spenddown-strats"},
                ],
            }
        ]
    }
    sections = resolve_steps(form, {"client": {"first_name": "Jordan", "age": 55}})
    assert sections[0]["steps"][0]["text"] == "Jordan"
    assert sections[0]["steps"][1]["text"] == "OA"
    assert sections[0]["steps"][2]["action"] == "click"
    assert sections[0]["steps"][3]["then"] == "stay"
    assert sections[0]["steps"][3]["text"] == "55"
    assert sections[0]["steps"][4]["action"] == "wait"


def test_passive_row_is_checked_on_the_saved_cells() -> None:
    description = "#passive-income-items tr.new-row input[name='description']"
    age = "#passive-income-items tr.new-row input[name='year-to-begin']"
    kept = "#passive-income-items tr.new-row input[name='is-continue-until-death']"
    assert passive_saved_selector(description) == (
        "#passive-income-items tr.passive-income-item td[name='description']"
    )
    assert passive_saved_selector(age) == (
        "#passive-income-items tr.passive-income-item td[name='age-to-begin']"
    )
    assert passive_saved_selector(kept) == (
        "#passive-income-items tr.passive-income-item "
        "input[name='is-continue-until-death']"
    )
    assert passive_saved_selector("input[name='roadmap.qpaCav']") is None


def test_resolve_steps_accepts_a_visible_wait() -> None:
    form = {
        "sections": [
            {
                "name": "retirement-goal-overview",
                "frame": {"start": "h2"},
                "steps": [
                    {"action": "wait", "until": "visible", "selector": "a.selectednav"},
                    {"action": "click", "selector": ".save-buttons input[name='SAVE']"},
                ],
            }
        ]
    }
    sections = resolve_steps(form, {})
    assert sections[0]["steps"][0]["until"] == "visible"
    assert sections[0]["steps"][1]["action"] == "click"


def test_resolve_steps_rejects_a_wait_without_a_selector() -> None:
    form = {
        "sections": [
            {
                "name": "client-information",
                "frame": {"start": "input"},
                "steps": [{"action": "wait", "until": "enabled"}],
            }
        ]
    }
    with pytest.raises(ValueError, match="until: enabled"):
        resolve_steps(form, {})


def test_lookup_reports_the_full_path() -> None:
    with pytest.raises(KeyError, match="goal.gogo.begin_age"):
        lookup({}, "goal.gogo.begin_age")


def test_live_recording_stops_before_the_browser_when_onepassword_is_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initiative = tmp_path / "rta"
    scenario = initiative / "scenarios" / "demo"
    scenario.mkdir(parents=True)
    (initiative / "demo-form.yaml").write_text(
        "sections:\n  - name: client\n    frame: {start: input}\n    steps: []\n",
        encoding="utf-8",
    )
    (scenario / "inputs.yaml").write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr("cocli.application.initiative_demo.get_op_secret", lambda _path: None)

    def launch_browser() -> None:
        raise AssertionError("browser should not launch")

    monkeypatch.setattr("cocli.application.initiative_demo.sync_playwright", launch_browser)
    with pytest.raises(RuntimeError, match="op://Private/Roadmappartners/password"):
        record_initiative_demo(initiative, "demo")
