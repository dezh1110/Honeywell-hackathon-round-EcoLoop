# Weather file

`bengaluru.epw` is bundled here as the default (`EPW_PATH` in
`.env.example`) so the real-EnergyPlus path works against Bengaluru weather
out of the box, not a US city placeholder.

**Source and what it actually is, stated plainly:** this file comes from
[aakashchandrai/Weather-Files](https://github.com/aakashchandrai/Weather-Files)
("Future Weather Files for Eight Indian Cities"), specifically the
`RCP4.5, 2026-2045, Median` scenario for Bengaluru. That means it's a
**climate-morphed near-term projection**, not a standard current-year TMY
(Typical Meteorological Year) file -- it reflects a moderate-emissions
climate scenario averaged over 2026-2045, not literally "last year's
weather." For a hackathon PoC this is a reasonable stand-in for Bengaluru's
climate (verified: correct coordinates, 12.97N 77.58E, 921m elevation;
full 8760-hour year; ran successfully through a real EnergyPlus 26.1.0
install with this project's IDF, producing plausible ~21C July zone
temperatures consistent with Bengaluru's known mild climate) -- but if you
need a strict current-TMY file for anything beyond a demo, get one from:

- https://energyplus.net/weather (search "Bengaluru" / "Bangalore", India)
- https://climate.onebuilding.org for a wider set of Indian stations

Either way, point `EPW_PATH` at whichever file you want to use.
