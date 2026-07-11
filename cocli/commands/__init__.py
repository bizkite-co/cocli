import typer


def register_commands(app: typer.Typer) -> None:
    from . import add
    from . import add_email
    from . import add_meeting
    from . import campaign
    from . import compile_enrichment
    from . import context
    from . import deduplicate
    from . import dev
    from . import enrich_customers
    from . import enrich_shopify_data
    from . import exclude
    from . import flag_email_providers
    from . import fz
    from . import import_companies
    from . import import_customers
    from . import import_data
    from . import ingest_google_maps_csv
    from . import init
    from . import meetings
    from . import process_shopify_scrapes
    from . import render
    from . import render_prospects_kml
    from . import scrape_shopify
    from . import status
    from . import sync
    from . import smart_sync
    from . import view
    from . import worker
    from . import web
    from . import infrastructure
    from . import index
    from . import cluster

    app.command(name="add", no_args_is_help=True)(add.add)
    app.command(name="add-email", no_args_is_help=True)(add_email.add_email)
    app.command(name="add-meeting", no_args_is_help=True)(add_meeting.add_meeting)
    app.command(name="context")(context.context)
    app.command(name="fz")(fz.fz)
    app.command(name="google-maps-cache-to-company-files", no_args_is_help=True)(
        import_companies.google_maps_cache_to_company_files
    )
    app.command(name="import-customers", no_args_is_help=True)(import_customers.import_customers)
    app.command(name="import-data", no_args_is_help=True)(import_data.import_data)
    app.command(name="google-maps-csv-to-google-maps-cache", no_args_is_help=True)(
        ingest_google_maps_csv.google_maps_csv_to_google_maps_cache
    )
    app.command(name="init")(init.init)
    app.command(name="next")(meetings.next_meetings)
    app.command(name="open-company-folder", no_args_is_help=True)(view.open_company_folder)
    app.command(name="process-shopify-scrapes")(
        process_shopify_scrapes.process_shopify_scrapes
    )
    app.command(name="recent")(meetings.recent_meetings)
    app.command(name="render-prospects-kml", no_args_is_help=True)(render_prospects_kml.render_prospects_kml)
    app.command(name="scrape-shopify-myip")(scrape_shopify.scrape_shopify_myip)
    app.command(name="status")(status.status)
    app.add_typer(sync.app, name="sync")
    app.command(name="view-company", no_args_is_help=True)(view.view_company)
    app.command(name="view-meetings", no_args_is_help=True)(view.view_meetings)
    app.command(name="enrich-customers", no_args_is_help=True)(enrich_customers.enrich_customers)
    app.command(name="enrich-shopify-data")(enrich_shopify_data.enrich_shopify_data)
    app.command(name="compile-enrichment")(compile_enrichment.compile_enrichment)
    app.command(name="flag-email-providers", no_args_is_help=True)(flag_email_providers.flag_email_providers)

    app.add_typer(campaign.app, name="campaign")
    app.add_typer(dev.app, name="dev")
    app.add_typer(exclude.app, name="exclude")
    app.add_typer(deduplicate.app, name="deduplicate")
    app.add_typer(render.app, name="render")
    app.add_typer(smart_sync.app, name="smart-sync")
    app.add_typer(worker.app, name="worker")
    app.add_typer(web.app, name="web")
    app.add_typer(infrastructure.app, name="infrastructure")
    app.add_typer(index.app, name="index")
    app.add_typer(cluster.app, name="cluster")
    try:
        from . import video
        app.add_typer(video.app, name="video")
    except ImportError as e:
        err_msg = str(e)
        # Register a dummy command or typer that warns the user if they try to use it
        video_inactive_app = typer.Typer(no_args_is_help=True, help="Video commands (not available).")
        @video_inactive_app.callback()
        def video_inactive_callback() -> None:
            typer.echo(f"Video commands not available: {err_msg}. Install with 'pip install .[video]'.")
            raise typer.Exit(1)
        app.add_typer(video_inactive_app, name="video")

