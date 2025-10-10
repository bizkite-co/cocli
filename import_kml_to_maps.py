
import os
import subprocess
import toml
from playwright.sync_api import sync_playwright
import logging

logger = logging.getLogger(__name__)

def main():
    """
    Automates the process of importing a KML file to Google My Maps.
    """
    
    # Read configuration
    config_path = "/home/mstouffer/repos/company-cli/campaigns/2025/turboship/config.toml"
    with open(config_path, "r") as f:
        config = toml.load(f)
        
    email = config.get("google_maps", {}).get("email")
    one_password_path = config.get("google_maps", {}).get("one_password_path")
    kml_file_path = "/home/mstouffer/repos/company-cli/campaigns/2025/turboship/turboship_customers.kml"
    
    if not email or not one_password_path:
        logger.error("Email or 1Password path not found in config.toml")
        return
        
    # Get password from 1Password
    try:
        password = subprocess.check_output(["op", "read", one_password_path]).strip().decode("utf-8")
    except FileNotFoundError:
        logger.error("The 'op' command-line tool is not installed or not in your PATH.")
        logger.error("Please install the 1Password CLI and ensure you are logged in.")
        return
    except subprocess.CalledProcessError:
        logger.error("Could not retrieve the password from 1Password.")
        logger.error("Please ensure you are logged in to the 'op' CLI.")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False) # Set headless=True to run in the background
        page = browser.new_page()
        
        # Go to Google My Maps
        page.goto("https://www.google.com/mymaps")
        
        # --- Login Process ---
        page.fill('input[type="email"]', email)
        page.press('input[type="email"]', "Enter")
        page.wait_for_timeout(2000) # Wait for the password page to load
        page.fill('input[type="password"]', password)
        page.press('input[type="password"]', "Enter")
        page.wait_for_navigation()
        
        # --- Create a new map ---
        page.click("button:has-text('Create a new map')")
        page.wait_for_timeout(2000) # Wait for the new map to be created
        
        # --- Import KML ---
        page.click("button:has-text('Import')")
        page.wait_for_timeout(1000)
        page.set_input_files("input[type='file']", kml_file_path)
        
        page.wait_for_timeout(5000) # Wait for the file to upload and process
        
        logger.info("KML file imported successfully.")
        
        browser.close()

if __name__ == "__main__":
    main()
