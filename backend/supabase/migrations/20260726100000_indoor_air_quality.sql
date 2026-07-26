/*
# Add indoor air quality column to building_telemetry

The hackathon spec's Feedback loop calls for streaming "zone temperatures,
indoor air quality, energy consumption, [and] PMV thermal comfort indices."
This was missing a dedicated IAQ column -- `building_telemetry` only had
temperature, PMV (per zone, in the `zones` jsonb), and energy so far.

`indoor_air_quality_ppm` is an estimated CO2 concentration (see
app/energyplus/thermal_model.py's `estimate_co2_ppm` for the estimation
method and its limits) written by the backend every decision cycle,
alongside the existing columns.
*/

ALTER TABLE building_telemetry ADD COLUMN IF NOT EXISTS indoor_air_quality_ppm double precision NOT NULL DEFAULT 420.0;
