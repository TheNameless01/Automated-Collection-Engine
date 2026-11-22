# DZ Car Rental Finder

Local-first automated system to discover, normalize, deduplicate, verify, and export car rental agencies (*Location de voiture / كراء السيارات*) across **all 69 Algerian wilayas**.

---

## Architecture

- **Backend**: Python 3.11+ + FastAPI + SQLite (WAL mode, versioned migrations, hot backups).
- **Frontend**: React 19 + TypeScript + Vite + Tailwind CSS + Leaflet (OpenStreetMap tiles). Chosen for strict type safety, zero runtime cost, clean RTL/LTR support (French, Arabic, English), and offline-ready single-folder `dist/` bundling served directly by FastAPI.
- **Desktop Launcher**: Python Tkinter controller (`desktop/launcher.py`) that runs the exact same FastAPI backend and SQLite database, opens the web dashboard automatically, and supports clean shutdown and Windows `.exe` packaging via PyInstaller.
- **Zero-Cost Guarantee**: Requires zero paid APIs, zero cloud databases, and zero commercial scraping services.

### Project Structure Note
The Vite/React frontend entry points (`index.html`, `src/`, `package.json`, `vite.config.ts`) sit at the repository root so both the Node preview bridge (`server.ts`) and standalone Python packaging (`dist/`) build cleanly from one workspace without duplicate `node_modules`.

---

## Official 69-Wilaya Coverage

The geographic foundation (`data/boundaries/`) implements Algeria's official **69 wilayas** (Law No. 84-09, Law No. 19-12 for wilayas 49–58, and Law No. 26-06 for wilayas 59–69) and **1,541 communes**, paired with Algeria's ADM0 national border and Voronoi-clipped 69-wilaya GeoJSON polygons for spatial containment checks.

---

## Compliant Data Sources & Attribution

1. **OpenStreetMap (Overpass API & Local Geofabrik PBF)**:
   - Parses `amenity=car_rental`, `shop=car_rental`, and multilingual car-rental keywords across `name`, `name:fr`, `name:ar`, `name:en`.
   - Local PBF extract: `https://download.geofabrik.de/africa/algeria-latest.osm.pbf` (processed via PyOsmium).
   - Attribution preserved: `© OpenStreetMap contributors (ODbL)`.
2. **PagesMaghreb Algeria Directory (`pagesmaghreb.com`)**:
   - Public business directory permitting crawling (`robots.txt: Allow: /`), rate-limited with exponential backoff.
3. **PagesJaunes Algérie (`pagesjaunes-dz.com`)**:
   - Public business directory honoring all `robots.txt` `Disallow` rules.
4. **Public Agency Websites**:
   - Enriches discovered agency websites while enforcing each site's `robots.txt`.
5. **Manual Import (CSV / Excel / GeoJSON)** & **Manual Google Maps Verification**:
   - Supports importing spreadsheets and manual verification links. Never automates Google Maps scraping or bypasses CAPTCHAs/auth/rate limits.

---

## Windows Prerequisites & Installation

1. **Install Python 3.11 or 3.12** from [python.org](https://www.python.org/downloads/windows/) (check **"Add python.exe to PATH"**).
2. *(Optional if rebuilding frontend)* **Install Node.js LTS** from [nodejs.org](https://nodejs.org/).
3. Double-click **`setup.bat`** (or run from Command Prompt):
   ```bat
   setup.bat
   ```
   This verifies Python, creates `.venv`, installs `requirements.txt`, initializes the SQLite database (`data\processed\dz_car_rental.db`) with all 69 wilayas and 1,541 communes, and builds `dist\` if Node.js is installed.

---

## Launching the Application

- **Desktop + Browser Dashboard**: Double-click **`run.bat`** (or run `run.bat --headless` to open the browser without the Tkinter window).
- **Building a Windows Executable**: Run **`build.bat`** to test and package into `dist_win\DZCarRentalFinder\DZCarRentalFinder.exe`.

---

## First Collection & Exports

1. Open **Sources** to test connections or download `algeria-latest.osm.pbf` (~302 MB) into `data/raw/`.
2. Open **Collect Data**, select target wilayas (or all 69), choose enabled sources and depth (`Quick` / `Standard` / `Deep`), and click **Start Collection Run**.
3. Use **Manual Review** and **Duplicates** to resolve uncertain wilayas or suspected duplicate pairs (every merge is reversible in Merge History).
4. Open **Export Center** to generate `.xlsx` (with `MASTER`, `STATISTICS`, `SOURCES`, `REVIEW_REQUIRED`, and all **69 wilaya sheets**) or UTF-8 BOM `.csv`. Files are saved in **`exports/`**.

---

## Running Automated Tests

On Windows:
```bat
scripts\run_tests.bat
```
On Linux/macOS:
```bash
PYTHONPATH=backend .venv/bin/pytest -v backend/tests
```
