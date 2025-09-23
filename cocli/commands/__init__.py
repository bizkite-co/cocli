import typer

def register_commands(app: typer.Typer):
    from . import add
    from . import add_meeting
    from . import view
    from . import import_data
    from . import scrape
    from . import fz
    from . import meetings
    from . import sync
    from . import scrape_shopify
    from . import process_shopify_scrapes
    from . import enrich_shopify_data

    app.command(name="add")(add.add)
    app.command(name="add-meeting")(add_meeting.add_meeting)

    app.command(name="view-company")(view.view_company)
    app.command(name="next")(meetings.next_meetings)
    app.command(name="recent")(meetings.recent_meetings)
    app.command(name="view-meetings")(view.view_meetings)
    app.command(name="open-company-folder")(view.open_company_folder)
    app.command(name="import-data")(import_data.import_data)
    app.command(name="scrape-google-maps")(scrape.scrape_google_maps)
    app.command(name="sync")(sync.sync)
    app.command(name="fz")(fz.fz)
    app.command(name="scrape-shopify-myip")(scrape_shopify.scrape_shopify_myip)
    app.command(name="process-shopify-scrapes")(process_shopify_scrapes.process_shopify_scrapes)
    app.command(name="enrich-shopify-data")(enrich_shopify_data.enrich_shopify_data)