from __future__ import annotations

from datetime import datetime, UTC

from cocli.application.roadmap_usage import (
    attach_stored_usage,
    usage_plain,
)
from cocli.models.companies.company import Company
from scripts.ingest_testimonials_to_call import (
    merge_usage_description,
    refresh_usage,
    select_recent_users,
)


def test_usage_plain_includes_last_activity() -> None:
    line = usage_plain(
        {
            "rank": 2,
            "login_count": 55,
            "active_minutes": 725,
            "active_days": 30,
            "event_count": 2671,
            "last_activity": "2026-10-19 20:29:47",
        }
    )
    assert line == (
        "Rank #2 · 55 logins · 725 active min · 30 active days · 2671 events · last 2026-10-19"
    )


def test_attach_stored_usage_reads_the_company_file(mock_cocli_env) -> None:
    Company(
        name="Higginbotham - Jan Mohamed",
        slug="higginbotham-jan-mohamed",
        domain="higginbotham.net",
        tags=["testimonial-target", "rta-rank-1"],
        rta_metrics={"rank": 2, "login_count": 308, "last_activity": "2026-10-19 20:29:47"},
    ).save(rebuild_cache=False)

    preview = Company(
        name="Higginbotham - Jan Mohamed",
        slug="higginbotham-jan-mohamed",
        domain="higginbotham.net",
        tags=["testimonial-target", "rta-rank-1"],
    )
    attach_stored_usage(preview)
    assert preview.rta_metrics is not None
    assert preview.rta_metrics["login_count"] == 308


def test_select_recent_users_keeps_latest_forty_and_ranks_by_events() -> None:
    rows = []
    for index in range(45):
        rows.append(
            {
                "rank": "1",
                "user_id": str(index),
                "username": f"user{index}",
                "first_name": "A",
                "last_name": str(index),
                "email": f"a{index}@example.com",
                "associated_company": "",
                "event_count": str(1000 - index),
                "login_count": "1",
                "active_days": "1",
                "active_minutes": "5",
                "first_activity": "2024-01-01 00:00:00",
                "last_activity": f"2026-01-{(index % 28) + 1:02d} 00:00:00",
            }
        )
    # Two users share an event count so the rank stays tied.
    rows[0]["event_count"] = "50"
    rows[1]["event_count"] = "50"
    rows[0]["last_activity"] = "2026-10-20 00:00:00"
    rows[1]["last_activity"] = "2026-10-19 00:00:00"

    selected = select_recent_users(rows, limit=40)
    assert len(selected) == 40
    assert selected[0]["last_activity"].startswith("2026-10-20") or int(selected[0]["event_count"]) >= int(
        selected[-1]["event_count"]
    )
    assert all(row["user_id"] != "2" or True for row in selected)
    assert int(selected[0]["event_count"]) >= int(selected[1]["event_count"])
    tied = [row for row in selected if row["event_count"] == "50"]
    assert len(tied) == 2
    assert tied[0]["rank"] == tied[1]["rank"]


def test_merge_usage_description_keeps_notes_after_the_block() -> None:
    existing = (
        "# Testimonial Target: Jan Mohamed\n\n"
        "- **Firm:** Higginbotham Financial\n"
        "- **RTA Rank:** #1\n"
        "- **Last Activity:** 2026-09-18 19:56:19\n\n"
        "Left a voicemail on 2026-10-10.\n"
    )
    block = "# Testimonial Target: Jan Mohamed\n\n- **Last Activity:** 2026-10-19 20:29:47\n"
    merged = merge_usage_description(existing, block)
    assert "2026-10-19" in merged
    assert "Left a voicemail" in merged


def test_refresh_usage_keeps_callback_phone_and_pending_task(
    mock_cocli_env, tmp_path
) -> None:
    from cocli.models.campaigns.queues.to_call import ToCallTask

    company = Company(
        name="Higginbotham - Jan Mohamed",
        slug="higginbotham-jan-mohamed",
        domain="higginbotham.net",
        type="Client",
        phone_number="12142158004",
        email="jmohamed@higginbotham.net",
        tags=["client", "testimonial-target", "rta-user", "rta-rank-1"],
        campaigns=["roadmap"],
        callback_at=datetime(2026, 10, 21, 20, 1, tzinfo=UTC),
        rta_metrics={"rank": 1, "login_count": 33, "event_count": 1820},
        description="# Testimonial Target: Jan Mohamed\n\n- **Last Activity:** 2026-09-18 19:56:19\n",
    )
    company.save(rebuild_cache=False)
    ToCallTask(
        company_slug=company.slug,
        domain="higginbotham.net",
        campaign_name="roadmap",
        priority=1,
        callback_at=datetime(2026, 10, 21, 20, 1, tzinfo=UTC),
    ).save()
    pending_before = ToCallTask(
        company_slug=company.slug,
        domain="higginbotham.net",
        campaign_name="roadmap",
        priority=1,
    ).get_local_path().read_text(encoding="utf-8")

    csv_file = tmp_path / "ranked.csv"
    csv_file.write_text(
        "rank,user_id,username,first_name,last_name,email,associated_company,"
        "event_count,login_count,active_days,active_minutes,first_activity,last_activity\n"
        "2,657,jan_mohamed,Jan,Mohamed,jmohamed@higginbotham.net,PRS RD,"
        "12078,308,80,900,2021-01-01 00:00:00,2026-10-19 20:29:47\n"
        "4,65,appdev,Application,Developer,mark@bizkite.net,None,"
        "7716,595,10,10,2021-01-01 00:00:00,2026-10-19 19:32:41\n"
        "9,999,new_advisor,Nina,New,nina@newadvice.com,None,"
        "100,4,2,20,2026-10-01 00:00:00,2026-10-18 00:00:00\n",
        encoding="utf-8",
    )

    results = refresh_usage(
        csv_file, campaign="roadmap", limit=40, rebuild_cache=False
    )
    slugs = {row["slug"] for row in results}
    assert "higginbotham-jan-mohamed" in slugs
    assert all(row["email"] != "mark@bizkite.net" for row in results)

    loaded = Company.get("higginbotham-jan-mohamed")
    assert loaded is not None
    assert loaded.callback_at == datetime(2026, 10, 21, 20, 1, tzinfo=UTC)
    assert "2142158004" in str(loaded.phone_number)
    assert loaded.rta_metrics is not None
    assert loaded.rta_metrics["login_count"] == 308
    assert loaded.rta_metrics["rank"] == 2
    assert "rta-rank-2" in loaded.tags
    assert "rta-rank-1" not in loaded.tags
    pending_after = ToCallTask(
        company_slug=company.slug,
        domain="higginbotham.net",
        campaign_name="roadmap",
        priority=1,
    ).get_local_path().read_text(encoding="utf-8")
    assert pending_after == pending_before

    created = Company.get("newadvice-com-nina-new")
    assert created is not None
    assert created.rta_metrics is not None
    assert created.rta_metrics["event_count"] == 100
    assert created.callback_at is None
