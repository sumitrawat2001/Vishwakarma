# Smart House & Construction Planner

A beginner-friendly Flask and MongoDB web application for preliminary house planning, indicative construction estimates, solar sizing, rainwater potential, saved projects, PDF reports, and an interactive Construction Simulation Lab for educational planning scenarios.

## Disclaimer
All calculations are approximate and for early planning only. They are not a substitute for a licensed architect, structural engineer, quantity surveyor, or local building authority.

## Stack
- Python, Flask, Flask-PyMongo
- MongoDB
- HTML5, CSS3, JavaScript
- ReportLab for PDF reports

## Run locally
1. Install Python 3.11+ and MongoDB, then start the MongoDB service.
2. Create an environment: `python -m venv .venv`
3. Activate it on Windows: `.venv\\Scripts\\Activate.ps1`
4. Install packages: `pip install -r requirements.txt`
5. Copy `.env.example` to `.env` and set a long `SECRET_KEY`.
6. Start the app: `python app.py`
7. Open `http://127.0.0.1:5000`.

## Construction Simulation Lab
The app now includes a dedicated `/simulation` page for exploring a lightweight virtual lab experience focused on housing and construction planning.

### Included simulation modules
- Material simulation
- Load simulation
- Rainwater harvesting simulation
- Solar simulation
- Construction cost simulation
- What-if simulator
- 3D visualization prototype
- Save simulation results to an existing project

### Simulation API endpoints
- `/api/simulation/material`
- `/api/simulation/load`
- `/api/simulation/rainwater`
- `/api/simulation/solar`
- `/api/simulation/cost`
- `/api/simulation/what-if`
- `/api/simulation/save`

These endpoints return JSON results that reuse the app’s existing planning formulas and help users explore scenarios before finalizing a project.

### Material estimator limitations
The current estimator is an area-based legacy heuristic, not an IS-code bill of quantities. It multiplies area per floor × floors by fixed app factors: cement 0.45, sand 0.045, aggregate 0.09, bricks 8, steel 4, flooring 0.9, and paint 3.5 per sq ft per floor. The original estimator did not define physical output units, so its numbers are app units only and must not be used to order materials. The Simulation Lab does not predict concrete strength. IS-based quantity takeoff and mix design need project-specific drawings, dimensions, materials data, and professional verification.

### Advanced material estimation
The authenticated `/material-estimation` module adds geometry-based takeoff for foundation/footing, columns, beams, slabs, brick walls, internal/external plaster, flooring, and painting; a steel bar-group calculator with spacing/count, lap, hook, and bend allowances; location-based sourced rates; saved estimate history; and per-estimate PDF reports. The older `/materials` calculator remains available and links to the advanced module.

Concrete M10, M15, and M20 use nominal 1:3:6, 1:2:4, and 1:1.5:3 volume ratios. Concrete quantities use wet geometric volume × configured dry-volume factor × wastage, ratio-part allocation, 1,440 kg/m³ cement density, 50 kg bags rounded up, and the configured water/cement ratio. Other grades require user-entered design-mix ratios and are identified separately. Brick mortar, plaster, tile wastage, and paint coverage assumptions are shown in the calculation details. Steel weight uses (diameter in mm² / 162) × total bar length in metres.

Material prices are not seeded with assumed market values. Official entries require a source and are selected per material from city/village, district, state, then country; missing entries remain unpriced and partial totals are clearly identified. Authorized administrators manage rates, location entries, nominal mix defaults, dry-volume factor, water/cement ratio, and wastage at `/admin/material-prices`; rate revisions retain their source, editor, timestamp, and history. Admin price/configuration records and user estimation history use the existing Mongo-backed resource repository, with the existing `.construction_resources.json` local fallback. These quantities and costs are preliminary and are not an approved BOQ, design mix, structural design, or supplier quotation.

The calculator saves estimates through `POST /api/material-estimation/calculate`; authenticated users can list their own records at `GET /api/material-estimation/history`. PDF reports are served only for the signed-in owner's saved estimate. Admin writes use `POST /api/admin/material-prices`, `POST /api/admin/material-locations`, and `POST /api/admin/material-estimation-settings`.

## Structural Design Studio

The authenticated `/structural-design` workspace opens a saved House Planner project and reuses its plot dimensions, floor count, room dimensions, and saved room placements. It provides foundation, plinth, column, beam, slab, wall/masonry, staircase, reinforcement-reference, and 3D construction-simulation sections. Structural design sets are saved as user- and project-scoped `structural_designs` resources in the existing Mongo-backed resource store or `.construction_resources.json` local fallback; existing project documents and planner layouts are not replaced.

Dimensioned schematic SVG views can be downloaded as SVG or PNG. A saved design can also produce a two-page preliminary PDF drawing at `/structural-design/drawing/<design_id>.pdf`. The Three.js view uses entered project geometry, supports orbit/zoom, visibility toggles, individual cumulative construction stages, and stage playback. The construction model is illustrative: room layout is shown in plan from saved House Planner placements; framing/grid positions are not automatically engineered.

The material-estimation action sends geometry to the existing `/api/material-estimation/calculate` workflow, so its established quantity formulas, sourced rates, manual rate overrides, saved estimate history, and cost handling remain in use. Concrete volume uses entered dimensions and subtracts entered slab openings; user-entered reinforcing-bar groups use `(diameter_mm² / 162) × total bar length_m`. Excavation uses footing count × footing length × footing width × entered excavation depth. Shuttering sums footing side area, column sides, beam sides/soffits, and slab soffits; openings, slopes, reuse, and site-specific methods are not modeled. Labour, excavation, and shuttering costs are included only when a user supplies a quantity/rate or an existing sourced labour rate is available. Component-level stage takeoffs are shown separately; aggregate pricing is not falsely apportioned to stages.

Every structural dimension, reinforcement input, model, and estimate is preliminary and educational, not an engineer-verified design, approved BOQ, construction drawing, or code-compliance check. The module does not analyze dead/live loads, wind, earthquakes, soil settlement, or bearing-pressure demand, and it does not assert compliance with any IS code. Have a qualified structural engineer review project-specific geometry, geotechnical information, load combinations, detailing, and the current applicable Indian Standards before construction.

## Vastu Analysis

The authenticated `/vastu` dashboard compares room directions with configurable, traditional Vastu guidelines. Choose an existing project to analyze saved plot dimensions and, when available, room positions captured from the draggable 2D House Planner. Rooms without a saved planner position use explicit direction selectors; no automatic architectural layout is inferred for them.

The weighted compatibility score uses only enabled rules with valid room directions. Administrators manage the shared Standard-mode rule set at `/admin/vastu-rules`; user-defined rules remain private and can be compared in Custom or Combined mode. Each analysis can still adjust its preferred direction and weight. Analysis settings and results are saved on the selected project, or a new Vastu analysis project is created when no project is selected. A printable PDF report is available for saved analyses.

The consultant dashboard provides bilingual, rule-based text chat through `POST /api/vastu/chat` and private conversation history through `GET /api/vastu/consultations`. When a user attaches a PNG, JPEG, or WEBP plan (up to 8 MB) and explicitly consents, the backend sends the image, question, and relevant selected-project context and active Vastu rules to the configured OpenAI chat-completions endpoint for vision analysis. The image is also saved in account-scoped consultation storage and served only through an authenticated endpoint. Configure `OPENAI_API_KEY` and a vision-capable `OPENAI_MODEL` on the server; the existing default is `gpt-4o-mini`. Never put the key in frontend code. OpenAI's data-processing and retention policies apply to submitted images and context. Text-only replies continue to use local configured rules; no payment provider is called. Administrators manage shared rules through `/api/admin/vastu/rules`.

Vastu content is presented as traditional cultural guidance, not scientifically proven prediction. The score does not predict health, wealth, luck, or construction safety and does not change structural engineering or safety calculations.

## Construction management APIs

Authenticated users can manage these resource collections through the same REST contract:

- `/api/labour`
- `/api/materials`
- `/api/equipment`
- `/api/tasks`
- `/api/expenses`
- `/api/documents`
- `/api/invoices`

Each collection supports `GET` and `POST`; individual records support `GET`, `PATCH`, and `DELETE`. Payloads are validated server-side, records are scoped to the authenticated user, and optional `project_id` filtering is supported. MongoDB collections are used when MongoDB is available; local development falls back to `.construction_resources.json` without changing the API contract.

The Materials and Cost pages expose save controls backed by these APIs. Dashboard metrics now use all saved projects and live resource data rather than only the five most recent projects.

## Vishwakarma AI support assistant
The project includes a project-specific assistant at `/support` and an API endpoint at `/api/support/ask`.

Vishwakarma AI grounds answers in the application's project knowledge, existing support training data, reusable calculator functions, and the latest saved project for the current user. It understands English, Hindi, and Hinglish locally for common module questions and can use the configured OpenAI-compatible model for broader multilingual answers. Material, cost, solar, rainwater, and what-if questions use the existing application formulas instead of invented calculations.

The assistant covers the planner, plot and room dimensions, 2D/3D visualization, floors and rooms, materials, construction cost and labour, solar, rainwater, Simulation Lab, saved projects, editing, reports, sharing/team features, troubleshooting, and deployment. Its results are preliminary and educational; structural, electrical, load-bearing, and safety decisions require licensed professional verification.

- If no AI key is configured, the agent answers from its built-in knowledge base and any Q&A you train in the UI.
- If `OPENAI_API_KEY` is set, the agent uses the OpenAI-compatible endpoint automatically.
- If `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, and `AZURE_OPENAI_DEPLOYMENT` are set, the agent uses Azure OpenAI instead.

### AI environment variables
```env
OPENAI_API_KEY=your-openai-api-key
OPENAI_MODEL=gpt-4o-mini
OPENAI_BASE_URL=https://api.openai.com/v1/chat/completions
```

No AI key is required for local calculator-backed and knowledge-based answers. API keys remain server-side and are never sent to frontend JavaScript.

## Account access
New accounts go straight to the dashboard after registration; email and mobile OTP verification are not required. Existing accounts can also log in without completing a verification step.

## Public deployment on Render / Cloud
A `render.yaml` file is included for Render deployment.

1. Push this project to GitHub.
2. Create a new Render web service from that repository.
3. Add environment variables in Render:
   - `SECRET_KEY`
   - `MONGO_URI`
   - optional AI variables from `.env.example`
4. Render will build and run the app using `gunicorn`.
5. Health check endpoint: `/health`

## Vercel deployment
Vercel needs both `SECRET_KEY` and `MONGO_URI` configured as non-empty project environment variables. Generate a strong session key locally with `python -c "import secrets; print(secrets.token_hex(32))"`, add it under Vercel Project Settings → Environment Variables, then redeploy. Do not use the development fallback as a production secret. If `SECRET_KEY` is missing or blank on Vercel, authentication routes return an explicit configuration error instead of failing with a generic 500.

Vercel detects the root `app.py` as the Flask application. Keep request paths routed directly to it; rewriting every URL to `/api/index` changes the path Flask receives and can route requests such as `/health` into the protected resource API.

## Structure
`app.py` contains routes and calculation services; `templates/` contains Jinja pages; `static/` contains CSS and JavaScript; `tests/` contains regression tests.

## Planner dimensions
The 2D House Planner shows plot and room measurements, plus schematic doors, windows, ventilators, skylights, furniture, and stairs. Use the Doors & openings controls to add an opening to a room instance; select it to edit its width, depth, and height, or drag it in either the 2D plan or 3D preview to reposition it. Openings and room dimensions are stored with the project and reused by the 3D preview, which depicts all modeled doors and windows, ventilator grilles, and roof-level skylight panes. The Roof toggle shows or hides a clearly visible roof slab aligned to the top floor. Parking is visualized as an open carport with a concrete bay, markings, support posts, canopy, and car rather than a walled room. The 3D Cutaway toggle makes room walls translucent so users can inspect interiors and furniture; camera presets provide isometric, top, front, and side views alongside orbit, zoom, and reset controls. Default object sizes and placements are indicative and need professional verification.

## Database
Collections are `users` and `projects`. Passwords are stored as Werkzeug hashes, never plain text. MongoDB is required for registration and saved projects.

## Verification
A fresh regression test run was completed successfully:

- Command: `python -m unittest tests.test_auth_store`
- Result: `Ran 6 tests in 0.775s` and `OK`

This confirms the app still passes its existing tests after adding the Simulation Lab route and API support.

## Formulas
- Plot area = length x width
- Built-up area uses a preliminary 70% plot coverage assumption x floors
- Rainwater litres/year = roof area x annual rainfall (mm) x runoff coefficient
- Solar capacity is estimated from monthly use, sunlight hours, and an 80% system factor

## Future scope
Architect-approved layouts, regional material rates, structural checks, team collaboration, and deployment monitoring.

## Screenshots

### Login
![Login Page](screenshots/login.png)

> Additional screenshots for dashboard, planner, 3D view, reports, and calculators can be added later as image assets are created.
