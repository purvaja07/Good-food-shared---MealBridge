# MealBridge

MealBridge is a Flask application that helps food donors share safe surplus with verified NGOs and community receivers. It includes donor listings, NGO pickup requests, expiry countdowns, optional map matching, notifications, and an administrator console.

## What works

- Role-based donor, NGO, and administrator accounts with Werkzeug password hashing.
- NGO verification before an organization can request food.
- Donation create, edit, and withdraw flows, with image upload validation and size limits.
- Nearby donation search by name, address, category, and optional distance when both sides provide coordinates.
- Interactive `/ngo/map` with verified NGO and food markers, browser geolocation, distance/category/capacity filters, expiry-aware matching, and OSRM road directions.
- Address lookup on the map: type an Indian address, town, or district and press Enter or the map-pin button to geocode and center the map there. Address queries are sent to OpenStreetMap Nominatim; successful lookups are cached for the running app process.
- Authenticated JSON endpoints for nearby donations, NGO locations, pickup requests, and pickup status updates.
- Pickup request acceptance/decline and accepted → picked up → completed tracking.
- Partial pickup requests update the remaining donation quantity and record the meals/portions collected.
- Expired available or reserved donations are made unavailable during normal page requests; related open pickup requests are rejected and both parties are notified.
- In-app notifications, reports, admin user controls, donation moderation, and platform statistics.
- CSRF checks on all form submissions.

## Run in VS Code (Windows)

Open the `MealBridge` folder in VS Code, then use its PowerShell terminal:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
py app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000). A local `mealbridge.db` SQLite database is used automatically, so a separate database server is not required for local development. Tables and default food categories are created on startup.

If PowerShell blocks environment activation, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that terminal, then activate the environment again.

## Optional demo data

In another terminal with the virtual environment active:

```powershell
flask --app app seed-demo
```

The command creates a sample donor, a verified NGO, and a time-limited sample donation in Muktainagar, Jalgaon, Maharashtra. Both demo accounts use `MealBridgeDemo!2026`:

- `donor@mealbridge.local`
- `ngo@mealbridge.local`

These are development-only credentials. Do not use demo accounts in a deployed environment.

Create the first administrator separately; public registration deliberately does not allow an admin role:

```powershell
flask --app app create-admin
```

The command securely prompts for the administrator’s name, email, and password.

## Use MySQL instead of SQLite

1. Create a database and a dedicated local application user. For example, in MySQL:

   ```sql
   CREATE DATABASE mealbridge CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   CREATE USER 'mealbridge_user'@'localhost' IDENTIFIED BY 'use-a-strong-password';
   GRANT ALL PRIVILEGES ON mealbridge.* TO 'mealbridge_user'@'localhost';
   ```

2. Set environment variables in the VS Code PowerShell terminal. URL-encode special characters in the database password:

   ```powershell
   $env:SECRET_KEY = "replace-with-a-long-random-secret"
   $env:DATABASE_URL = "mysql+pymysql://mealbridge_user:use-a-strong-password@localhost/mealbridge?charset=utf8mb4"
   ```

3. Start the app with `py app.py`. SQLAlchemy creates missing tables and default categories. The equivalent MySQL DDL is also available in [`database/schema.sql`](./database/schema.sql).

SQLite remains the default when `DATABASE_URL` is unset. `mysql://...` URLs are also normalized to the PyMySQL driver.

## Project layout

```text
MealBridge/
├── app.py
├── config.py
├── extensions.py
├── requirements.txt
├── database/schema.sql
├── models/
├── routes/
├── templates/
└── static/
    ├── css/style.css
    ├── js/script.js
    └── uploads/
```

## Notes

- Pickup and expiry form values are treated as the local time used by the browser and the application server. For a production deployment, configure both to the same timezone (Bengaluru uses Asia/Kolkata).
- Distance filtering and map markers require latitude and longitude for both the NGO and donation. Address search works without coordinates.
- Nearby-match travel screening is a conservative straight-line estimate (20 km/h plus a pickup buffer); the OSRM route is shown after an NGO asks for directions. Neither the route nor an expiry countdown verifies that food is safe to eat—confirm food handling and timing with the donor.
- The interactive map is available to signed-in NGO accounts at `/ngo/map`; allow browser location access for current-distance matching. NGOs can also save coordinates in their dashboard profile. The map uses the public OSRM routing endpoint only when a route is requested.
- Without a saved or shared location, the food map opens around Muktainagar town centre, Jalgaon district (21.04655, 76.05938). Choose **My location** to request browser GPS and calculate distances from your actual location.
- Map JSON endpoints are authenticated: `GET /api/donations`, `GET /api/ngos`, `GET /api/donations/nearby?lat=...&lon=...&radius_km=5&needed_quantity=1&capacity=50`, `POST /api/pickup/request`, `GET /api/pickup/requests`, and `PUT /api/pickup/update`. JSON writes require the session CSRF token in the `X-CSRF-Token` header.
- Existing databases are updated at startup with the request-quantity and pickup-history columns needed for partial pickups.
- The expiry transition runs on incoming page requests rather than a separate worker. A production deployment that needs time-exact transitions should run a scheduled job using the same expiry logic.
- The impact view estimates food waste avoided at 0.5 kg per completed meal as a planning benchmark; it is not a measured weight.
- Set a unique `SECRET_KEY`, use HTTPS, use a managed database, and remove demo accounts before deployment. Back up `mealbridge.db` if using SQLite.
- Leaflet and OpenStreetMap tiles and Bootstrap assets are loaded from their public CDNs.
