import typer

def register_commands(app: typer.Typer):
    from . import add
    from . import add_email
    from . import add_meeting
    from . import campaign
    from . import compile_enrichment
    from . import context
    from . import deduplicate
    from . import enrich_customers
    from . import enrich_shopify_data
    from . import exclude
    from . import flag_email_providers
    from . import fz
    from . import import_companies
    from . import import_customers
    from . import import_data
    from . import import_turboship
    from . import ingest_google_maps_csv
    from . import init
    from . import meetings
    from . import process_shopify_scrapes
    from . import render
    from . import render_prospects_kml
    from . import scrape_shopify
    from . import status
    from . import sync
    from . import view
    from . import google_maps

    app.command(name="add")(add.add)
    app.command(name="add-email")(add_email.add_email)
    app.command(name="add-meeting")(add_meeting.add_meeting)
    app.command(name="context")(context.context)
    app.command(name="exclude")(exclude.exclude)
    app.command(name="fz")(fz.fz)
    app.command(name="google-maps-cache-to-company-files")(import_companies.google_maps_cache_to_company_files)
    app.command(name="import-customers")(import_customers.import_customers)
    app.command(name="import-data")(import_data.import_data)
    app.command(name="import-turboship")(import_turboship.import_turboship)
    app.command(name="google-maps-csv-to-google-maps-cache")(ingest_google_maps_csv.google_maps_csv_to_google_maps_cache)
    app.command(name="init")(init.init)
    app.command(name="next")(meetings.next_meetings)
    app.command(name="open-company-folder")(view.open_company_folder)
    app.command(name="process-shopify-scrapes")(process_shopify_scrapes.process_shopify_scrapes)
    app.command(name="recent")(meetings.recent_meetings)
    app.command(name="render-prospects-kml")(render_prospects_kml.render_prospects_kml)
    app.command(name="scrape-shopify-myip")(scrape_shopify.scrape_shopify_myip)
    app.command(name="status")(status.status)
    app.command(name="sync")(sync.sync)
    app.command(name="view-company")(view.view_company)
    app.command(name="view-meetings")(view.view_meetings)
    app.command(name="enrich-customers")(enrich_customers.enrich_customers)
    app.command(name="enrich-shopify-data")(enrich_shopify_data.enrich_shopify_data)
    app.command(name="compile-enrichment")(compile_enrichment.compile_enrichment)
    app.command(name="flag-email-providers")(flag_email_providers.flag_email_providers)

    app.add_typer(campaign.app, name="campaign")
    app.add_typer(deduplicate.app, name="deduplicate")
    app.add_typer(render.app, name="render")
