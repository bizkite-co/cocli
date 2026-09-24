from __future__ import annotations

from pathlib import Path

from scripts.ingest_testimonials_to_call import (
    is_target_user,
    resolve_profile,
    ingest_testimonials,
)


def test_is_target_user_filters_internal_and_empty() -> None:
    # Internal usernames
    assert not is_target_user({"username": "appdev", "email": "mark@bizkite.net"})
    assert not is_target_user({"username": "joel", "email": "joel@roadmappartners.net"})
    assert not is_target_user({"username": "josh_almieri", "email": "josh@paradigmgoc.com"})
    assert not is_target_user({"username": "angela_gerber", "email": "angela@prsplan.com"})
    assert not is_target_user({"username": "aaron_scharf", "email": "ascharf@higginbotham.net"})
    assert not is_target_user({"username": "chip_slaughter", "email": "cslaughter@lpl.com"})

    # Empty email
    assert not is_target_user({"username": "bhunter", "email": ""})
    assert not is_target_user({"username": "bhunter", "email": "   "})

    # Valid external targets
    assert is_target_user({"username": "jan_mohamed", "email": "jmohamed@higginbotham.net"})
    assert is_target_user({"username": "kevin_klaas", "email": "KKlaas@higginbotham.net"})
    assert is_target_user({"username": "will_cassidy", "email": "will@cassidy-co.com"})


def test_resolve_profile_known_and_fallback() -> None:
    # Known profile: Jan Mohamed (user_id 657)
    p_jan = resolve_profile({"user_id": "657", "email": "jmohamed@higginbotham.net"})
    assert p_jan["slug"] == "higginbotham-jan-mohamed"
    assert p_jan["phone"] == "2142158004"

    # Known profile: Kevin Klaas (user_id 529)
    p_kevin = resolve_profile({"user_id": "529", "email": "KKlaas@higginbotham.net"})
    assert p_kevin["slug"] == "monarch-solutions-kevin-klaas"
    assert p_kevin["phone"] == "8158476229"

    # Fallback profile: Unknown user
    p_unknown = resolve_profile({
        "user_id": "9999",
        "first_name": "Alice",
        "last_name": "Smith",
        "email": "alice@advisors.com",
    })
    assert p_unknown["domain"] == "advisors.com"
    assert "alice" in p_unknown["slug"]


def test_ingest_testimonials_dry_run(tmp_path: Path) -> None:
    # Create sample CSV with a mix of targets and internal staff
    csv_file = tmp_path / "test_ranked.csv"
    csv_file.write_text(
        '"rank","user_id","username","first_name","last_name","email","associated_company","event_count","login_count","active_days","active_minutes","first_activity","last_activity"\n'
        '"1","657","jan_mohamed","Jan","Mohamed","jmohamed@higginbotham.net","PRS RD","1820","33","21","515","2026-07-01 19:44:17","2026-09-18 19:56:19"\n'
        '"3","65","appdev","Application","Developer","mark@bizkite.net","None","351","13","7","175","2026-06-30 01:52:38","2026-09-17 23:50:09"\n'
        '"12","64","chip_slaughter","Chip ","Slaughter III","cslaughter@LPL.com","Independent","77","4","4","45","2026-07-21 21:58:46","2026-09-14 15:49:52"\n'
        '"6","1174","don@blaunerfinancial.com","Don","Blauner","don@blaunerfinancial.com","None","235","1","1","35","2026-07-20 03:37:41","2026-07-20 04:32:30"\n'
    )

    results = ingest_testimonials(csv_path=csv_file, campaign="test_campaign", dry_run=True)
    # Should only include Jan Mohamed (#1) and Don Blauner (#6), skipping appdev (#3) and Chip Slaughter (#12)
    assert len(results) == 2
    assert results[0]["rank"] == 1
    assert results[0]["slug"] == "higginbotham-jan-mohamed"
    assert results[1]["rank"] == 6
    assert results[1]["slug"] == "blauner-financial-don-blauner"
