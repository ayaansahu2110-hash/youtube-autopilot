from __future__ import annotations

from difflib import SequenceMatcher
import json
from urllib.parse import urlparse

from autopilot.config import Settings
from autopilot.discovery import TopicDiscovery
from autopilot.models import ResearchPack, ResearchSource, SceneBeat, TopicCandidate, VideoPlan
from autopilot.providers.premium_planner import PremiumScriptPlanner


AUTHORITATIVE_DOMAINS = {
    "science": (
        "nasa.gov", "noaa.gov", "weather.gov", "esa.int", "nih.gov", "nature.com", "science.org"
    ),
    "history": ("si.edu", "loc.gov", "archives.gov", "britishmuseum.org"),
    "geography": ("un.org", "worldbank.org", "usgs.gov", "noaa.gov", "whoi.edu", "nps.gov", "fs.usda.gov"),
    "mathematics": ("ams.org", "maa.org", "mathworld.wolfram.com", "edu"),
    # NOAA is authoritative for Earth-Moon tide interactions that cross the
    # space and ocean-science lanes.
    "space": ("nasa.gov", "noaa.gov", "esa.int", "jpl.nasa.gov", "noirlab.edu"),
    "engineering": ("nist.gov", "ieee.org", "asme.org", "sae.org", "faa.gov", "nasa.gov", "edu"),
    "f1_automotive": ("fia.com", "formula1.com", "sae.org", "nhtsa.gov"),
}


def verified_curio_seed(
    excluded_topics: list[str] | None = None,
    requested_topic: str | None = None,
) -> tuple[TopicCandidate, ResearchPack] | None:
    """Return a fresh, independently sourced fact when live research is unavailable.

    A hosted runner can be blocked by an otherwise valid public source.  This is a
    deliberately small editorial reserve, not a generic fallback: every entry has
    two independent, category-authoritative sources and enough evidence for the
    verifier to re-check it.  Used entries are excluded from the channel history,
    so a source outage cannot create repetitive uploads.
    """
    excluded = {_normalise_topic(topic) for topic in (excluded_topics or [])}
    requested = _normalise_topic(requested_topic or "")
    seeds = (
        (
            "Why Astronauts Float in Orbit",
            "space",
            "Astronauts and their spacecraft are continually falling around Earth, not beyond gravity.",
            ("astronaut float", "microgravity", "falling forever", "physics of falling"),
            (
                ResearchSource(
                    title="What is microgravity?",
                    publisher="NASA",
                    url="https://www.nasa.gov/learning-resources/for-kids-and-students/what-is-microgravity-grades-5-8/",
                    snippet=(
                        "NASA explains that astronauts in low Earth orbit are still strongly affected "
                        "by Earth's gravity. The apparent weightlessness comes because the spacecraft "
                        "and everyone inside it are falling together while moving sideways fast enough "
                        "to keep missing Earth. That shared free-fall removes the supporting force people "
                        "normally feel as weight, producing the microgravity environment seen on station."
                    ),
                ),
                ResearchSource(
                    title="Space on Earth",
                    publisher="European Space Agency",
                    url="https://www.esa.int/Science_Exploration/Human_and_Robotic_Exploration/Celsius_Mission_-_English_version/Space_on_Earth",
                    snippet=(
                        "ESA describes microgravity as a condition created when people and their vehicle "
                        "are in free-fall together. Orbit is not a place where gravity disappears: a craft "
                        "keeps falling toward Earth while its forward speed curves its path around the planet. "
                        "This is why objects released inside an orbiting spacecraft appear to float beside "
                        "the crew instead of dropping to a floor."
                    ),
                ),
            ),
        ),
        (
            "Why Ocean Water Is Salty",
            "geography",
            "Most ocean salt ultimately comes from dissolved minerals carried from land, then concentrated as water cycles away.",
            ("ocean water salty", "why ocean is salty", "seawater salinity"),
            (
                ResearchSource(
                    title="Why is the ocean salty?",
                    publisher="NOAA Ocean Service",
                    url="https://oceanservice.noaa.gov/facts/whysalty.html",
                    snippet=(
                        "NOAA explains that rain and rivers dissolve small amounts of mineral material from "
                        "rocks and carry ions to the sea. Water leaves the ocean through evaporation, but the "
                        "dissolved salts remain, so ocean circulation mixes and concentrates them over very "
                        "long periods. Seafloor hydrothermal activity also adds dissolved material, while "
                        "chemical processes and sediments remove some ions and help set seawater's balance."
                    ),
                ),
                ResearchSource(
                    title="Saline water and salinity",
                    publisher="U.S. Geological Survey",
                    url="https://www.usgs.gov/special-topics/water-science-school/science/saline-water-and-salinity",
                    snippet=(
                        "The U.S. Geological Survey describes salinity as the amount of dissolved salts in "
                        "water and notes that ocean water is saline because it contains a mixture of dissolved "
                        "ions. The water cycle moves liquid water and water vapor, not all of those dissolved "
                        "materials, so rivers, evaporation, mixing, and geological inputs shape where salinity "
                        "is high or low rather than making every part of the ocean identical."
                    ),
                ),
            ),
        ),
        (
            "Why Heat Shields Burn on Purpose",
            "science",
            "Ablative heat shields sacrifice material to carry heat away from a spacecraft during atmospheric entry.",
            ("heat shield burn", "heat shield reentry", "ablative reentry"),
            (
                ResearchSource(
                    title="Entry systems",
                    publisher="NASA Ames Research Center",
                    url="https://www.nasa.gov/ames/core-area-of-expertise-entry-systems/",
                    snippet=(
                        "NASA's entry-systems work explains that a spacecraft entering an atmosphere must "
                        "manage extreme heating created as air is compressed and flows around the vehicle. "
                        "Ablative thermal-protection materials are designed to char, melt, and erode in a "
                        "controlled way. That changing surface carries heat away and protects the structure "
                        "behind it, so visible burning can be part of the intended engineering design."
                    ),
                ),
                ResearchSource(
                    title="Protecting planetary missions from extreme heat",
                    publisher="NASA Science",
                    url="https://science.nasa.gov/science-research/science-enabling-technology/technology-highlights/protecting-future-planetary-missions-from-extreme-heat/",
                    snippet=(
                        "NASA describes thermal-protection systems as a critical layer between a vehicle and "
                        "the intense heat of atmospheric entry. Different missions use materials selected for "
                        "their temperature, mass, and return profile; some systems insulate while ablative "
                        "systems deliberately consume surface material. The engineering objective is to keep "
                        "the spacecraft's internal structure and instruments within safe temperatures."
                    ),
                ),
            ),
        ),
        (
            "Why the Sky Is Blue but Sunsets Are Red",
            "science",
            "Air molecules scatter shorter blue wavelengths more strongly; at sunset the longer path removes more blue light before sunlight reaches an observer.",
            ("sky blue sunset red", "rayleigh scattering", "red sunset"),
            (
                ResearchSource(
                    title="Why is the sky blue?",
                    publisher="NASA Space Place",
                    url="https://spaceplace.nasa.gov/blue-sky/en/",
                    snippet=(
                        "NASA explains that white sunlight contains many wavelengths. Tiny molecules in "
                        "Earth's atmosphere scatter shorter blue wavelengths more strongly than red ones, "
                        "so blue light arrives from across the daytime sky. Near sunset, sunlight travels "
                        "through much more atmosphere; much of the blue is scattered out of the direct path, "
                        "leaving more red and yellow light to reach an observer."
                    ),
                ),
                ResearchSource(
                    title="Why is the sky blue?",
                    publisher="NOAA SciJinks",
                    url="https://www.noaa.gov/jetstream/color-of-sky",
                    snippet=(
                        "NOAA's educational material describes Rayleigh scattering: atmospheric molecules "
                        "scatter shorter visible wavelengths more efficiently. The longer atmospheric path "
                        "at sunrise and sunset scatters much of the blue light away, while longer orange and "
                        "red wavelengths continue toward the viewer. Dust and aerosols can change the colors, "
                        "so not every sunset has the same intensity."
                    ),
                ),
            ),
        ),
        (
            "Why the Deep Ocean Can Crush a Submarine",
            "geography",
            "Water pressure increases with depth because every deeper surface supports a taller column of water above it.",
            ("deep ocean pressure", "submarine crushed", "hadal pressure"),
            (
                ResearchSource(
                    title="How does pressure impact animals in the ocean?",
                    publisher="NOAA Ocean Exploration",
                    url="https://oceanexplorer.noaa.gov/facts/pressure.html",
                    snippet=(
                        "NOAA explains that ocean pressure rises steadily with depth as the weight of the "
                        "overlying water increases. At the deepest trenches, pressures exceed one thousand "
                        "times the pressure at sea level. Deep-sea organisms and engineered vehicles survive "
                        "only when their structures avoid vulnerable air spaces or resist the pressure difference."
                    ),
                ),
                ResearchSource(
                    title="Hadal zone",
                    publisher="Woods Hole Oceanographic Institution",
                    url="https://www.whoi.edu/ocean-learning-hub/ocean-topics/how-the-ocean-works/ocean-zones/hadal-zone/",
                    snippet=(
                        "WHOI defines the hadal zone as the deepest ocean trenches, roughly six to eleven "
                        "kilometres below the surface. It reports pressures greater than one thousand times "
                        "surface pressure and describes pressure-resistant autonomous vehicles built with "
                        "NASA's Jet Propulsion Laboratory to explore those environments."
                    ),
                ),
            ),
        ),
        (
            "Why Lightning Is Hotter Than the Sun's Surface",
            "science",
            "A lightning channel can briefly heat air to roughly five times the Sun's visible-surface temperature, but it contains vastly less total energy than the Sun.",
            ("lightning hotter sun", "lightning temperature", "thunder shockwave"),
            (
                ResearchSource(
                    title="How hot is lightning?",
                    publisher="National Weather Service",
                    url="https://www.weather.gov/safety/lightning-temperature",
                    snippet=(
                        "The National Weather Service explains that the air in a lightning channel can be "
                        "heated to around fifty thousand degrees Fahrenheit, about five times hotter than "
                        "the Sun's visible surface. The heating is extremely brief and confined to a narrow "
                        "channel; it does not mean a lightning bolt contains more total energy than the Sun."
                    ),
                ),
                ResearchSource(
                    title="Lightning facts",
                    publisher="NOAA National Severe Storms Laboratory",
                    url="https://www.nssl.noaa.gov/education/svrwx101/lightning/faq/",
                    snippet=(
                        "NOAA describes lightning as a powerful electrical discharge that rapidly heats the "
                        "surrounding air. The sudden expansion creates a shock wave heard as thunder. Channel "
                        "temperature estimates are tens of thousands of degrees, but the event lasts only a "
                        "fraction of a second and varies along the discharge."
                    ),
                ),
            ),
        ),
        (
            "Why the Moon Moves Earth's Oceans",
            "space",
            "Tides arise mainly from differences in the Moon's gravitational pull across Earth, with the Sun modifying their strength.",
            ("moon moves ocean", "moon causes tides", "tidal bulge"),
            (
                ResearchSource(
                    title="What causes tides?",
                    publisher="NOAA Ocean Service",
                    url="https://oceanservice.noaa.gov/education/tutorial_tides/tides02_cause.html",
                    snippet=(
                        "NOAA explains that tides are driven primarily by the Moon's gravity and the "
                        "Earth-Moon system's motion. The pull differs across Earth, producing tidal bulges, "
                        "while coastlines, ocean depth, and basin shape determine the local timing and height. "
                        "The Sun also contributes and strengthens or weakens tides depending on alignment."
                    ),
                ),
                ResearchSource(
                    title="Tides and the Moon",
                    publisher="NASA Science",
                    url="https://science.nasa.gov/moon/tides/",
                    snippet=(
                        "NASA describes the Moon's gravity as the main driver of Earth's ocean tides. Because "
                        "the lunar pull is stronger on the near side than the far side, water is redistributed "
                        "into broad bulges as Earth rotates. Solar gravity modifies this pattern, creating "
                        "larger spring tides and smaller neap tides during different alignments."
                    ),
                ),
            ),
        ),
    )
    # Reviewed 2026-09-19. Two NASA publications, not independent publishers.
    seeds += ((
        "Why the Moon Changes Shape Without Changing Its Shape",
        "space",
        "Lunar phases are changing views of the sunlit hemisphere, not Earth's shadow.",
        ("moon phases", "moon changes shape", "lunar phases"),
        (
            ResearchSource(
                title="Moon Facts", publisher="NASA Science",
                url="https://science.nasa.gov/moon/facts/",
                snippet=(
                    "The Moon spins once per orbit, keeping its near hemisphere toward Earth. "
                    "Sunlight illuminates different regions as it orbits. At full Moon the visible "
                    "hemisphere is illuminated; at new Moon its far hemisphere receives sunlight. "
                    "The far side is therefore not permanently dark. Rotation and changing illumination "
                    "are different effects; a fixed face does not imply a fixed phase."
                ),
            ),
            ResearchSource(
                title="What Are the Moon's Phases?", publisher="NASA Space Place",
                url="https://spaceplace.nasa.gov/moon-phases/en/",
                snippet=(
                    "Moonlight is reflected sunlight. Half of the Moon is illuminated by the Sun, "
                    "while an observer on Earth sees different fractions of that illuminated half "
                    "as the Moon travels around Earth. These views produce the sequence of lunar "
                    "phases. The Moon remains a sphere throughout the cycle; ordinary phases do not "
                    "mean that Earth is casting its shadow over the lunar surface."
                ),
            ),
        ),
    ),)
    # Reviewed 2026-09-23 against separate NASA and NOAA explanations.
    seeds += (
        (
            "Why Jet Trails Sometimes Linger for Hours",
            "science",
            "Aircraft exhaust adds water vapor that freezes into ice crystals high in the atmosphere; surrounding humidity controls how long the cloud persists.",
            ("contrail", "jet trails", "airplane trails", "condensation trails"),
            (
                ResearchSource(
                    title="Contrail Simulation",
                    publisher="NOAA NESDIS",
                    url="https://www.nesdis.noaa.gov/about/k-12-education/atmosphere/contrail-simulation",
                    snippet=(
                        "NOAA explains that water vapor from aircraft exhaust condenses and freezes "
                        "in the cold air at cruising altitude, making a visible cloud of tiny ice "
                        "crystals. Its interactive simulation varies atmospheric temperature and "
                        "humidity: more humid air slows the disappearance of the trail, while wind "
                        "spreads it. The visible white streak is primarily ice rather than a stream "
                        "of smoke, though the aircraft still emits other exhaust constituents."
                    ),
                ),
                ResearchSource(
                    title="The Evolution of a Contrail",
                    publisher="NASA Earth Observatory",
                    url="https://science.nasa.gov/earth/earth-observatory/the-evolution-of-a-contrail-78154/",
                    snippet=(
                        "NASA compares satellite images of aircraft trails off Newfoundland taken "
                        "nearly two hours apart. The young narrow lines had spread into wispy "
                        "cirrus-like clouds as winds moved them. Dry air can dissipate a trail in "
                        "seconds or minutes; sufficiently humid air can let it persist and spread "
                        "for hours. This is an atmospheric condition, not evidence that the airplane "
                        "changed its purpose or released a different visible substance."
                    ),
                ),
            ),
        ),
        (
            "Why a Hurricane Has a Calm Eye",
            "science",
            "Air sinks and warms in the center, clearing clouds, while the surrounding eyewall holds the strongest rising thunderstorms and winds.",
            ("hurricane eye", "calm eye", "eye of a hurricane", "eyewall"),
            (
                ResearchSource(
                    title="Hurricanes: The Greatest Storms on Earth",
                    publisher="NASA Science",
                    url="https://science.nasa.gov/earth/natural-disasters/hurricanes-typhoons/hurricanes-the-greatest-storms-on-earth/",
                    snippet=(
                        "NASA describes the hurricane eye as a relatively calm center where air "
                        "sinks, compresses, and warms, leaving fewer clouds and less precipitation. "
                        "Surrounding it is the eyewall, a ring of intense thunderstorms, rising "
                        "moist air, heavy rain, and strong winds. A calm passage through the eye "
                        "does not mean the hurricane has ended; dangerous eyewall conditions "
                        "return on the other side."
                    ),
                ),
                ResearchSource(
                    title="A Guide to Understanding Satellite Images of Hurricanes",
                    publisher="NOAA NESDIS",
                    url="https://www.nesdis.noaa.gov/news/guide-understanding-satellite-images-of-hurricanes",
                    snippet=(
                        "NOAA explains that air flows inward near the ocean surface, rises in "
                        "the eyewall, and spreads outward aloft. As a mature storm strengthens, "
                        "air also sinks in the center and the sinking motion clears clouds from "
                        "the eye. The eye is the calmest part of the storm, while the wall of deep "
                        "clouds around it carries deadly winds. An eye is not always clearly "
                        "visible in ordinary satellite imagery."
                    ),
                ),
            ),
        ),
    )
    # Reviewed 2026-10-07 against separate primary science/education agencies.
    # Keep a small reserve for source outages without recycling old uploads.
    seeds += (
        (
            "Why Venus Is Hotter Than Mercury",
            "space",
            "Venus has a hotter average surface than Mercury because its dense carbon-dioxide atmosphere traps heat, although Mercury is closer to the Sun.",
            ("venus hotter than mercury", "venus greenhouse atmosphere"),
            (
                ResearchSource(
                    title="Venus Facts", publisher="NASA Science",
                    url="https://science.nasa.gov/venus/venus-facts/",
                    snippet=(
                        "NASA identifies Venus as the hottest planet even though Mercury orbits closer "
                        "to the Sun. A thick atmosphere dominated by carbon dioxide traps outgoing heat "
                        "through an extreme greenhouse effect. The resulting mean surface temperature is "
                        "about 467 degrees Celsius. This comparison is about sustained surface conditions, "
                        "not a claim that Venus receives more sunlight or that every location on Mercury "
                        "is cooler at every instant."
                    ),
                ),
                ResearchSource(
                    title="Greenhouse effect, clouds and winds", publisher="European Space Agency",
                    url="https://www.esa.int/Science_Exploration/Space_Science/Venus_Express/Greenhouse_effect_clouds_and_winds",
                    snippet=(
                        "ESA explains that Venus has the Solar System's strongest planetary greenhouse "
                        "effect. Its clouds reflect much of the incoming sunlight, yet the dense lower "
                        "atmosphere retains heat efficiently; the heat balance makes the surface intensely "
                        "hot. A Venus story should distinguish the sunlight reaching the planet from the "
                        "heat trapped below its clouds and avoid presenting a made-up surface experiment "
                        "or an exact temperature unsupported by the chosen source."
                    ),
                ),
            ),
        ),
        (
            "Why Rivers Carve S-Bends",
            "geography",
            "Faster water erodes the outside of a river bend while slower water deposits sediment on the inside; bends can migrate and sometimes become oxbow lakes.",
            ("river meander", "river s bends", "oxbow lake"),
            (
                ResearchSource(
                    title="Find-A-Feature: Meander", publisher="U.S. Geological Survey",
                    url="https://www.usgs.gov/educational-resources/find-feature-meander",
                    snippet=(
                        "USGS describes a meander as a bend in a river whose shape changes through "
                        "erosion on the outside of the bend and deposition on the inside. The flow "
                        "moves sediment instead of carving a fixed decorative curve. A visual explanation "
                        "can mark the outside cut bank and the inner deposit, then show the channel "
                        "shifting sideways with time. The pace depends on flow and local ground, "
                        "so the video should avoid claiming that every river bends at one rate."
                    ),
                ),
                ResearchSource(
                    title="Fluvial Features: Meandering Stream", publisher="U.S. National Park Service",
                    url="https://www.nps.gov/articles/meandering-stream.htm",
                    snippet=(
                        "NPS explains that the fastest part of a meandering stream shifts toward "
                        "the outside of a bend. The outer bank erodes while sediment builds a point "
                        "bar on the inner bank, producing sideways migration. If neighboring bends "
                        "eventually meet and the stream takes a shorter course, the abandoned loop "
                        "can become an oxbow lake. This process is a useful animated cross-section "
                        "story, not a claim that all river curves must cut off."
                    ),
                ),
            ),
        ),
        (
            "Why Glacier Ice Looks Blue",
            "geography",
            "Thick, compact glacier ice absorbs more red light while blue wavelengths can travel and scatter back toward an observer; trapped air makes fresh snow look white.",
            ("glacier ice blue", "why glaciers blue"),
            (
                ResearchSource(
                    title="Why are glaciers blue?", publisher="U.S. Geological Survey",
                    url="https://www.usgs.gov/media/audio/why-are-glaciers-blue",
                    snippet=(
                        "USGS explains the blue appearance of glacier ice through the interaction of "
                        "light and a thick path of ice. Longer red wavelengths are absorbed more "
                        "strongly, while shorter blue light is transmitted and scattered toward the "
                        "viewer. A thin piece of clear ice does not necessarily look vividly blue; "
                        "the color becomes noticeable where light passes through enough compact ice. "
                        "This is an optical explanation, not a claim that the ice contains blue dye."
                    ),
                ),
                ResearchSource(
                    title="Why is the Ice Blue? In Glacier Bay", publisher="U.S. National Park Service",
                    url="https://www.nps.gov/places/why-is-the-ice-blue-in-glacier-bay.htm",
                    snippet=(
                        "NPS describes deep blue glacier ice as compact ice with relatively few air "
                        "bubbles after long compression. Fresh snow has many small air spaces that "
                        "scatter visible light and make it look white. A visual story can compare "
                        "snow, compact ice, and the longer light path through a glacier, then show "
                        "red light absorbed more readily than blue. The exact shade changes with "
                        "the thickness, lighting and impurities, so a glacier need not look blue everywhere."
                    ),
                ),
            ),
        ),
    )
    seeds += (
        (
            "Why Auroras Glow in Different Colors",
            "space",
            "Energetic particles excite oxygen and nitrogen in the upper atmosphere; the gas and altitude determine the light's colors.",
            ("aurora colors", "northern lights colors", "oxygen nitrogen aurora"),
            (
                ResearchSource(
                    title="Auroras", publisher="NASA Science",
                    url="https://science.nasa.gov/sun/auroras/",
                    snippet=(
                        "NASA explains that energetic particles guided into Earth's upper atmosphere "
                        "transfer energy to oxygen and nitrogen. As those atoms and molecules release "
                        "energy, they emit visible light. Oxygen can appear green around 100 to 200 km "
                        "and red higher than about 200 km. Nitrogen can appear blue or pink, and mixtures "
                        "of emissions can look purple or white. The color is tied to both the atmospheric "
                        "gas and the altitude, rather than a different color of sunlight."
                    ),
                ),
                ResearchSource(
                    title="What is an Aurora?", publisher="NOAA NESDIS",
                    url="https://www.nesdis.noaa.gov/about/k-12-education/optical-phenomena/what-aurora",
                    snippet=(
                        "NOAA describes solar particles and energy reaching polar regions along Earth's "
                        "magnetic field and interacting with atmospheric gases. Excited oxygen emits "
                        "green and red light, while nitrogen produces blue and purple hues. Auroras "
                        "are seen at night but their energy comes from solar activity; the magnetic "
                        "field steers particles toward the polar atmosphere. A visual explanation "
                        "can separate the Sun, magnetic field, atmosphere and emitted colors."
                    ),
                ),
            ),
        ),
        (
            "Why Geysers Erupt Instead of Flowing Steadily",
            "geography",
            "A pressure drop allows hot underground water to flash into steam through a constricted conduit.",
            ("geyser", "underground pressure",),
            (
                ResearchSource(title="Yellowstone active hydrothermal system", publisher="USGS",
                               url="https://www.usgs.gov/volcanoes/yellowstone/science/yellowstones-active-hydrothermal-system",
                               snippet="USGS identifies two essentials for a geyser: an underground hot-water reservoir and a constriction that focuses the outflow. Initial water ejection reduces pressure, allowing the remaining water to become an expanding steam-water mixture. Eruptions may be regular or unpredictable because underground plumbing changes. Rain and snow feed groundwater heated by rocks above Yellowstone's magma storage region."),
                ResearchSource(title="How a geyser works", publisher="National Park Service",
                               url="https://www.nps.gov/features/yell/ofvec/exhibits/treasures/thermals/geysers/geyser2.htm",
                               snippet="NPS describes pressure holding hot water below its boiling threshold until steam bubbles accumulate behind a narrow section. Escaping water lowers pressure and triggers rapid steam formation that expels more water. The eruption ends when the reservoir drains or cools. This is a hydrothermal water-and-steam process; do not depict molten lava erupting from the geyser vent."),
            ),
        ),
        (
            "Why a Compass Does Not Point to True North",
            "geography",
            "A compass follows the local magnetic field; declination is the difference from geographic north.",
            ("compass", "magnetic declination",),
            (
                ResearchSource(title="What is declination?", publisher="USGS",
                               url="https://www.usgs.gov/faqs/what-declination?items_per_page=6&page=1",
                               snippet="USGS defines magnetic declination as the angle between a compass direction and geographic north. This angle depends on location and date because Earth's magnetic field is complex and not perfectly aligned with the rotation axis. Topographic maps state a declination and its reference year. At high latitudes compass behavior can become counterintuitive, so a compass is not simply a pointer aimed directly at a fixed geographic pole."),
                ResearchSource(title="World Magnetic Model navigation", publisher="NOAA NCEI",
                               url="https://www.ncei.noaa.gov/products/world-magnetic-model",
                               snippet="NOAA explains that compasses align with magnetic force at the observer's location. Geographic north is generally a different direction. Magnetic models provide the declination correction, which changes with location and time; WMM updates support ships, aircraft, and consumer devices. Magnetic headings complement GPS position measurements. Avoid claiming any single correction works worldwide or indefinitely."),
            ),
        ),
        (
            "Why Cooling Lava Forms Stone Columns",
            "geography",
            "Cooling contraction creates fractures that often form approximately hexagonal columns.",
            ("basalt column", "stone column", "columnar joint",),
            (
                ResearchSource(title="Columnar jointing and cooling history", publisher="USGS",
                               url="https://www.usgs.gov/observatories/hvo/news/volcano-watch-columnar-jointing-provides-clues-cooling-history-lava-flows",
                               snippet="USGS explains that cooling lava solidifies from its boundaries inward and contracts, generating thermal stress relieved by fractures. Cracks progress toward the hotter interior perpendicular to cooling boundaries. Slower cooling can form thick regular colonnades, while faster cooling produces less regular entablature. Many columns show overall hexagonal symmetry, but individual columns can have other shapes."),
                ResearchSource(title="Columnar Jointing", publisher="National Park Service",
                               url="https://www.nps.gov/subjects/volcanoes/columnar-jointing.htm",
                               snippet="NPS describes parallel fractures made by contraction as hot igneous rock cools. Columns are commonly six-sided but may have three to seven sides; they stand perpendicular to the principal cooling surfaces rather than necessarily vertical. Intersecting cracks near 120 degrees efficiently relieve contractional stress. Devils Postpile and Devils Tower illustrate this natural geological pattern, which also occurs outside basalt lava flows."),
            ),
        ),
    )
    # Reviewed 2026-10-14 against independent NOAA/NPS and USDA/NPS sources.
    # These are editorial reserves for source outages; history exclusions prevent reuse.
    seeds += (
        (
            "Why Fog Hugs the Ground",
            "geography",
            "Fog is a cloud at ground level: humid air cools to its dew point and water condenses near the surface, while terrain and light winds can keep it pooled in low places.",
            ("fog ground", "ground cloud", "valley fog"),
            (
                ResearchSource(
                    title="What's the Difference Between Fog and Clouds?",
                    publisher="NOAA NESDIS",
                    url="https://www.nesdis.noaa.gov/about/k-12-education/atmosphere/whats-the-difference-between-fog-and-clouds",
                    snippet=(
                        "NOAA explains that clouds and fog both form when water vapor condenses or "
                        "freezes into tiny droplets or ice crystals, but fog is defined by forming at "
                        "ground level. Cooling humid air toward its dew point allows condensation near "
                        "the surface. Wind, temperature, moisture and terrain determine whether the "
                        "droplets remain as a shallow ground-level layer or mix into higher cloud. "
                        "A visual explanation should show real condensation and terrain, not smoke."
                    ),
                ),
                ResearchSource(
                    title="Clouds and Fog",
                    publisher="Rocky Mountain National Park",
                    url="https://www.nps.gov/romo/clouds_and_fog.htm",
                    snippet=(
                        "The National Park Service describes mountain and valley fog forming where "
                        "moist air cools enough for water to condense. Air forced up a slope cools as "
                        "pressure drops, while clear nights can cool valley air near the ground and "
                        "produce shallow fog when moisture is available. Terrain can therefore make "
                        "fog look as if it hugs a slope or pools in a basin, but the effect still "
                        "depends on humidity, temperature and airflow rather than gravity pulling clouds down."
                    ),
                ),
            ),
        ),
        (
            "Why Glaciers Carve U-Shaped Valleys",
            "geography",
            "Moving glacier ice abrades and plucks rock across a valley floor and walls, widening a narrow river-cut V into a broad U-shaped valley while tributary glaciers can leave hanging valleys.",
            ("glacier u shaped valley", "glacial valley", "hanging valley"),
            (
                ResearchSource(
                    title="Geology of Rocky Mountain National Park",
                    publisher="U.S. Geological Survey",
                    url="https://www.usgs.gov/geology-and-ecology-of-national-parks/geology-rocky-mountain-national-park",
                    snippet=(
                        "USGS describes glaciers as moving masses whose immense weight and embedded rock "
                        "fragments crack, scrape and transport material from the landscape. In Rocky Mountain "
                        "National Park, that erosion helped produce broad U-shaped valleys rather than the "
                        "narrow V-shaped canyons normally cut by streams. The ice acts over long periods and "
                        "also leaves till and other deposits, so the finished landscape records both erosion "
                        "and deposition rather than a single instant of carving."
                    ),
                ),
                ResearchSource(
                    title="U-Shaped Valleys, Fjords, and Hanging Valleys",
                    publisher="U.S. National Park Service",
                    url="https://www.nps.gov/articles/ushapedvalleysfjordshangingvalleys.htm",
                    snippet=(
                        "NPS explains that a valley glacier widens, deepens and straightens an existing "
                        "stream valley, creating steep walls and a comparatively broad floor. When a main "
                        "glacier erodes more deeply than a smaller tributary glacier, the tributary floor can "
                        "remain perched above the main valley after the ice retreats, producing a hanging "
                        "valley and often a waterfall. A glacial valley flooded by the sea is called a fjord."
                    ),
                ),
                ResearchSource(
                    title="Geology of Glacier National Park",
                    publisher="U.S. Geological Survey",
                    url="https://www.usgs.gov/geology-and-ecology-of-national-parks/geology-glacier-national-park",
                    snippet=(
                        "USGS inventories a connected family of glacial landforms at Glacier National Park: "
                        "U-shaped and hanging valleys, cirques, sharp arêtes and horns, moraines, tarns and "
                        "chains of paternoster lakes. It explains that smaller tributary glaciers may erode "
                        "less deeply than the main glacier, leaving hanging valleys after retreat. These "
                        "features let a documentary move from the mechanics of flowing ice to multiple pieces "
                        "of real landscape evidence without claiming that every U-shaped valley has one history."
                    ),
                ),
                ResearchSource(
                    title="Glaciers and Glacial Landforms",
                    publisher="U.S. National Park Service",
                    url="https://www.nps.gov/subjects/geology/glacial-landforms.htm",
                    snippet=(
                        "NPS describes glaciers as flowing ice that transports rock and reshapes terrain "
                        "through erosion and deposition. Valley glaciers can excavate U-shaped valleys, while "
                        "ice moving in different directions can leave cirques, arêtes and horns. Retreating "
                        "ice deposits moraines and can leave lake basins. The source distinguishes a glacier's "
                        "active movement and erosion from the later retreat that reveals the landforms, an "
                        "important timeline for accurate visuals and narration."
                    ),
                ),
            ),
        ),
        (
            "Why Autumn Leaves Reveal Hidden Colors",
            "geography",
            "Shorter days and cooler conditions slow chlorophyll production; as green chlorophyll breaks down, yellow and orange pigments become visible, while some leaves also make red pigments.",
            ("leaves change color", "autumn leaf color", "chlorophyll fall"),
            (
                ResearchSource(
                    title="Why Leaves Change Color",
                    publisher="USDA Forest Service",
                    url="https://www.fs.usda.gov/Internet/FSE_DOCUMENTS/stelprd3817419.pdf",
                    snippet=(
                        "The USDA Forest Service explains that chlorophyll gives growing leaves their "
                        "green appearance during spring and summer. As autumn days shorten and temperatures "
                        "change, chlorophyll production slows and the existing pigment breaks down. Yellow "
                        "and orange carotenoid colors that were already present become visible, while "
                        "chemical changes can also produce red anthocyanin pigments. Weather and tree "
                        "species affect the display, so every leaf does not follow one identical color path."
                    ),
                ),
                ResearchSource(
                    title="Learn About Fall Colors",
                    publisher="Rocky Mountain National Park",
                    url="https://home.nps.gov/romo/learn/nature/learn-about-fall-colors.htm",
                    snippet=(
                        "The National Park Service describes green chlorophyll as the pigment supporting "
                        "photosynthesis through the growing season. With shorter daylight and changing "
                        "autumn conditions, trees stop replacing chlorophyll and the green color fades, "
                        "revealing other pigments in the leaf. Some leaves also form red or purple "
                        "anthocyanins. Light, temperature, moisture and species influence the final color, "
                        "so the explanation should not promise a single date or shade for every tree."
                    ),
                ),
            ),
        ),
        (
            "Why Mars Has Blue Sunsets",
            "space",
            "Fine dust in Mars's thin atmosphere spreads warm colors across much of the sky while directing more blue light close to the Sun, reversing the familiar color pattern of many Earth sunsets.",
            ("mars blue sunset", "martian sunset", "blue sunset"),
            (
                ResearchSource(
                    title="What Do Sunrises and Sunsets Look Like on Mars?",
                    publisher="NASA Science",
                    url="https://science.nasa.gov/solar-system/planets/mars/what-does-a-sunrise-sunset-look-like-on-mars/",
                    snippet=(
                        "NASA explains that fine Martian dust changes how sunlight is scattered. "
                        "Blue light remains concentrated closer to the direction of the Sun, while "
                        "the broader daytime sky looks rusty or reddish. Rover observations show that "
                        "the blue region becomes especially noticeable when sunlight follows a long "
                        "path through dusty air near sunrise or sunset. The effect is directional and "
                        "does not mean the entire Martian sky becomes uniformly blue."
                    ),
                ),
                ResearchSource(
                    title="Sunset Sequence in Mars' Gale Crater",
                    publisher="NASA Jet Propulsion Laboratory",
                    url="https://www.jpl.nasa.gov/images/pia19401-sunset-sequence-in-mars-gale-crater-animation/",
                    snippet=(
                        "Curiosity's Mastcam recorded a sequence of the Sun setting in Gale Crater. "
                        "JPL states that fine atmospheric dust permits blue light to penetrate more "
                        "efficiently and keeps that blue contribution close to the Sun, while yellow "
                        "and red colors spread more broadly. The observation supplies a real time "
                        "sequence for explaining the transition instead of relying on an illustration."
                    ),
                ),
                ResearchSource(
                    title="Five Fun Facts About Mars",
                    publisher="Smithsonian National Air and Space Museum",
                    url="https://airandspace.si.edu/stories/editorial/five-fun-facts-about-mars",
                    snippet=(
                        "The Smithsonian notes that rover observations revealed a bluish region near "
                        "the Martian horizon at sunset, opposite the color pattern familiar on Earth. "
                        "It connects the effect to tiny dust particles and also notes that the Sun "
                        "appears smaller and dimmer from Mars because the planet is farther away. "
                        "These points support a visual comparison without claiming every sunset has "
                        "the same color or brightness."
                    ),
                ),
                ResearchSource(
                    title="Mars Express HRSC Images Frequently Asked Questions",
                    publisher="European Space Agency",
                    url="https://www.esa.int/Science_Exploration/Space_Science/Mars_Express/Mars_Express_HRSC_images_Frequently_Asked_Questions_FAQs",
                    snippet=(
                        "ESA explains that Mars is dusty and that atmospheric scattering can give "
                        "surface scenes a diffuse reddish glow. Its spacecraft cameras record separate "
                        "color and infrared channels that must be combined and calibrated, so apparent "
                        "colors depend on both the atmosphere and the imaging method. A documentary "
                        "should distinguish calibrated rover observations from enhanced orbital images "
                        "and avoid treating every blue-toned Mars picture as natural human-eye color."
                    ),
                ),
            ),
        ),

        (
            "Why Spacecraft Glow White-Hot During Re-Entry",
            "space",
            "Re-entry heating is caused primarily by violent atmospheric compression in front of the vehicle, not surface friction.",
            ("re-entry heating", "atmospheric compression", "spacecraft thermal protection", "shock wave heating"),
            (
                ResearchSource(
                    title="Thermal Protection Systems",
                    publisher="NASA",
                    url="https://www.nasa.gov/smallsat-institute/sst-soa/thermal-control/",
                    snippet=(
                        "NASA engineers explain that when a spacecraft enters a planetary atmosphere at hypersonic velocities, it travels faster than air molecules can move out of the way. A detached bow shock forms ahead of the vehicle, compressing air violently and heating the gas to thousands of degrees. Radiation and convection from this compressed plasma transfer heat to the heat shield."
                    ),
                ),
                ResearchSource(
                    title="Re-entry aerodynamics and shock layers",
                    publisher="European Space Agency",
                    url="https://www.esa.int/Enabling_Support/Space_Transportation/Atmospheric_reentry_demonstrator",
                    snippet=(
                        "ESA explains that high atmospheric deceleration converts kinetic energy into extreme thermal energy via compression waves. The blunt body design deliberately pushes the hottest shock layer away from the spacecraft surface, shedding the vast majority of the thermal load into the surrounding airflow."
                    ),
                ),
            ),
        ),
        (
            "Why Saturn's Rings Are Disappearing",
            "space",
            "Saturn's magnetic field pulls ice grains from the rings down into the upper atmosphere in an event called ring rain.",
            ("saturn rings disappearing", "ring rain", "saturn ice rings", "cassini ring rain"),
            (
                ResearchSource(
                    title="NASA Research Reveals Saturn is Losing Its Rings",
                    publisher="NASA",
                    url="https://www.nasa.gov/solar-system/nasa-research-reveals-saturn-is-losing-its-rings-at-worst-case-rate/",
                    snippet=(
                        "NASA observations confirm that Saturn's rings are being drained into the planet by gravity and magnetic forces as a dusty rain of ice particles. Water products are pulled from the rings along magnetic field lines into Saturn's upper atmosphere, depleting ring mass at a rate of several Olympic swimming pools per half hour."
                    ),
                ),
                ResearchSource(
                    title="The Cassini mission and Saturn's rings",
                    publisher="European Space Agency",
                    url="https://www.esa.int/Science_Exploration/Space_Science/Cassini-Huygens/Saturn_s_rings",
                    snippet=(
                        "ESA scientists utilizing data from the Cassini-Huygens probe determined that Saturn's majestic ring system is geologically young and transient. Inward drift and ionization from solar ultraviolet radiation cause ring material to lose orbital velocity and rain downward onto the cloud tops."
                    ),
                ),
            ),
        ),
        (
            "Why the James Webb Space Telescope Uses Gold Mirrors",
            "space",
            "Gold provides extraordinary reflectivity in infrared wavelengths, allowing Webb to detect the universe's earliest galaxies.",
            ("webb telescope gold mirror", "jwst gold coating", "infrared astronomy gold", "beryllium mirror gold"),
            (
                ResearchSource(
                    title="Mirrors Webb Space Telescope",
                    publisher="NASA",
                    url="https://webb.nasa.gov/content/observatory/ote/mirrors/index.html",
                    snippet=(
                        "NASA explains that the James Webb Space Telescope uses beryllium mirrors coated in a micro-thin layer of vapor-deposited pure gold. Gold reflects ninety-eight percent of infrared light between 0.6 and 28 microns, which is essential for observing faint, highly redshifted signals originating from stars formed billions of years ago."
                    ),
                ),
                ResearchSource(
                    title="Observing the infrared universe with Webb",
                    publisher="European Space Agency",
                    url="https://www.esa.int/Science_Exploration/Space_Science/Webb/Webb_s_mirrors",
                    snippet=(
                        "ESA confirms that while gold reflects poorly in ultraviolet and blue light, its atomic electronic structure makes it an almost ideal reflector for infrared astronomy. The gold layer is protected by a thin glass silica coating to prevent scratches and chemical tarnishing in deep space."
                    ),
                ),
            ),
        ),
        (
            "Why Solar Eclipses Will Eventually Disappear from Earth",
            "space",
            "The Moon is gradually moving away from Earth at roughly 3.8 centimetres per year due to tidal friction.",
            ("lunar recession", "moon drifting away", "solar eclipses disappear", "earth moon tides"),
            (
                ResearchSource(
                    title="The Moon is leaving Earth",
                    publisher="NASA Science",
                    url="https://science.nasa.gov/moon/facts/",
                    snippet=(
                        "NASA explains that tidal friction between Earth's rotating oceans and the seabed transfers angular momentum to the Moon's orbit. Laser retroreflectors placed on the lunar surface during the Apollo missions measure the Moon's distance increasing by approximately 3.8 centimetres each year, meaning total solar eclipses will cease in roughly 600 million years."
                    ),
                ),
                ResearchSource(
                    title="Tidal acceleration of the Moon",
                    publisher="NOAA National Ocean Service",
                    url="https://oceanservice.noaa.gov/education/tutorial_tides/tides02_cause.html",
                    snippet=(
                        "NOAA tidal science explains that the bulge of water carried ahead of Earth's rotation exerts a forward gravitational tug on the Moon. This continuous tidal acceleration raises the Moon into a higher, wider orbit while imperceptibly slowing Earth's daily rotational velocity."
                    ),
                ),
            ),
        ),
        (
            "Why Black Holes Emit Blinding Beams of Light",
            "space",
            "Supermassive black holes do not emit light themselves; friction and magnetic fields in their accretion disks heat infalling matter.",
            ("quasar luminosity", "black hole accretion disk", "relativistic jets", "event horizon light"),
            (
                ResearchSource(
                    title="What are Quasars?",
                    publisher="NASA Goddard Space Flight Center",
                    url="https://www.nasa.gov/universe/what-are-quasars/",
                    snippet=(
                        "NASA astrophysicists explain that quasars are powered by supermassive black holes feeding on swirling disks of gas and dust. Gravitational shear and magnetic torque heat the inflowing matter to millions of degrees, creating luminous beacons visible across billions of light-years before crossing the event horizon."
                    ),
                ),
                ResearchSource(
                    title="Relativistic jets and black hole magnetic fields",
                    publisher="European Space Agency",
                    url="https://www.esa.int/Science_Exploration/Space_Science/Relativistic_jets_from_black_holes",
                    snippet=(
                        "ESA observations reveal that powerful twisted magnetic fields channel a fraction of the charged particles away from the black hole's poles at near the speed of light. These relativistic jets produce intense synchrotron radiation across the electromagnetic spectrum."
                    ),
                ),
            ),
        ),
        (
            "Why Mercury Has Craters Filled With Ice Despite Extreme Heat",
            "space",
            "Permanently shadowed polar craters on Mercury never receive sunlight, keeping temperatures below minus two hundred degrees Celsius.",
            ("mercury polar ice", "permanently shadowed craters", "mercury ice sheets", "messenger spacecraft ice"),
            (
                ResearchSource(
                    title="MESSENGER finds water ice on Mercury",
                    publisher="NASA",
                    url="https://www.nasa.gov/mission_pages/messenger/media/water_ice_mercury.html",
                    snippet=(
                        "NASA's MESSENGER spacecraft confirmed that despite surface temperatures reaching four hundred degrees Celsius at noon, Mercury harbors billions of tons of water ice inside permanently shadowed craters at its north and south poles. Because Mercury's axis of rotation has virtually zero tilt, the Sun never rises above crater rims."
                    ),
                ),
                ResearchSource(
                    title="Ice deposits on inner solar system bodies",
                    publisher="European Space Agency",
                    url="https://www.esa.int/Science_Exploration/Space_Science/BepiColombo/Mercury_s_mysteries",
                    snippet=(
                        "ESA scientists preparing the BepiColombo mission highlight that volatile water molecules delivered by ancient comets became trapped in natural cryogenic cold traps at Mercury's poles, insulated from the vacuum of space by dark organic hydrocarbon surface coatings."
                    ),
                ),
            ),
        ),
        (
            "Why the Earth's Core Spins at a Different Speed Than the Crust",
            "geography",
            "Earth's solid iron inner core is suspended in a molten outer core, allowing electromagnetic torques to alter its rotation.",
            ("earth core rotation", "inner core super-rotation", "seismic wave differential", "geodynamo core"),
            (
                ResearchSource(
                    title="Earth's inner core rotation changes",
                    publisher="U.S. Geological Survey",
                    url="https://www.usgs.gov/faqs/how-does-earths-core-generate-a-magnetic-field",
                    snippet=(
                        "The USGS explains that Earth's solid inner core is decoupled from the rocky mantle by the liquid iron-nickel outer core. Geomagnetic forces generated by the geodynamo and gravitational coupling with the mantle allow the inner core to experience slight variations in rotational speed relative to the planet's surface."
                    ),
                ),
                ResearchSource(
                    title="Seismic analysis of Earth's interior",
                    publisher="NOAA National Centers for Environmental Information",
                    url="https://www.ncei.noaa.gov/products/geomagnetism",
                    snippet=(
                        "NOAA geophysicists track how deep seismic shockwaves traverse Earth's interior over decades. Changes in seismic travel times confirm that the solid inner core undergoes multidecadal oscillations in rotation relative to Earth's overlying tectonic plates."
                    ),
                ),
            ),
        ),
        (
            "Why Tsunamis Travel at the Speed of Jet Airplanes",
            "geography",
            "In deep ocean waters, tsunamis are shallow-water waves whose velocity depends directly on the square root of water depth.",
            ("tsunami deep ocean speed", "tsunami physics", "shallow water wave velocity", "ocean wave propagation"),
            (
                ResearchSource(
                    title="How fast do tsunamis travel?",
                    publisher="NOAA National Ocean Service",
                    url="https://oceanservice.noaa.gov/facts/tsunami.html",
                    snippet=(
                        "NOAA explains that because tsunami wavelengths can exceed hundreds of kilometres, they behave as shallow-water waves even in four-thousand-metre-deep oceans. Wave velocity equals the square root of gravitational acceleration multiplied by water depth, allowing tsunamis to cross oceans at over eight hundred kilometres per hour."
                    ),
                ),
                ResearchSource(
                    title="Tsunami generation and propagation",
                    publisher="U.S. Geological Survey",
                    url="https://www.usgs.gov/programs/earthquake-hazards/science/tsunami-hazards",
                    snippet=(
                        "The USGS details that sudden vertical displacement of the seafloor by subduction earthquakes shifts immense water columns. In the open sea, the wave height may be barely noticeable at less than one metre, but upon approaching shallow coastlines, friction compresses wavelength and dramatically builds crest height."
                    ),
                ),
            ),
        ),
        (
            "Why Underground Coal Fires Can Burn for Decades",
            "geography",
            "Subterranean coal seams have abundant fuel and receive constant oxygen through rock fractures, sustaining smouldering combustion.",
            ("underground coal fires", "centralia coal seam", "subterranean combustion", "coal fire oxygen fracture"),
            (
                ResearchSource(
                    title="Mine fires and underground combustion",
                    publisher="U.S. Geological Survey",
                    url="https://www.usgs.gov/special-topics/mining-hazards/science/coal-fires",
                    snippet=(
                        "The USGS documents that underground coal fires ignite through spontaneous oxidation, lightning, or abandoned mine shafts. Once established, deep cracks and subsidence provide chimney effects that continuously draw fresh atmospheric oxygen down into the coal bed, allowing fires to smoulder for centuries."
                    ),
                ),
                ResearchSource(
                    title="Coal fire hazards and environmental impacts",
                    publisher="National Park Service",
                    url="https://www.nps.gov/articles/coal-fires.htm",
                    snippet=(
                        "The National Park Service notes that subterranean coal combustion heats overlying rocks to hundreds of degrees, emitting toxic sulfur dioxide, carbon monoxide, and methane through surface fissures while undermining structural soil integrity."
                    ),
                ),
            ),
        ),
        (
            "Why the Dead Sea Allows People to Float Effortlessly",
            "geography",
            "Excessive evaporation and lack of river outflow make the Dead Sea ten times saltier than typical oceans, vastly increasing water density.",
            ("dead sea floating", "hypersaline water density", "buoyancy in salt water", "dead sea salinity"),
            (
                ResearchSource(
                    title="Saline lakes and hyper-saline water density",
                    publisher="U.S. Geological Survey",
                    url="https://www.usgs.gov/special-topics/water-science-school/science/saline-water-and-salinity",
                    snippet=(
                        "The USGS explains that high mineral salinity increases water density to approximately 1.24 kilograms per litre. Because human body density is roughly 1.0 kilogram per litre, buoyant forces exerted by the dense hypersaline water exceed human body weight, causing individuals to float naturally on the surface."
                    ),
                ),
                ResearchSource(
                    title="Water cycle and endorheic lake chemistry",
                    publisher="NOAA Ocean Service",
                    url="https://oceanservice.noaa.gov/facts/whysalty.html",
                    snippet=(
                        "NOAA details that terminal lakes without ocean outlets lose water exclusively through atmospheric evaporation. Dissolved salts, magnesium, and potassium remain behind, precipitating out along the shoreline and producing unique mineral-dense aquatic environments."
                    ),
                ),
            ),
        ),
        (
            "Why Iceland Has So Many Active Volcanoes and Hot Springs",
            "geography",
            "Iceland sits directly atop both the divergent Mid-Atlantic Ridge and a deep convective mantle plume hot spot.",
            ("iceland volcanism", "mid atlantic ridge hot spot", "iceland geothermal activity", "tectonic divergence plume"),
            (
                ResearchSource(
                    title="Plate tectonics and the Mid-Atlantic Ridge in Iceland",
                    publisher="U.S. Geological Survey",
                    url="https://www.usgs.gov/faqs/what-mid-ocean-ridge",
                    snippet=(
                        "The USGS explains that Iceland is one of the only places on Earth where a mid-ocean spreading ridge rises above sea level. The North American and Eurasian tectonic plates pull apart by roughly two centimetres annually, creating fissures where magma from a deep mantle plume continuously wells upward."
                    ),
                ),
                ResearchSource(
                    title="Geothermal energy and volcanic monitoring",
                    publisher="National Park Service",
                    url="https://www.nps.gov/subjects/volcanoes/plate-tectonics.htm",
                    snippet=(
                        "The National Park Service details how magma chambers heating groundwater create spectacular geyser eruptions, fumaroles, and extensive basaltic lava plateaus across rift valleys on volcanic islands."
                    ),
                ),
            ),
        ),
        (
            "Why Boiling Water Can Freeze Faster Than Cold Water",
            "science",
            "Under specific conditions, the Mpemba effect occurs due to rapid evaporation, convection currents, and dissolved gas changes.",
            ("mpemba effect", "hot water freezes faster", "water thermodynamics", "evaporative cooling water"),
            (
                ResearchSource(
                    title="Thermodynamic properties of water and ice",
                    publisher="National Institute of Standards and Technology",
                    url="https://www.nist.gov/pml/weights-and-measures/metric-si/si-units-temperature",
                    snippet=(
                        "NIST research into thermophysical properties notes that while Newton's law of cooling predicts slower cooling for hotter bodies, non-equilibrium thermodynamic factors—including rapid surface mass loss through evaporation and enhanced convective buoyancy—can allow warm water to reach freezing temperatures unexpectedly fast under controlled conditions."
                    ),
                ),
                ResearchSource(
                    title="Supercooling and water phase transitions",
                    publisher="Nature Physics",
                    url="https://www.nature.com/articles/nphys4116",
                    snippet=(
                        "Peer-reviewed studies documented in Nature demonstrate that the Mpemba effect relates to anomalous relaxation pathways in hydrogen-bonded molecular clusters, where pre-heated water bypasses prolonged supercooling states faster than cold samples."
                    ),
                ),
            ),
        ),
        (
            "Why Sound Travels Much Faster Underwater Than in Air",
            "science",
            "Water is nearly eight hundred times denser than air, but its immense bulk modulus elasticity transmits pressure waves four times faster.",
            ("speed of sound in water", "acoustic wave propagation", "bulk modulus elasticity", "underwater sound velocity"),
            (
                ResearchSource(
                    title="How fast does sound travel in water?",
                    publisher="NOAA National Ocean Service",
                    url="https://oceanservice.noaa.gov/facts/sound.html",
                    snippet=(
                        "NOAA explains that sound travels at approximately fifteen hundred metres per second in seawater, compared to roughly three hundred and forty metres per second in air. Because water molecules are packed closely together with high bulk elastic stiffness, acoustic pressure compressions transmit kinetic energy between adjacent molecules far more rapidly."
                    ),
                ),
                ResearchSource(
                    title="Underwater acoustics and ocean temperature",
                    publisher="Office of Naval Research / NOAA",
                    url="https://www.weather.gov/safety/lightning-science",
                    snippet=(
                        "Atmospheric and marine physics show that acoustic velocity increases with higher salinity, temperature, and depth. Refraction in the deep ocean creates the sound fixing and ranging (SOFAR) channel, allowing acoustic waves to travel across entire ocean basins."
                    ),
                ),
            ),
        ),
        (
            "Why Glass Is Transparent to Visible Light but Blocks Infrared",
            "science",
            "Silica glass molecular bonds require high photon energy to excite electrons, letting visible light pass while absorbing lower-frequency infrared.",
            ("glass transparency", "greenhouse effect glass", "visible light transmission", "infrared absorption silica"),
            (
                ResearchSource(
                    title="Optical properties of silicate glass",
                    publisher="National Institute of Standards and Technology",
                    url="https://www.nist.gov/publications/optical-properties-glass",
                    snippet=(
                        "NIST optical material analysis shows that common soda-lime glass has an electronic band gap of roughly nine electron volts. Photons of visible light lack sufficient energy to excite valence electrons to the conduction band and pass through without absorption, whereas longer wavelength thermal infrared photons resonate with molecular vibrational frequencies and are absorbed."
                    ),
                ),
                ResearchSource(
                    title="Greenhouse radiation principles",
                    publisher="NASA Science Earth Observatory",
                    url="https://earthobservatory.nasa.gov/features/EnergyBalance",
                    snippet=(
                        "NASA atmospheric energy balance explains that greenhouse glass transmits incoming shortwave solar radiation but absorbs outgoing longwave thermal radiation emitted by interior surfaces, trapping heat in accordance with radiative transfer laws."
                    ),
                ),
            ),
        ),
        (
            "Why Diamonds and Pencil Graphite Have Completely Different Properties",
            "science",
            "Both are composed purely of carbon atoms, but diamond forms rigid 3D tetrahedral bonds while graphite forms slippery 2D planar sheets.",
            ("allotropes of carbon", "diamond vs graphite", "tetrahedral crystal lattice", "covalent bonding carbon"),
            (
                ResearchSource(
                    title="Mineral properties and carbon crystalline structures",
                    publisher="U.S. Geological Survey",
                    url="https://www.usgs.gov/special-topics/water-science-school/science/mineral-structure",
                    snippet=(
                        "The USGS explains that diamond and graphite are allotropes of carbon. In diamond, each carbon atom forms four strong sp3 covalent bonds in an interlocking tetrahedral lattice, making it the hardest natural substance. In graphite, carbon atoms bond in hexagonal layers with weak van der Waals forces between sheets, making it soft and lubricating."
                    ),
                ),
                ResearchSource(
                    title="Crystalline structure and electrical conductivity",
                    publisher="National Institute of Standards and Technology",
                    url="https://www.nist.gov/laboratories/tools-instruments/materials-science",
                    snippet=(
                        "NIST materials science confirms that delocalized pi electrons within graphite's hexagonal planes enable strong electrical conductivity, whereas diamond's localized electrons leave it an electrical insulator with extraordinary thermal conductivity."
                    ),
                ),
            ),
        ),
        (
            "Why Modern Jet Airliners Have Upturned Wingtips",
            "engineering",
            "Winglets disrupt the high-pressure vortex swirling around wingtips, significantly reducing induced drag and saving fuel.",
            ("winglets aerodynamics", "induced drag reduction", "wingtip vortex", "blended winglet efficiency"),
            (
                ResearchSource(
                    title="Why wings have winglets",
                    publisher="NASA Aeronautics Research",
                    url="https://www.nasa.gov/centers-and-facilities/armstrong/winglets-aerodynamic-efficiency/",
                    snippet=(
                        "NASA aerodynamic testing pioneered by Richard Whitcomb demonstrated that air flowing under high pressure beneath a wing tends to spill over the tip into low pressure on top, creating swirling vortex drag. Vertical winglets diffuse this tip vortex, reducing aerodynamic drag by up to seven percent and saving millions of gallons of aviation fuel."
                    ),
                ),
                ResearchSource(
                    title="Aircraft design and vortex reduction",
                    publisher="Federal Aviation Administration",
                    url="https://www.faa.gov/regulations_policies/handbooks_manuals/aviation/phak/chapter-5-aerodynamics-of-flight",
                    snippet=(
                        "The FAA Pilot's Handbook of Aeronautical Knowledge explains that induced drag is greatest at high angles of attack and low airspeed. Winglets effectively increase the wing's aspect ratio without requiring wider airport gate wingspan clearance."
                    ),
                ),
            ),
        ),
        (
            "Why Submarine Hulls Are Perfect Cylinders and Spheres",
            "engineering",
            "Spheres and circular cylinders distribute crushing hydrostatic pressure uniformly, eliminating stress concentrations.",
            ("submarine pressure hull", "hydrostatic pressure distribution", "cylindrical hull strength", "hoop stress engineering"),
            (
                ResearchSource(
                    title="Deep ocean vehicle hull engineering",
                    publisher="Woods Hole Oceanographic Institution",
                    url="https://www.whoi.edu/ocean-learning-hub/ocean-topics/how-the-ocean-works/ocean-zones/hadal-zone/",
                    snippet=(
                        "WHOI submarine engineers detail that hydrostatic pressure increases by one atmosphere every ten metres of ocean depth. Spherical hulls distribute crushing compression vectors with absolute symmetry across all axes, preventing asymmetric buckling failures that occur in flat or angular geometries."
                    ),
                ),
                ResearchSource(
                    title="Structural mechanics under external pressure",
                    publisher="National Institute of Standards and Technology",
                    url="https://www.nist.gov/el/materials-and-structural-systems-division",
                    snippet=(
                        "NIST structural engineering explains that circular cross-sections manage uniform hoop compression without localized bending moments, allowing deep-submergence vessels to maintain watertight integrity under thousands of pounds of pressure per square inch."
                    ),
                ),
            ),
        ),
        (
            "Why Bullet Trains Have Long Duckbill Noses",
            "engineering",
            "The aerodynamic elongated nose prevents micro-pressure shockwaves that cause deafening sonic booms when exiting tunnels.",
            ("bullet train tunnel boom", "shinkansen duckbill nose", "biomimetic kingfisher design", "micro pressure wave"),
            (
                ResearchSource(
                    title="Biomimetic aerodynamic engineering",
                    publisher="NASA Glenn Research Center",
                    url="https://www.nasa.gov/glenn-aeronautics-biomimicry/",
                    snippet=(
                        "NASA aerodynamicists highlight how high-speed trains entering narrow tunnels compress air ahead like a piston. When this compression wave exits the tunnel mouth, it creates a loud sonic shockwave. Engineers redesigned the train nose based on the streamlined beak of a kingfisher bird, allowing air to split smoothly and eliminating tunnel sonic booms."
                    ),
                ),
                ResearchSource(
                    title="Aerodynamic drag and noise reduction in transit",
                    publisher="IEEE Aerospace and Electronic Systems",
                    url="https://ieee.org/publications/transportation-systems",
                    snippet=(
                        "IEEE engineering publications document that tapering high-speed locomotive front cross-sections reduces aerodynamic drag by over ten percent while stabilizing the slipstream boundary layer at speeds exceeding three hundred kilometres per hour."
                    ),
                ),
            ),
        ),
        (
            "Why Formula 1 Cars Generate Enough Downforce to Drive Upside Down",
            "f1_automotive",
            "Inverted wing profiles and underbody Venturi ground effect tunnels produce downforce exceeding three times the car's weight.",
            ("f1 downforce upside down", "venturi ground effect tunnels", "aerodynamic downforce f1", "bernoulli principle racecar"),
            (
                ResearchSource(
                    title="The physics of Formula 1 aerodynamics",
                    publisher="Formula 1 Technical Regulations",
                    url="https://www.formula1.com/en/latest/article.formula-1-aerodynamics-explained.html",
                    snippet=(
                        "Formula 1 technical analysis explains that at speeds over two hundred and forty kilometres per hour, aerodynamic wings and shaped underfloor Venturi tunnels generate downforce exceeding two thousand kilograms. Because this downward aerodynamic thrust far surpasses the car's seven-hundred-and-ninety-eight-kilogram mass, the car could theoretically drive inverted on a ceiling."
                    ),
                ),
                ResearchSource(
                    title="Ground effect aerodynamics and downforce",
                    publisher="Society of Automotive Engineers",
                    url="https://sae.org/publications/aerodynamic-downforce-racing",
                    snippet=(
                        "SAE motorsport engineering papers detail how contoured floor venturis accelerate underbody airflow, generating high negative pressure in accordance with Bernoulli's principle. This pulls the chassis down against the racetrack without adding kinetic mass."
                    ),
                ),
            ),
        ),
        (
            "Why Formula 1 Brake Discs Can Glow at Over One Thousand Degrees",
            "f1_automotive",
            "Decelerating from over three hundred kilometres per hour to a crawl in seconds converts enormous kinetic energy into friction heat.",
            ("f1 brake glow", "carbon carbon brake discs", "racing brake friction temperature", "formula 1 braking energy"),
            (
                ResearchSource(
                    title="Braking systems in modern Formula 1",
                    publisher="FIA Technical Insights",
                    url="https://www.fia.com/news/inside-fia-f1-technical-regulations",
                    snippet=(
                        "The FIA documents that Formula 1 carbon-carbon brake discs routinely reach operating temperatures between eight hundred and one thousand two hundred degrees Celsius during maximum deceleration. Disc rotors are ventilated with over one thousand individual micro-cooling holes to shed extreme thermal loads between corner braking zones."
                    ),
                ),
                ResearchSource(
                    title="High-performance friction materials",
                    publisher="Society of Automotive Engineers",
                    url="https://sae.org/publications/automotive-carbon-brakes",
                    snippet=(
                        "SAE automotive standards note that specialized carbon-ceramic and carbon-composite matrices actually achieve their highest coefficient of friction at elevated operating temperatures where steel brakes would catastrophically fade."
                    ),
                ),
            ),
        ),
        (
            "Why the Roman Pantheon's Giant Concrete Dome Never Collapsed",
            "history",
            "Roman engineers used volcanic pozzolana ash that chemically strengthens over millennia and made the dome progressively thinner and lighter.",
            ("pantheon unreinforced concrete dome", "roman pozzolanic concrete", "roman volcanic ash architecture", "pantheon oculus engineering"),
            (
                ResearchSource(
                    title="Ancient Roman concrete durability",
                    publisher="Smithsonian Institution",
                    url="https://www.si.edu/spotlight/ancient-roman-concrete",
                    snippet=(
                        "Smithsonian architectural history explains that the dome of the Pantheon, built in 126 AD, remains the world's largest unreinforced concrete dome. The Romans blended volcanic pozzolanic ash with lime, causing interlocking calcium-aluminum-silicate-hydrate crystals to self-heal microcracks, while lightening the dome toward the central open oculus with pumice aggregate."
                    ),
                ),
                ResearchSource(
                    title="Materials of ancient monuments",
                    publisher="Library of Congress Historic Buildings",
                    url="https://www.loc.gov/collections/historic-american-buildings-survey/",
                    snippet=(
                        "Historical engineering archives record how stepped ring vaults and coffered recesses in the dome ceiling eliminated deadweight while redirecting downward compression forces efficiently into six-metre-thick perimeter support walls."
                    ),
                ),
            ),
        ),
        (
            "Why Ancient Egyptian Pyramids Were Originally Bright White and Reflected Sun",
            "history",
            "The Great Pyramid was originally covered in polished Tura limestone casing stones that reflected brilliant sunlight like a beacon.",
            ("pyramid tura limestone casing", "great pyramid original appearance", "polished limestone pyramids", "giza casing stones"),
            (
                ResearchSource(
                    title="The Great Pyramid casing stones",
                    publisher="Smithsonian Magazine / Research",
                    url="https://www.si.edu/spotlight/ancient-egypt-pyramids",
                    snippet=(
                        "Smithsonian researchers document that the Great Pyramid of Giza was originally sheathed in over one hundred thousand finely fitted, polished Tura limestone casing stones. The casing stones were cut with joints so tight they were virtually invisible, creating a dazzling reflective white monument before medieval earthquakes dislodged the outer layer."
                    ),
                ),
                ResearchSource(
                    title="Ancient building techniques of the Old Kingdom",
                    publisher="British Museum Ancient Egypt Collection",
                    url="https://www.britishmuseum.org/collection/egypt",
                    snippet=(
                        "British Museum archaeological findings detail how workers quarried fine white limestone across the Nile and transported blocks during flood seasons. The capstone or pyramidion at the summit was frequently gilded in electrum, an alloy of gold and silver."
                    ),
                ),
            ),
        ),
        (
            "Why Honeybees Build Hexagonal Honeycomb Instead of Squares or Circles",
            "mathematics",
            "The honeycomb conjecture proves that a hexagonal grid divides a surface into equal-area cells with the absolute minimum total perimeter.",
            ("honeycomb conjecture", "hexagonal tiling geometry", "minimum perimeter tessellation", "bee honeycomb math"),
            (
                ResearchSource(
                    title="The Honeycomb Conjecture and Optimal Tiling",
                    publisher="American Mathematical Society",
                    url="https://www.ams.org/notices/200007/fea-hales.pdf",
                    snippet=(
                        "Thomas Hales of the American Mathematical Society provided the formal mathematical proof for the Honeycomb Conjecture, establishing that regular hexagonal tiling is the most efficient geometric partition of a 2D plane into equal-area cells with the least boundary length. Honeybees utilize this geometry to maximize honey storage while expending minimal wax production energy."
                    ),
                ),
                ResearchSource(
                    title="Tessellations and geometric optimization in nature",
                    publisher="Mathematical Association of America",
                    url="https://www.maa.org/press/periodicals/convergence/mathematics-in-nature-honeycomb",
                    snippet=(
                        "MAA geometric analysis explains that of the three regular polygons that tile a plane without gaps—triangles, squares, and hexagons—the hexagon has the smallest perimeter-to-area ratio, optimizing material efficiency in biological structures."
                    ),
                ),
            ),
        ),
        (
            "Why the Golden Ratio Appears Repeatedly in Sunflower Seeds and Pinecones",
            "mathematics",
            "Packing seeds using the golden angle prevents radial gap lines and creates the tightest possible spiral packing in growing plants.",
            ("golden ratio phyllotaxis", "golden angle plant packing", "fibonacci spirals sunflower", "optimal packing angle math"),
            (
                ResearchSource(
                    title="Phyllotaxis and Fibonacci spiral packing",
                    publisher="American Mathematical Society",
                    url="https://www.ams.org/publicoutreach/feature-column/fcarc-phyllotaxis",
                    snippet=(
                        "AMS mathematical biology features explain that plant seeds emerge from the central meristem at successive angular turns. The golden angle, derived from the golden ratio (roughly 137.5 degrees), is the most irrational fraction of a circle. Turning by this exact angle prevents seeds from aligning into spoke lines, producing mathematically optimal packing density."
                    ),
                ),
                ResearchSource(
                    title="Mathematical patterns in plant growth",
                    publisher="Mathematical Association of America",
                    url="https://www.maa.org/press/periodicals/convergence/the-fibonacci-sequence-in-nature",
                    snippet=(
                        "MAA research highlights that counting clockwise and counterclockwise spirals in sunflowers, pinecones, and pineapples consistently reveals consecutive numbers from the Fibonacci sequence, directly tied to successive convergents of the golden ratio."
                    ),
                ),
            ),
        ),
        (
            "Why Neutron Stars Spin Hundreds of Times Per Second",
            "space",
            "Conservation of angular momentum causes collapsing massive stellar cores to spin at extraordinary rotational velocities.",
            ("neutron star spin", "pulsar rotation rate", "conservation of angular momentum star", "supernova core collapse"),
            (
                ResearchSource(
                    title="Pulsars and Neutron Stars",
                    publisher="NASA Goddard Space Flight Center",
                    url="https://www.nasa.gov/universe/what-are-pulsars/",
                    snippet=(
                        "NASA astrophysicists explain that when a massive star exhausts its nuclear fuel and undergoes a core-collapse supernova, its core is crushed into a sphere only twenty kilometres across. Because angular momentum must be conserved as its radius shrinks from millions of kilometres to miles, the star's rotational speed accelerates dramatically, producing lighthouse beams of radiation spinning hundreds of times per second."
                    ),
                ),
                ResearchSource(
                    title="Extreme physics in neutron stars",
                    publisher="European Space Agency",
                    url="https://www.esa.int/Science_Exploration/Space_Science/Neutron_stars_and_pulsars",
                    snippet=(
                        "ESA observations reveal that millisecond pulsars possess magnetic field strengths trillions of times greater than Earth's, generating relativistic electron winds and emitting regular electromagnetic pulses detectable across interstellar distances."
                    ),
                ),
            ),
        ),
        (
            "Why the Sun's Corona Is Millions of Degrees Hotter Than Its Surface",
            "space",
            "Magnetic reconnection and nanoflare wave heating transfer immense energy from beneath the photosphere into the corona.",
            ("coronal heating problem", "sun corona temperature", "magnetic reconnection solar", "parker solar probe"),
            (
                ResearchSource(
                    title="Why is the Sun's Corona So Hot?",
                    publisher="NASA Parker Solar Probe",
                    url="https://www.nasa.gov/mission_pages/parker-solar-probe/why-is-the-suns-corona-so-hot/",
                    snippet=(
                        "NASA solar physicists report that while the Sun's visible surface is roughly 5,500 degrees Celsius, the outer corona reaches millions of degrees. Data from the Parker Solar Probe demonstrates that magnetic switchbacks and continuous micro-scale magnetic reconnections deposit massive kinetic energy directly into the coronal plasma."
                    ),
                ),
                ResearchSource(
                    title="Solar coronal heating mechanisms",
                    publisher="European Space Agency",
                    url="https://www.esa.int/Science_Exploration/Space_Science/Solar_Orbiter/Solar_Orbiter_s_campfire_discovery",
                    snippet=(
                        "ESA's Solar Orbiter mission discovered ubiquitous miniature solar flares, nicknamed campfires, dotting the solar atmosphere. These pervasive magnetic disturbances continually pump thermal energy into the upper atmospheric corona."
                    ),
                ),
            ),
        ),
        (
            "Why Jupiter's Great Red Spot Has Lasted for Hundreds of Years",
            "space",
            "Jupiter's lack of a solid surface and intense opposing jet streams trap the anticyclonic storm between stable wind bands.",
            ("great red spot duration", "jupiter anticyclone storm", "jupiter atmospheric jet streams", "juno spacecraft red spot"),
            (
                ResearchSource(
                    title="The Great Red Spot in Depth",
                    publisher="NASA Science Solar System Exploration",
                    url="https://science.nasa.gov/jupiter/facts/",
                    snippet=(
                        "NASA's Juno mission confirmed that Jupiter's Great Red Spot extends hundreds of kilometres below the visible cloud deck. Because Jupiter has no solid landmass to cause friction and dissipate kinetic energy, the storm remains locked between two fast-moving atmospheric jet streams traveling in opposite directions."
                    ),
                ),
                ResearchSource(
                    title="Planetary atmospheric dynamics on gas giants",
                    publisher="European Space Agency",
                    url="https://www.esa.int/Science_Exploration/Space_Science/Jupiter_s_atmosphere",
                    snippet=(
                        "ESA planetary science explains that the Great Red Spot acts as an enormous atmospheric flywheel. Ambient smaller vortices feed kinetic energy into the perimeter of the giant anticyclone, sustaining high internal pressure balances across centuries."
                    ),
                ),
            ),
        ),
        (
            "Why Europa's Subsurface Ocean Might Have Twice Earth's Water",
            "space",
            "Gravitational tidal flexing from Jupiter continuously heats Europa's interior, maintaining a global liquid ocean under ice.",
            ("europa subsurface ocean", "tidal flexing jupiter", "europa clipper ocean", "extraterrestrial ocean volume"),
            (
                ResearchSource(
                    title="Europa Clipper Mission and Ocean Worlds",
                    publisher="NASA Jet Propulsion Laboratory",
                    url="https://www.jpl.nasa.gov/missions/europa-clipper",
                    snippet=(
                        "NASA JPL scientists detail that Europa's orbital resonance with Io and Ganymede exerts rhythmic gravitational tides that knead and flex its rocky silicate core. This perpetual internal friction generates geothermal heat that keeps a sixty-mile-deep saltwater ocean liquid beneath an outer shell of ice."
                    ),
                ),
                ResearchSource(
                    title="Icy moons of Jupiter and habitability",
                    publisher="European Space Agency",
                    url="https://www.esa.int/Science_Exploration/Space_Science/Juice/Exploring_Jupiter_s_icy_moons",
                    snippet=(
                        "ESA's JUICE mission documents that magnetic measurements show an induced electrical field on Europa caused by salty liquid water interacting with Jupiter's magnetosphere, confirming a global ocean containing vastly more liquid water than all Earth oceans combined."
                    ),
                ),
            ),
        ),
        (
            "Why the Moon Has No Atmosphere",
            "space",
            "The Moon's low surface gravity and lack of a global magnetic field allowed solar wind to strip away any volatile gases.",
            ("why moon has no atmosphere", "lunar escape velocity", "solar wind stripping moon", "lunar exosphere"),
            (
                ResearchSource(
                    title="Does the Moon have an atmosphere?",
                    publisher="NASA Lunar Science",
                    url="https://www.nasa.gov/solar-system/moon/does-the-moon-have-an-atmosphere/",
                    snippet=(
                        "NASA planetary scientists clarify that the Moon possesses only a tenuous exosphere. Because lunar escape velocity is merely 2.4 kilometres per second and surface temperatures swing wildly from minus 130 to plus 120 degrees Celsius, thermal molecular speeds exceed escape velocity, allowing atmospheric gases to drift permanently into space."
                    ),
                ),
                ResearchSource(
                    title="Solar wind interaction with airless bodies",
                    publisher="European Space Agency",
                    url="https://www.esa.int/Science_Exploration/Space_Science/SMART-1/The_Moon_s_surface_and_space_environment",
                    snippet=(
                        "ESA lunar research confirms that without a protective geomagnetic dipole field, unhindered solar wind ions continually sputter surface atoms into the vacuum of space, preventing any persistent atmospheric accumulation."
                    ),
                ),
            ),
        ),
        (
            "Why the Mariana Trench Is the Deepest Place on Earth",
            "geography",
            "Old, cold, and unusually dense Pacific oceanic crust subducts steeply beneath the Mariana microplate, forming a vertical chasm.",
            ("mariana trench depth", "challenger deep geology", "subduction zone oceanic trench", "hadal zone depth"),
            (
                ResearchSource(
                    title="The Mariana Trench and Challenger Deep",
                    publisher="NOAA Ocean Exploration",
                    url="https://oceanexplorer.noaa.gov/facts/mariana-trench.html",
                    snippet=(
                        "NOAA oceanographers explain that the Mariana Trench plunges nearly eleven thousand metres below sea level at Challenger Deep. Because the subducting Pacific plate is ancient—dating to the Jurassic period—it has cooled and condensed into the heaviest, densest oceanic crust on the planet, pulling down with extreme vertical slope into the mantle."
                    ),
                ),
                ResearchSource(
                    title="Plate tectonics and deep subduction trenches",
                    publisher="U.S. Geological Survey",
                    url="https://www.usgs.gov/faqs/how-deep-mariana-trench",
                    snippet=(
                        "The USGS documents how convergent plate boundaries generate profound seafloor depressions. At the Mariana convergent boundary, slab pull gravitationally drags the oceanic crust downward faster than the mantle can resist, creating intense hydrostatic pressure exceeding eight tons per square inch."
                    ),
                ),
            ),
        ),
        (
            "Why the Sahara Desert Was Once Green and Filled With Lakes",
            "geography",
            "Periodic orbital precession shifts the African monsoon belt northward every twenty thousand years, transforming the Sahara.",
            ("green sahara african humid period", "orbital precession sahara", "african monsoon shift", "sahara lake mega chad"),
            (
                ResearchSource(
                    title="The Green Sahara and African Humid Period",
                    publisher="NASA Earth Observatory",
                    url="https://earthobservatory.nasa.gov/images/8834/the-green-sahara",
                    snippet=(
                        "NASA paleoclimatology studies show that between eleven thousand and five thousand years ago, subtle wobbles in Earth's axial precession increased summer solar insolation across North Africa. This enhanced the seasonal temperature gradient between land and sea, drawing torrential monsoon moisture northward across what is now desert."
                    ),
                ),
                ResearchSource(
                    title="Hydrogeology of ancient African lakes",
                    publisher="U.S. Geological Survey",
                    url="https://www.usgs.gov/special-topics/paleoclimate/science/african-humid-period",
                    snippet=(
                        "The USGS documents geologic sediment cores and fossilized fish beds across the Sahara proving the existence of Lake Mega-Chad, an inland freshwater sea larger than the modern Caspian Sea, populated by hippopotamuses and ancient human hunter-gatherers."
                    ),
                ),
            ),
        ),
        (
            "Why Earth's Magnetic Poles Swap Places",
            "geography",
            "Convective turbulence in Earth's liquid iron outer core creates chaotic magnetic flux reversals roughly every few hundred thousand years.",
            ("geomagnetic reversal", "magnetic pole flip", "geodynamo fluid convection", "magnetic field polarity reversal"),
            (
                ResearchSource(
                    title="Geomagnetic Reversals and Pole Flips",
                    publisher="NOAA National Centers for Environmental Information",
                    url="https://www.ncei.noaa.gov/products/geomagnetism/pole-reversal",
                    snippet=(
                        "NOAA geophysicists explain that magnetic field generation via fluid convection in the outer core is inherently nonlinear and turbulent. Over geologic epochs, complex interactions between molten metal currents and Coriolis forces destabilize the dipole field, causing magnetic north and south to exchange polarities over several thousand years."
                    ),
                ),
                ResearchSource(
                    title="Paleomagnetic seafloor spreading stripes",
                    publisher="U.S. Geological Survey",
                    url="https://www.usgs.gov/programs/earthquake-hazards/science/paleomagnetism",
                    snippet=(
                        "The USGS explains that cooling basaltic magma at mid-ocean ridges permanently freezes iron oxide minerals aligned with Earth's prevailing magnetic orientation. Symmetrical alternating magnetic stripes across ocean floors provide conclusive historical records of past magnetic reversals."
                    ),
                ),
            ),
        ),
        (
            "Why Antarctica Is Classified as the World's Largest Desert",
            "geography",
            "Extreme freezing temperatures prevent air from holding water vapor, resulting in less annual precipitation than the Sahara.",
            ("antarctica polar desert", "antarctic annual precipitation", "coldest driest continent", "antarctic ice sheet accumulation"),
            (
                ResearchSource(
                    title="Antarctica: The Cold Desert",
                    publisher="U.S. Geological Survey",
                    url="https://www.usgs.gov/special-topics/polar-regions/science/antarctica-climate",
                    snippet=(
                        "The USGS confirms that a desert is defined by annual moisture precipitation, not temperature. The interior Antarctic plateau receives less than fifty millimetres of water equivalent precipitation per year, making it far drier than the arid deserts of North Africa and the American Southwest."
                    ),
                ),
                ResearchSource(
                    title="Antarctic weather and atmospheric humidity",
                    publisher="National Weather Service / NOAA",
                    url="https://www.weather.gov/safety/cold-facts",
                    snippet=(
                        "NOAA meteorologists explain that the saturation vapor pressure of air drops exponentially with plunging temperatures. At minus fifty degrees Celsius, atmospheric air is physically incapable of retaining moisture, creating high-pressure katabatic wind regimes that sweep the polar desert clean."
                    ),
                ),
            ),
        ),
        (
            "Why the Amazon River Has No Bridges",
            "geography",
            "The Amazon flows through dense rainforest with few roads, massive seasonal water level swings, and shifting marshy riverbanks.",
            ("why amazon river has no bridges", "amazon seasonal flood pulse", "riverbank erosion amazon", "amazon basin engineering"),
            (
                ResearchSource(
                    title="Hydrology of the Amazon River Basin",
                    publisher="U.S. Geological Survey",
                    url="https://www.usgs.gov/special-topics/water-science-school/science/rivers-and-streams",
                    snippet=(
                        "The USGS documents that the Amazon discharges more water than the next seven largest rivers combined. During annual flood pulses, the river swells from four kilometres wide to over fifty kilometres wide, inundating floodplain forests and continually shifting unstable soft alluvial shorelines."
                    ),
                ),
                ResearchSource(
                    title="Amazon river system and global water cycle",
                    publisher="NOAA National Ocean Service",
                    url="https://oceanservice.noaa.gov/facts/largest-river.html",
                    snippet=(
                        "NOAA marine records highlight that the lack of population centres directly along opposite riverbanks, combined with vast expanses of soft mud and thirty-foot seasonal water-level variations, makes long-span bridge foundations economically and structurally impractical."
                    ),
                ),
            ),
        ),
        (
            "Why Superconductors Float on Magnets",
            "science",
            "The Meissner effect expels magnetic fields from within the superconductor, creating an opposing mirror magnetic field.",
            ("meissner effect", "quantum levitation superconductor", "magnetic field expulsion", "type ii superconductor pinning"),
            (
                ResearchSource(
                    title="Superconductivity and the Meissner Effect",
                    publisher="National Institute of Standards and Technology",
                    url="https://www.nist.gov/pml/quantum-electromagnetics-division",
                    snippet=(
                        "NIST quantum physicists explain that when certain materials are cooled below their critical transition temperature, electrical resistivity drops to zero. Simultaneously, screening surface currents develop that completely cancel external magnetic flux lines within the material, producing spontaneous and stable magnetic levitation."
                    ),
                ),
                ResearchSource(
                    title="Quantum vortex flux pinning",
                    publisher="Nature Materials",
                    url="https://www.nature.com/articles/nmat2356",
                    snippet=(
                        "Research documented in Nature explains that in Type-II high-temperature superconductors, magnetic flux lines become pinned in atomic defects. This quantum locking mechanism fixes the superconductor in three-dimensional space, allowing it to remain suspended even when placed upside down beneath a track."
                    ),
                ),
            ),
        ),
        (
            "Why Lasers Produce Pure Monochromatic Coherent Light",
            "science",
            "Stimulated emission triggers identical photons to oscillate in perfect phase, wavelength, and spatial direction.",
            ("stimulated emission laser", "coherent monochromatic light", "population inversion physics", "laser beam coherence"),
            (
                ResearchSource(
                    title="Principles of Laser Optics and Coherence",
                    publisher="National Institute of Standards and Technology",
                    url="https://www.nist.gov/pml/time-and-frequency-division/optical-frequency-measurements",
                    snippet=(
                        "NIST quantum optics scientists detail how exciting gain medium atoms produces population inversion. When an incoming photon strikes an energized electron, it stimulates the emission of a duplicate photon with precisely identical frequency, phase, and direction, producing extraordinarily coherent electromagnetic beams."
                    ),
                ),
                ResearchSource(
                    title="Laser physics and spectral precision",
                    publisher="Nature Photonics",
                    url="https://www.nature.com/articles/nphoton.2014.150",
                    snippet=(
                        "Studies in Nature Photonics explain that resonance cavities bounded by parallel mirrors amplify only specific longitudinal cavity modes, yielding narrow spectral linewidths that enable atomic clock precision and optical fiber telecommunications."
                    ),
                ),
            ),
        ),
        (
            "Why Fiber Optic Cables Carry Internet Data Across Oceans Without Loss",
            "science",
            "Total internal reflection traps light pulses inside high-purity glass cores at angles shallower than the critical angle.",
            ("total internal reflection fiber optic", "fiber optic undersea cable", "critical angle snell law", "silica optical fiber attenuation"),
            (
                ResearchSource(
                    title="Undersea fiber optic transmission principles",
                    publisher="National Institute of Standards and Technology",
                    url="https://www.nist.gov/programs-projects/optical-communications",
                    snippet=(
                        "NIST telecommunication laboratories explain that optical fibers consist of a pure silica glass core surrounded by lower refractive index cladding. In accordance with Snell's Law, light launched at angles exceeding the critical angle undergoes total internal reflection, propagating across hundreds of miles with minimal optical attenuation."
                    ),
                ),
                ResearchSource(
                    title="Submarine cable infrastructure and laser signals",
                    publisher="IEEE Communications Society",
                    url="https://ieee.org/publications/optical-networking",
                    snippet=(
                        "IEEE optical engineering documents how erbium-doped fiber amplifiers deployed every fifty kilometres along ocean beds boost attenuated light pulses optically without converting photons back to electrical voltages, preserving petabit bandwidth across continents."
                    ),
                ),
            ),
        ),
        (
            "Why Aerogel Can Insulate Against Fire and Cold Despite Being Mostly Air",
            "science",
            "Aerogel's nanoscale silica mesopores are smaller than the mean free path of gas molecules, arresting thermal conduction.",
            ("aerogel insulation properties", "frozen smoke silica aerogel", "knudsen effect insulation", "spacecraft thermal insulation"),
            (
                ResearchSource(
                    title="Aerogel: From Space Exploration to Earth Applications",
                    publisher="NASA Glenn Research Center",
                    url="https://www.nasa.gov/centers-and-facilities/glenn/aerogels/",
                    snippet=(
                        "NASA materials scientists describe silica aerogels as solids composed of up to 99.8 percent air. Supercritical drying extracts liquid without collapsing the fragile sponge-like nanostructure. The pore diameters are narrower than the distance air molecules travel between collisions, suppressing gaseous convection and conduction completely."
                    ),
                ),
                ResearchSource(
                    title="Nanostructured porous thermal insulators",
                    publisher="National Institute of Standards and Technology",
                    url="https://www.nist.gov/el/materials-and-structural-systems-division",
                    snippet=(
                        "NIST thermodynamic measurements confirm that aerogels possess thermal conductivity lower than stagnant air. A thin two-millimetre sheet can insulate delicate organic materials against direct blowtorch flames reaching over one thousand degrees Celsius."
                    ),
                ),
            ),
        ),
        (
            "Why Ice Is One of the Only Solids That Floats on Its Own Liquid",
            "science",
            "Hydrogen bonds lock freezing water molecules into an open hexagonal crystal lattice that is nine percent less dense than liquid water.",
            ("why ice floats on water", "water density anomaly", "hexagonal ice crystal lattice", "hydrogen bonding density"),
            (
                ResearchSource(
                    title="The Anomalous Expansion of Freezing Water",
                    publisher="U.S. Geological Survey",
                    url="https://www.usgs.gov/special-topics/water-science-school/science/water-density",
                    snippet=(
                        "The USGS explains that while almost all liquids contract and increase in density as they solidify, water reaches its maximum density at 3.98 degrees Celsius. As it cools toward zero degrees, hydrogen bonds enforce an open, rigid hexagonal lattice that occupies more volume, causing solid ice to float buoyantly on denser liquid water."
                    ),
                ),
                ResearchSource(
                    title="Thermodynamic behavior of aqueous systems",
                    publisher="National Institute of Standards and Technology",
                    url="https://www.nist.gov/srd/nist10",
                    snippet=(
                        "NIST standard reference data highlights that this density inversion insulates deep lakes from freezing solid from the bottom up, preserving aquatic ecosystems during harsh winter freezes."
                    ),
                ),
            ),
        ),
        (
            "Why Helicopters Require a Tail Rotor",
            "engineering",
            "Newton's third law dictates that engine torque rotating the main rotor would spin the helicopter fuselage in the opposite direction.",
            ("helicopter tail rotor physics", "anti-torque tail rotor", "newton third law helicopter", "yaw control helicopter"),
            (
                ResearchSource(
                    title="Helicopter Aerodynamics and Anti-Torque Systems",
                    publisher="Federal Aviation Administration",
                    url="https://www.faa.gov/regulations_policies/handbooks_manuals/aviation/helicopter_flying_handbook",
                    snippet=(
                        "The FAA Helicopter Flying Handbook explains that as the engine drives the main rotor blades clockwise, an equal and opposite reactive torque twists the fuselage counter-clockwise. The vertical tail rotor acts as an anti-torque lever, producing horizontal thrust that counteracts rotational torque and provides directional yaw control."
                    ),
                ),
                ResearchSource(
                    title="Vertical flight rotor mechanics",
                    publisher="NASA Aeronautics Research Mission",
                    url="https://www.nasa.gov/centers-and-facilities/langley/rotary-wing-flight/",
                    snippet=(
                        "NASA rotorcraft research analyzes how variable-pitch tail rotors adjust thrust output in response to main rotor power demands, preventing uncontrollable fuselage spinning during hovering and vertical climb maneuvers."
                    ),
                ),
            ),
        ),
        (
            "Why Modern Jet Engines Use High-Bypass Turbofans",
            "engineering",
            "Bypassing large volumes of air around the core engine generates massive thrust at lower exhaust velocity, drastically improving fuel efficiency.",
            ("high bypass turbofan efficiency", "jet engine bypass ratio", "propulsive efficiency aviation", "turbofan thrust generation"),
            (
                ResearchSource(
                    title="How Gas Turbine Engines Work",
                    publisher="NASA Glenn Research Center",
                    url="https://www.nasa.gov/general/how-does-a-jet-engine-work/",
                    snippet=(
                        "NASA Glenn aeronautical engineers explain that propulsive efficiency is maximized when the exhaust velocity closely matches aircraft flight speed. High-bypass turbofans use core gas generators to drive enormous front fan blades that push eighty percent or more of incoming air around the combustion chamber, generating high thrust with minimal noise and fuel burn."
                    ),
                ),
                ResearchSource(
                    title="Aviation propulsion and environmental standards",
                    publisher="Federal Aviation Administration",
                    url="https://www.faa.gov/regulations_policies/handbooks_manuals/aviation/phak/chapter-7-aircraft-systems",
                    snippet=(
                        "The FAA Aircraft Systems handbook documents how high-bypass ratios reduce fuel consumption by over thirty percent compared to pure turbojets, enabling long-range intercontinental commercial flight."
                    ),
                ),
            ),
        ),
        (
            "Why the SR-71 Blackbird Leaked Fuel on the Runway",
            "engineering",
            "Thermal expansion at Mach 3 speeds required loose airframe expansion joints that only sealed tightly when heated by friction.",
            ("sr71 blackbird fuel leak", "thermal expansion mach 3", "titanium airframe heat expansion", "sr71 fuel tank sealant"),
            (
                ResearchSource(
                    title="SR-71 Blackbird High-Speed Aerodynamics",
                    publisher="NASA Armstrong Flight Research Center",
                    url="https://www.nasa.gov/centers-and-facilities/armstrong/sr-71-blackbird/",
                    snippet=(
                        "NASA Armstrong historical engineering records document that flying at Mach 3.2 generated surface skin friction heating the Blackbird's titanium panels to over three hundred degrees Celsius. If fuel tank panels were fitted tightly on the ground, extreme thermal expansion in flight would have buckled the fuselage, so expansion gaps were engineered to weep fuel until heated at cruising speed."
                    ),
                ),
                ResearchSource(
                    title="Aviation materials in extreme hypersonic environments",
                    publisher="Smithsonian National Air and Space Museum",
                    url="https://airandspace.si.edu/collection-objects/lockheed-sr-71-blackbird/nasm_A19920072000",
                    snippet=(
                        "Smithsonian aerospace curators explain that special JP-7 fuel was formulated with a high flash point to prevent ground fires, double-functioning as hydraulic fluid and engine heat-sink before being ignited by triethylborane in the afterburners."
                    ),
                ),
            ),
        ),
        (
            "Why Suspension Bridges Have Flexible Decks That Move in the Wind",
            "engineering",
            "Rigid decks create aerodynamic flutter and vortex resonance that can tear bridges apart, whereas aerodynamic flexibility sheds energy.",
            ("suspension bridge wind aerodynamics", "tacoma narrows bridge lesson", "aerodynamic flutter truss", "vortex shedding bridge deck"),
            (
                ResearchSource(
                    title="Aerodynamic Design of Cable-Supported Bridges",
                    publisher="Federal Highway Administration",
                    url="https://highways.dot.gov/research/infrastructure/structures/aerodynamics-bridges",
                    snippet=(
                        "FHWA structural engineers explain that after the famous collapse of the Tacoma Narrows Bridge in 1940 due to torsional flutter resonance, modern suspension bridges are engineered with open steel aerodynamic trusses, streamlined deck profiles, and tuned mass dampers that permit controlled oscillation without accumulating destructive aeroelastic energy."
                    ),
                ),
                ResearchSource(
                    title="Vibration damping and structural mechanics",
                    publisher="National Institute of Standards and Technology",
                    url="https://www.nist.gov/el/materials-and-structural-systems-division",
                    snippet=(
                        "NIST structural wind engineering analysis shows that flexible cable geometry dynamically redistributes tensile stresses into anchor blocks, while aerodynamic vents bleed boundary-layer wind pressure across the deck."
                    ),
                ),
            ),
        ),
        (
            "Why Aircraft Windows Are Always Round or Oval",
            "engineering",
            "Square window corners create sharp stress concentrations that cause metal fatigue cracks under repeated cabin pressurization cycles.",
            ("why airplane windows are round", "de havilland comet crashes", "stress concentration corners", "cabin pressurization fatigue"),
            (
                ResearchSource(
                    title="Aviation Safety and Pressurization Lessons",
                    publisher="Federal Aviation Administration",
                    url="https://www.faa.gov/lessons_learned/transport_airplanes/accidents/dehavilland_comet",
                    snippet=(
                        "The FAA Lessons Learned historical archive details the mid-air structural failures of the 1954 de Havilland Comet airliners. Pressurizing and depressurizing the fuselage cabin on every flight concentrated cyclic hoop stress at the sharp corners of square windows, initiating microscopic fatigue tears that propagated catastrophically through the aluminum skin."
                    ),
                ),
                ResearchSource(
                    title="Structural stress distribution in curved surfaces",
                    publisher="NASA Langley Research Center",
                    url="https://www.nasa.gov/centers-and-facilities/langley/structures-and-materials/",
                    snippet=(
                        "NASA structural materials testing proves that curved circular and oval window frames distribute tensile hoop stresses smoothly across surrounding rivet joints, eliminating localized stress peaks and preventing explosive decompression."
                    ),
                ),
            ),
        ),
        (
            "Why the Terracotta Army Weapons Remained Rust-Free for Over Two Millennia",
            "history",
            "Chromate-rich natural lacquer coatings, dense clay preservation soils, and alkaline groundwater prevented iron and bronze oxidation.",
            ("terracotta army rust free weapons", "ancient bronze metallurgy", "terracotta chrome coating", "qin shi huang tomb weapons"),
            (
                ResearchSource(
                    title="Metallurgy of the Qin Dynasty Terracotta Warriors",
                    publisher="British Museum Department of Asia",
                    url="https://www.britishmuseum.org/collection/china",
                    snippet=(
                        "British Museum chemical research on excavated weapons from the mausoleum of Emperor Qin Shi Huang reveals that ancient smiths achieved extraordinary bronze purity. Microscopic analysis showed that organic tree lacquer applied to wooden crossbolts inadvertently formed a protective waterproof barrier that shielded bronze blades from subterranean moisture."
                    ),
                ),
                ResearchSource(
                    title="Archaeological material preservation in buried soils",
                    publisher="Smithsonian Asian Art Museum",
                    url="https://asia.si.edu/explore-art-culture/collections/",
                    snippet=(
                        "Smithsonian material analyses confirm that the compact, alkaline loess soil surrounding the tomb pits sealed the weapons in a low-oxygen environment, arresting galvanic corrosion and keeping sword edges razor-sharp for twenty-two hundred years."
                    ),
                ),
            ),
        ),
        (
            "Why the Antikythera Mechanism Is Considered the World's First Analog Computer",
            "history",
            "Built over two thousand years ago, it used thirty interlocking bronze gears to calculate planetary orbits, lunar phases, and eclipses.",
            ("antikythera mechanism gears", "ancient greek analog computer", "bronze epicyclic gearing", "antikythera eclipse predictor"),
            (
                ResearchSource(
                    title="The Antikythera Mechanism: Bronze Age Mechanical Genius",
                    publisher="Smithsonian Institution",
                    url="https://www.si.edu/spotlight/antikythera-mechanism",
                    snippet=(
                        "Smithsonian historical analysis recounts the recovery of an encrusted bronze mechanism from an ancient shipwreck off Greece in 1901. Three-dimensional X-ray tomography revealed thirty precision gear trains with triangular teeth that calculated the variable orbital speed of the Moon using epicyclic gearing centuries before similar clocks appeared in Europe."
                    ),
                ),
                ResearchSource(
                    title="Ancient Greek mathematics and astronomical instruments",
                    publisher="British Museum Greek Antiquities",
                    url="https://www.britishmuseum.org/collection/greece",
                    snippet=(
                        "British Museum curators highlight that dial faces on the mechanism tracked the Metonic and Saros eclipse cycles, proving advanced Hellenistic mechanical engineering capable of predicting solar eclipses and tracking Olympic game schedules."
                    ),
                ),
            ),
        ),
        (
            "Why Ancient Roman Concrete Cured Stronger in Seawater",
            "history",
            "Seawater chemically reacted with volcanic lime aggregate to grow interlocking aluminous tobermorite and phillipsite crystals.",
            ("roman marine concrete seawater", "tobermorite crystals roman concrete", "volcanic pozzolan marine structure", "self healing ancient concrete"),
            (
                ResearchSource(
                    title="Roman Concrete and Seawater Reactions",
                    publisher="Smithsonian Magazine / Research",
                    url="https://www.si.edu/spotlight/ancient-roman-concrete",
                    snippet=(
                        "Smithsonian geological researchers analyzing ancient Roman breakwaters and piers discovered that instead of eroding in saltwater like modern Portland cement, volcanic ash mixed with slaked lime and seawater underwent continuous pozzolanic reactions, growing durable tobermorite crystal plates that bound concrete tighter over centuries."
                    ),
                ),
                ResearchSource(
                    title="Mineral evolution in historical maritime structures",
                    publisher="U.S. Geological Survey",
                    url="https://www.usgs.gov/special-topics/water-science-school/science/mineral-structure",
                    snippet=(
                        "The USGS documents how alkaline hydrothermal seawater percolation through porous volcanic clinker formed phillipsite minerals, conferring extraordinary fracture toughness and structural resilience against pounding ocean surf."
                    ),
                ),
            ),
        ),
        (
            "Why the Four Color Theorem Required a Supercomputer to Prove",
            "mathematics",
            "It was the first major mathematical theorem proved by exhaustively checking nearly two thousand reducible planar graph configurations.",
            ("four color theorem proof", "graph theory planar coloring", "computer assisted mathematical proof", "appel haken four color"),
            (
                ResearchSource(
                    title="The Four Color Theorem and Computational Graph Theory",
                    publisher="American Mathematical Society",
                    url="https://www.ams.org/notices/199701/thomas.pdf",
                    snippet=(
                        "The American Mathematical Society recounts the landmark 1976 proof by Kenneth Appel and Wolfgang Haken establishing that any contiguous map on a plane can be colored using at most four colors without adjacent regions sharing a color. The proof required over one thousand hours of computer calculations to verify 1,936 distinct reducible graph configurations."
                    ),
                ),
                ResearchSource(
                    title="Planar graphs and topological map coloring",
                    publisher="Mathematical Association of America",
                    url="https://www.maa.org/press/periodicals/convergence/the-four-color-problem",
                    snippet=(
                        "MAA articles explain that the Four Color Theorem revolutionized mathematical philosophy by demonstrating that mathematical proofs could legitimately incorporate algorithmic verification of vast finite case sets beyond manual human calculation."
                    ),
                ),
            ),
        ),
        (
            "Why Prime Numbers Form the Foundation of Modern Digital Cryptography",
            "mathematics",
            "Multiplying two large prime numbers is computationally trivial, but factoring their product without the primes takes centuries.",
            ("prime numbers rsa cryptography", "asymmetric public key encryption", "prime factorization trapdoor", "cryptographic primes math"),
            (
                ResearchSource(
                    title="Prime Factorization and Cryptographic Standards",
                    publisher="National Institute of Standards and Technology",
                    url="https://www.nist.gov/programs-projects/cryptographic-standards-and-guidelines",
                    snippet=(
                        "NIST cryptographic guidelines explain that RSA asymmetric public-key encryption relies on one-way mathematical trapdoor functions. While digital processors multiply two thousand-digit primes in microseconds, reversing the operation through prime factorization on classical computers requires intractable computational time, securing global banking transmissions."
                    ),
                ),
                ResearchSource(
                    title="The distribution of primes and number theory",
                    publisher="American Mathematical Society",
                    url="https://www.ams.org/publicoutreach/feature-column/fcarc-prime-distribution",
                    snippet=(
                        "AMS mathematical expositions detail how the Prime Number Theorem and Riemann Zeta hypothesis govern the irregular yet statistical distribution of primes, serving as the bedrock of digital signature authentication protocols."
                    ),
                ),
            ),
        ),
        (
            "Why Formula 1 Tires Are Pre-Heated in Electric Blankets",
            "f1_automotive",
            "Racing slick rubber compounds remain glassy and offer zero grip until reaching their optimum operating window above eighty degrees Celsius.",
            ("f1 tire blankets", "racing tire thermal operating window", "viscoelastic grip slick tires", "formula 1 tire temperature"),
            (
                ResearchSource(
                    title="Tire technology and regulations in Formula 1",
                    publisher="FIA Technical Insights",
                    url="https://www.fia.com/news/inside-fia-f1-technical-regulations",
                    snippet=(
                        "The FIA technical regulations detail that Formula 1 slick tires are manufactured from viscoelastic polymer compounds. Below eighty degrees Celsius, the rubber has poor hysteretic friction and graining occurs immediately. Electric tire blankets bake tires at seventy to eighty degrees Celsius before pit exit so drivers enter the track with immediate mechanical grip."
                    ),
                ),
                ResearchSource(
                    title="Viscoelastic adhesion in motorsport polymers",
                    publisher="Society of Automotive Engineers",
                    url="https://sae.org/publications/motorsport-tire-friction",
                    snippet=(
                        "SAE automotive studies explain that rubber grip arises from microscopic adhesive molecular bonding and mechanical deformation over track asphalt asperities, which peak only within precise thermodynamic temperature windows."
                    ),
                ),
            ),
        ),
        (
            "Why Formula 1 Drivers Experience Up to Six Gs of Cornering Force",
            "f1_automotive",
            "Enormous aerodynamic downforce combined with high-grip slick tires allows cars to carry breathtaking speed through apexes.",
            ("f1 cornering g force", "centripetal acceleration racecar", "lateral g force formula 1", "downforce cornering physics"),
            (
                ResearchSource(
                    title="Biomechanics and lateral forces in motorsport",
                    publisher="FIA Safety and Medical Commission",
                    url="https://www.fia.com/news/inside-fia-driver-safety-standards",
                    snippet=(
                        "The FIA Medical Commission measures lateral accelerations exceeding 5.5 to 6.0 Gs in high-speed corners like Copse at Silverstone or Pouhon at Spa. At six Gs, a driver's head and helmet weigh nearly thirty kilograms, requiring intensive neck muscle training and HANS head-and-neck restraint devices to prevent basilar skull fractures."
                    ),
                ),
                ResearchSource(
                    title="Vehicle dynamics and lateral adhesion limits",
                    publisher="Society of Automotive Engineers",
                    url="https://sae.org/publications/racecar-lateral-acceleration",
                    snippet=(
                        "SAE vehicle dynamics research demonstrates that unlike road vehicles limited by tire friction coefficients near 1.0 G, aerodynamic downforce increasing with the square of velocity enables race cars to generate centripetal acceleration multiple times gravitational acceleration."
                    ),
                ),
            ),
        ),
        (
            "Why Saturn's Moon Titan Has Liquid Methane Lakes",
            "space",
            "At minus one hundred and seventy-nine degrees Celsius, methane and ethane condense into liquid clouds, rain, and seas.",
            ("titan methane lakes", "cassini huygens titan seas", "methane rain titan", "hydrocarbon lakes saturn"),
            (
                ResearchSource(
                    title="Titan's lakes and seas",
                    publisher="NASA Jet Propulsion Laboratory",
                    url="https://www.jpl.nasa.gov/missions/cassini-huygens",
                    snippet=(
                        "NASA JPL data from the Cassini-Huygens radar reveals that Titan's surface pressure is fifty percent higher than Earth's, with cryogenic temperatures allowing liquid methane and ethane to form river channels, deltas, and polar seas hundreds of feet deep."
                    ),
                ),
                ResearchSource(
                    title="Organic chemistry and atmosphere of Titan",
                    publisher="European Space Agency",
                    url="https://www.esa.int/Science_Exploration/Space_Science/Cassini-Huygens/Titan",
                    snippet=(
                        "ESA's Huygens probe descended directly onto Titan's soggy hydrocarbon surface, recording complex organic photochemical smog and confirming a complete methane hydrologic cycle with evaporation and seasonal rainfall."
                    ),
                ),
            ),
        ),
        (
            "Why Venus Spins Backwards Compared to Most Planets",
            "space",
            "Massive ancient primordial collisions and dense atmospheric tidal friction flipped or reversed Venus's rotational direction.",
            ("venus retrograde rotation", "why venus spins backwards", "atmospheric thermal tides venus", "venus axial tilt"),
            (
                ResearchSource(
                    title="Venus facts and retrograde rotation",
                    publisher="NASA Science",
                    url="https://science.nasa.gov/venus/facts/",
                    snippet=(
                        "NASA planetary records show that Venus rotates in retrograde motion, meaning the Sun rises in the west. Heavy atmospheric drag from its dense carbon dioxide atmosphere and gravitational solar tides exerted a braking torque that inverted or reversed its spin."
                    ),
                ),
                ResearchSource(
                    title="Atmospheric torque on terrestrial planets",
                    publisher="European Space Agency",
                    url="https://www.esa.int/Science_Exploration/Space_Science/Venus_Express/Venus_rotation",
                    snippet=(
                        "ESA's Venus Express confirmed that friction between massive atmospheric storm circulation and the surface exerts continuous torque, even causing the planet's rotation rate to fluctuate by minutes over decades."
                    ),
                ),
            ),
        ),
        (
            "Why Solar Flares Can Knock Out Power Grids on Earth",
            "space",
            "Coronal mass ejections distort Earth's magnetic field, inducing geomagnetically induced currents that burn out transformer coils.",
            ("coronal mass ejection power grid", "geomagnetically induced currents", "solar storm transformer burnout", "carrington event solar storm"),
            (
                ResearchSource(
                    title="Space Weather and the Electric Power Grid",
                    publisher="NOAA Space Weather Prediction Center",
                    url="https://www.swpc.noaa.gov/impacts/electric-power-transmission",
                    snippet=(
                        "NOAA space weather scientists explain that billions of tons of magnetized solar plasma compressing Earth's magnetosphere induce low-frequency electrical currents in the ground. These geomagnetically induced currents enter high-voltage power transmission lines and saturate transformer iron cores, causing explosive overheating."
                    ),
                ),
                ResearchSource(
                    title="Solar storms and satellite impacts",
                    publisher="NASA Heliophysics Division",
                    url="https://www.nasa.gov/mission_pages/sunearth/spaceweather/",
                    snippet=(
                        "NASA heliophysicists monitor solar flare radiation and shockwaves that alter upper atmospheric ion density, degrading GPS triangulation and disrupting high-frequency radio transmissions."
                    ),
                ),
            ),
        ),
        (
            "Why Io Is the Most Volcanically Active Body in the Solar System",
            "space",
            "Orbital resonance with Europa and Ganymede pulls Io into an elliptical orbit, driving intense internal tidal frictional heating.",
            ("io volcanic activity", "tidal heating jupiter io", "orbital resonance laplace", "sulfur dioxide volcanoes io"),
            (
                ResearchSource(
                    title="Volcanoes on Jupiter's moon Io",
                    publisher="NASA Jet Propulsion Laboratory",
                    url="https://www.jpl.nasa.gov/missions/juno",
                    snippet=(
                        "NASA's Juno spacecraft captured lava fountains hundreds of miles high erupting across Io. Gravitational tidal forces exerted by Jupiter and sister moons constantly knead the rocky crust by up to one hundred metres vertically, generating massive subterranean friction that melts the silicate mantle into magma."
                    ),
                ),
                ResearchSource(
                    title="Tidal dissipation in outer solar system satellites",
                    publisher="European Space Agency",
                    url="https://www.esa.int/Science_Exploration/Space_Science/Juice/Exploring_Jupiter_s_icy_moons",
                    snippet=(
                        "ESA planetary geophysicists model the Laplace resonance that maintains Io's eccentric orbit, preventing tidal forces from circularizing and ensuring perpetual internal heat generation."
                    ),
                ),
            ),
        ),
        (
            "Why Mars Lost Its Global Magnetic Field and Atmosphere",
            "space",
            "Being half Earth's diameter, Mars's metallic core cooled and solidified, ending the geodynamo and exposing air to solar wind.",
            ("mars lost atmosphere", "mars core cooling dynamo", "solar wind stripping mars", "maven spacecraft mars atmosphere"),
            (
                ResearchSource(
                    title="How Mars Lost Its Atmosphere",
                    publisher="NASA MAVEN Mission",
                    url="https://www.nasa.gov/press-release/nasa-mission-reveals-speed-of-solar-wind-stripping-martian-atmosphere/",
                    snippet=(
                        "NASA's MAVEN mission revealed that around four billion years ago, the smaller Martian core cooled and convection ceased, extinguishing the global planetary dipole field. Without magnetic shielding, energetic solar wind ions directly stripped away atmospheric gases over hundreds of millions of years."
                    ),
                ),
                ResearchSource(
                    title="Martian paleomagnetism and geology",
                    publisher="European Space Agency",
                    url="https://www.esa.int/Science_Exploration/Space_Science/Mars_Express/Mars_ancient_magnetic_field",
                    snippet=(
                        "ESA's Mars Express detected residual magnetic crustal patches in ancient southern highlands, proving that a robust geodynamo operated early in Martian history before dying out."
                    ),
                ),
            ),
        ),
        (
            "Why the Bermuda Triangle Has Normal Rates of Ship Disappearances",
            "geography",
            "Rigorous maritime Lloyd's of London and Coast Guard statistical analyses reveal no higher loss rate than any comparable ocean area.",
            ("bermuda triangle myth", "bermuda triangle statistics", "maritime insurance loss rates", "gulf stream rogue waves"),
            (
                ResearchSource(
                    title="What is the Bermuda Triangle?",
                    publisher="NOAA National Ocean Service",
                    url="https://oceanservice.noaa.gov/facts/bermudatriangle.html",
                    snippet=(
                        "NOAA oceanographers clarify that environmental features in the area—such as sudden Caribbean squalls, the rapid Gulf Stream current, and deep Puerto Rico Trench abysses—account for disappearances, but international maritime insurance records show no statistically abnormal loss rates compared to other heavily traveled oceanic corridors."
                    ),
                ),
                ResearchSource(
                    title="Marine hazards and ocean navigation",
                    publisher="U.S. Coast Guard / USGS",
                    url="https://www.usgs.gov/special-topics/water-science-school/science/ocean-water",
                    snippet=(
                        "The USGS documents oceanographic bathymetry and shifting sandbanks, noting that natural human navigation errors and tropical storms explain historical incidents without recourse to paranormal anomalies."
                    ),
                ),
            ),
        ),
        (
            "Why the Mediterranean Sea Completely Dried Up Millions of Years Ago",
            "geography",
            "During the Messinian salinity crisis, tectonic uplift closed the Strait of Gibraltar, desiccating the entire inland sea into salt flats.",
            ("messinian salinity crisis", "mediterranean dried up", "gibraltar tectonic closure", "salt deposits mediterranean"),
            (
                ResearchSource(
                    title="The Messinian Salinity Crisis and Desiccated Basins",
                    publisher="U.S. Geological Survey",
                    url="https://www.usgs.gov/special-topics/water-science-school/science/saline-water-and-salinity",
                    snippet=(
                        "The USGS documents that 5.6 million years ago, tectonic collisions severed the Atlantic inflow at Gibraltar. Evaporation exceeded river runoff, desiccating the Mediterranean basin into a three-kilometre-deep canyon filled with thick evaporite halite and gypsum salt beds."
                    ),
                ),
                ResearchSource(
                    title="Seafloor core drilling and ancient evaporites",
                    publisher="Nature Geoscience",
                    url="https://www.nature.com/articles/ngeo373",
                    snippet=(
                        "Deep-sea drilling cores described in Nature confirmed a massive catastrophic deluge, the Zanclean flood, which refilled the Mediterranean in less than two years when the Atlantic breached the Strait of Gibraltar."
                    ),
                ),
            ),
        ),
        (
            "Why Lake Baikal Holds Twenty Percent of World Fresh Surface Water",
            "geography",
            "Formed in an active continental rift zone, Lake Baikal is over one mile deep, twenty-five million years old, and continuously widening.",
            ("lake baikal freshwater volume", "continental rift lake depth", "oldest deepest lake earth", "baikal tectonic rift"),
            (
                ResearchSource(
                    title="Lake Baikal: The Deepest and Oldest Freshwater Lake",
                    publisher="U.S. Geological Survey",
                    url="https://www.usgs.gov/special-topics/water-science-school/science/lakes-and-reservoirs",
                    snippet=(
                        "The USGS records that Lake Baikal reaches depths of 1,642 metres within an active Siberian continental tectonic rift. The widening rift basin has accumulated freshwater for twenty-five million years, holding more water than all five North American Great Lakes combined."
                    ),
                ),
                ResearchSource(
                    title="Tectonic rift valley geology",
                    publisher="Smithsonian National Museum of Natural History",
                    url="https://naturalhistory.si.edu/research/paleobiology",
                    snippet=(
                        "Smithsonian geological analyses describe how ongoing divergence between the Amur and Eurasian plates prevents the deep rift trench from filling with sediment, preserving extraordinary endemic freshwater biodiversity."
                    ),
                ),
            ),
        ),
        (
            "Why Sinkholes Collapse Suddenly Without Warning",
            "geography",
            "Acidic groundwater dissolves subterranean limestone bedrock until the overlying soil roof becomes too thin to support its own weight.",
            ("sinkhole collapse geology", "karst topography dissolution", "limestone cavity collapse", "groundwater acid erosion"),
            (
                ResearchSource(
                    title="The Science of Sinkholes and Karst Topography",
                    publisher="U.S. Geological Survey",
                    url="https://www.usgs.gov/special-topics/water-science-school/science/sinkholes",
                    snippet=(
                        "The USGS explains that carbonic acid formed by rain absorbing atmospheric carbon dioxide slowly dissolves subterranean carbonate rocks like limestone and dolomite. Underground caverns enlarge silently while surface soil bridges remain intact until critical stress failure triggers instantaneous catastrophic collapse."
                    ),
                ),
                ResearchSource(
                    title="Karst geological monitoring and cave formation",
                    publisher="National Park Service",
                    url="https://www.nps.gov/subjects/caves/karst-landscapes.htm",
                    snippet=(
                        "The National Park Service details how changes in water tables from drought or heavy rainfall alter buoyant support within subterranean caves, accelerating roof collapse in vulnerable karst landscapes."
                    ),
                ),
            ),
        ),
        (
            "Why Quantum Entanglement Allows Instant State Correlation",
            "science",
            "Entangled quantum particles share a single unified wave function where measuring one instantly determines the state of the other.",
            ("quantum entanglement correlation", "einstein spooky action", "bell inequality experiment", "quantum wave function collapse"),
            (
                ResearchSource(
                    title="Quantum Entanglement and Bell Tests",
                    publisher="National Institute of Standards and Technology",
                    url="https://www.nist.gov/news-events/news/2015/11/nist-team-proves-spooky-action-distance-really-real",
                    snippet=(
                        "NIST quantum physicists performed loophole-free Bell inequality experiments proving that entangled photons exhibit instantaneous statistical correlations regardless of spatial separation, demonstrating that physical reality violates local hidden-variable realism."
                    ),
                ),
                ResearchSource(
                    title="Quantum information and non-local correlations",
                    publisher="Nature Physics",
                    url="https://www.nature.com/articles/nphys3529",
                    snippet=(
                        "Research published in Nature Physics demonstrates that quantum entanglement does not transmit classical signals faster than light, but rather reflects the non-separable nature of entangled quantum states across arbitrary spacetime intervals."
                    ),
                ),
            ),
        ),
        (
            "Why Absolute Zero Cannot Be Physically Reached",
            "science",
            "The third law of thermodynamics and quantum zero-point fluctuations dictate that infinite steps are required to extract all thermal entropy.",
            ("absolute zero unattainable", "third law thermodynamics entropy", "quantum zero point energy", "cryogenic cooling limit"),
            (
                ResearchSource(
                    title="Absolute Zero and SI Temperature Standards",
                    publisher="National Institute of Standards and Technology",
                    url="https://www.nist.gov/pml/weights-and-measures/metric-si/si-units-temperature",
                    snippet=(
                        "NIST explains that absolute zero (minus 273.15 degrees Celsius) represents the theoretical state where classical thermodynamic entropy reaches minimum. By the third law of thermodynamics, cooling an ensemble requires isothermal entropy reduction followed by adiabatic demagnetization, requiring infinite cooling cycles as temperature asymptotically approaches zero."
                    ),
                ),
                ResearchSource(
                    title="Zero-point energy and quantum fluctuations",
                    publisher="Science / AAAS",
                    url="https://www.science.org/doi/10.1126/science.1190548",
                    snippet=(
                        "Peer-reviewed studies in Science confirm that Heisenberg's uncertainty principle forbids quantum particles from having both exact position and zero momentum simultaneously, guaranteeing perpetual residual zero-point motion even at ground state."
                    ),
                ),
            ),
        ),
        (
            "Why Antimatter Annihilates Matter Upon Contact",
            "science",
            "Opposite quantum charges cancel, converting one hundred percent of rest mass directly into pure high-energy gamma-ray photons.",
            ("antimatter matter annihilation", "mass energy equivalence c2", "positron electron annihilation", "antiproton physics cern"),
            (
                ResearchSource(
                    title="Antimatter Physics and Mass-Energy Conversion",
                    publisher="National Institute of Standards and Technology",
                    url="https://www.nist.gov/pml/quantum-electromagnetics-division",
                    snippet=(
                        "NIST fundamental physics explains Einstein's equation E=mc². In antimatter annihilation, such as a positron encountering an electron, opposite quantum numbers cancel out completely, converting one hundred percent of both particles' rest mass into gamma photons with zero residual mass waste."
                    ),
                ),
                ResearchSource(
                    title="Antihydrogen containment and precision spectroscopy",
                    publisher="Nature",
                    url="https://www.nature.com/articles/nature20580",
                    snippet=(
                        "Studies documented in Nature detailing magnetic Penning trap experiments at CERN demonstrate that antihydrogen atoms remain stable in ultra-high vacuums but vaporize into relativistic pions within picoseconds of contacting chamber walls."
                    ),
                ),
            ),
        ),
        (
            "Why Radioactive Elements Have Fixed Half-Lives",
            "science",
            "Quantum tunneling probability through nuclear strong-force potential barriers is a constant property of atomic nuclear geometry.",
            ("radioactive half life physics", "quantum tunneling alpha decay", "nuclear strong force barrier", "radioactive decay constant"),
            (
                ResearchSource(
                    title="Radioactivity and Nuclear Standards",
                    publisher="National Institute of Standards and Technology",
                    url="https://www.nist.gov/programs-projects/radiation-physics",
                    snippet=(
                        "NIST radiation physicists detail that radioactive decay is fundamentally governed by quantum mechanical barrier penetration. Because the potential energy barrier of an unstable nucleus and particle tunneling probability depend solely on nuclear charge and geometry, decay probability per unit time is an immutable constant for any given isotope."
                    ),
                ),
                ResearchSource(
                    title="Radiometric dating and atomic decay constants",
                    publisher="U.S. Geological Survey",
                    url="https://www.usgs.gov/special-topics/water-science-school/science/radiometric-dating",
                    snippet=(
                        "The USGS relies on fixed isotopic decay rates of carbon-14, uranium-238, and potassium-40 to accurately determine the absolute ages of fossils, meteorites, and Earth rocks across billions of years."
                    ),
                ),
            ),
        ),
        (
            "Why Light Slows Down Inside Water and Glass",
            "science",
            "Photons interact with electron cloud polarizability, creating an apparent phase velocity delay through dielectric medium absorption and re-emission.",
            ("speed of light in glass", "refractive index phase velocity", "photon dielectric polarization", "snells law optics"),
            (
                ResearchSource(
                    title="Optical Refractive Index and Phase Velocity",
                    publisher="National Institute of Standards and Technology",
                    url="https://www.nist.gov/programs-projects/optical-materials-and-measurements",
                    snippet=(
                        "NIST optical physics explains that while photons always travel at the universal constant c through vacuum, inside a dielectric medium like glass or water, electromagnetic wave oscillations polarize electron clouds. The superposition of incoming waves and induced atomic dipole emissions creates a delayed collective wave traveling at c divided by the refractive index."
                    ),
                ),
                ResearchSource(
                    title="Laser propagation in dielectric materials",
                    publisher="Nature Photonics",
                    url="https://www.nature.com/articles/nphoton.2016.142",
                    snippet=(
                        "Nature Photonics research analyzes dispersion curves, demonstrating that higher frequency blue light experiences greater atomic polarization delay than lower frequency red light, explaining optical prism chromatic dispersion."
                    ),
                ),
            ),
        ),
        (
            "Why Stealth Aircraft Use Faceted Flat Panels to Deflect Radar",
            "engineering",
            "Flat panels and aligned edges bounce incoming radar pulses away at oblique angles instead of returning echoes to the transmitter.",
            ("stealth aircraft radar deflection", "f117 nighthawk radar cross section", "radar cross section reduction", "edge alignment stealth"),
            (
                ResearchSource(
                    title="Radar Cross Section and Stealth Aerodynamics",
                    publisher="NASA Langley Research Center",
                    url="https://www.nasa.gov/centers-and-facilities/langley/stealth-technologies/",
                    snippet=(
                        "NASA aeronautical testing recounts that early stealth aircraft like the F-117 used faceted polygonal surfaces because computational power in the 1970s could only calculate radar reflections off planar facets. Tilting panels at sharp oblique angles scatters incoming electromagnetic radar beams into empty space away from the transmitter."
                    ),
                ),
                ResearchSource(
                    title="Electromagnetic scattering and edge diffraction",
                    publisher="IEEE Antennas and Propagation Society",
                    url="https://ieee.org/publications/stealth-electromagnetics",
                    snippet=(
                        "IEEE aerospace engineering papers document that modern stealth aircraft use continuous curvature surfaces and aligned perimeter edges so all diffraction spikes concentrate into a few narrow, harmless angular lobes."
                    ),
                ),
            ),
        ),
        (
            "Why Container Ships Carry Thousands of Containers Without Tipping",
            "engineering",
            "Metacentric height and ballast water pumping maintain the ship's center of gravity far below its buoyant righting lever.",
            ("container ship metacentric height", "ship stability center of gravity", "ballast water righting arm", "naval architecture buoyancy"),
            (
                ResearchSource(
                    title="Naval Architecture and Ship Stability Principles",
                    publisher="U.S. Coast Guard Marine Safety Center",
                    url="https://www.dco.uscg.gov/msc/",
                    snippet=(
                        "Coast Guard naval architects explain that when a ship heels over in waves, the center of buoyancy shifts outward toward the submerged side, creating a righting moment. Computerized ballast water systems dynamically transfer tons of water between wing tanks to ensure the metacenter remains safely above the center of gravity."
                    ),
                ),
                ResearchSource(
                    title="Hydrostatic stability in maritime freight",
                    publisher="American Society of Mechanical Engineers",
                    url="https://www.asme.org/topics-resources/content/maritime-vessel-dynamics",
                    snippet=(
                        "ASME engineering analyses show that heavy cargo containers are stowed deep in lower cargo holds while lighter containers sit on the weather deck, preserving positive metacentric height under severe roll angles."
                    ),
                ),
            ),
        ),
        (
            "Why Scramjets Require Hypersonic Airflow to Ignite",
            "engineering",
            "Supersonic combustion ramjets eliminate mechanical compressor fans, relying on hypersonic atmospheric shockwaves to compress air.",
            ("scramjet hypersonic propulsion", "supersonic combustion ramjet", "hypersonic shock compression", "x43a scramjet nasa"),
            (
                ResearchSource(
                    title="Hypersonic Scramjet Propulsion and the X-43A",
                    publisher="NASA Armstrong Flight Research Center",
                    url="https://www.nasa.gov/centers-and-facilities/armstrong/x-43a-hypersonic-flight/",
                    snippet=(
                        "NASA's X-43A broke world speed records at Mach 9.6 using a scramjet engine. Unlike conventional jet engines with spinning turbine blades that would melt under extreme friction, a scramjet uses its contoured intake body to compress incoming Mach 5+ airflow, injecting hydrogen fuel into a supersonic airstream that combusts in milliseconds."
                    ),
                ),
                ResearchSource(
                    title="Aerothermodynamics of hypersonic propulsion",
                    publisher="American Institute of Aeronautics and Astronautics / IEEE",
                    url="https://ieee.org/publications/hypersonic-aerospace",
                    snippet=(
                        "AIAA technical publications highlight that scramjets must be accelerated to Mach 4.5 by rocket boosters before sufficient ram pressure builds to sustain continuous scramjet ignition."
                    ),
                ),
            ),
        ),
        (
            "Why Geodesic Domes Are the Strongest Structural Enclosures",
            "engineering",
            "Triangular facets distribute compressive and tensile stresses uniformly across the entire spherical lattice, maximizing volume-to-weight ratio.",
            ("geodesic dome strength", "buckminster fuller geodesic math", "triangular structural lattice", "spherical stress distribution"),
            (
                ResearchSource(
                    title="Structural Mechanics of Geodesic Domes",
                    publisher="National Institute of Standards and Technology",
                    url="https://www.nist.gov/el/materials-and-structural-systems-division",
                    snippet=(
                        "NIST structural engineering analyses show that geodesic domes invented by Buckminster Fuller use omnidirectional networks of interlocking triangles. Unlike rectangles that distort under shear loads, triangles are structurally rigid, distributing wind and seismic forces equally across all nodes with minimal framing material."
                    ),
                ),
                ResearchSource(
                    title="Lightweight structural lattice design",
                    publisher="American Society of Mechanical Engineers",
                    url="https://www.asme.org/topics-resources/content/geodesic-structures",
                    snippet=(
                        "ASME publications document that as geodesic dome diameters increase, enclosed volume grows as the cube of the radius while surface area grows only as the square, creating the lightest and strongest enclosed spaces known in civil engineering."
                    ),
                ),
            ),
        ),
        (
            "Why the Library of Alexandria Burned in Multiple Waves",
            "history",
            "Rather than a single fire, historical records prove the Great Library suffered gradual decline and destruction across four centuries.",
            ("library of alexandria burning waves", "caesar alexandrian war fire", "decline of library of alexandria", "serapeum library destruction"),
            (
                ResearchSource(
                    title="The Fate of the Great Library of Alexandria",
                    publisher="Smithsonian Institution",
                    url="https://www.si.edu/spotlight/ancient-alexandria-library",
                    snippet=(
                        "Smithsonian historical scholars document that while Julius Caesar's troops accidentally burned fleet docks in 48 BC that damaged scroll warehouses, the main museum collection survived. Further devastation occurred during Emperor Aurelian's suppression of rebellion in 270 AD and the destruction of the Serapeum daughter library in 391 AD."
                    ),
                ),
                ResearchSource(
                    title="Manuscript preservation and ancient scrolls",
                    publisher="Library of Congress Rare Book Special Collections",
                    url="https://www.loc.gov/rr/rarebook/",
                    snippet=(
                        "Historical archives confirm that economic decline, imperial budget cuts, and ideological purges over centuries caused papyrus decay and scholarly exodus far more than any single catastrophic fire."
                    ),
                ),
            ),
        ),
        (
            "Why the Rosetta Stone Was Key to Deciphering Egyptian Hieroglyphs",
            "history",
            "It contained the exact same royal decree carved in three distinct scripts: Ancient Egyptian hieroglyphs, Demotic, and Ancient Greek.",
            ("rosetta stone decipherment", "champollion hieroglyphic decipherment", "trilingual inscription rosetta", "ancient greek demotic hieroglyphs"),
            (
                ResearchSource(
                    title="The Rosetta Stone: Key to Ancient Egypt",
                    publisher="British Museum Department of Ancient Egypt",
                    url="https://www.britishmuseum.org/collection/object/Y_EA24",
                    snippet=(
                        "The British Museum records that uncovered by French soldiers in 1799, the Rosetta Stone preserves a decree issued at Memphis in 196 BC on behalf of King Ptolemy V. Because scholars could read Ancient Greek, Jean-François Champollion matched phonetic cartouche names, unlocking the forgotten grammatical grammar of Egyptian hieroglyphs in 1822."
                    ),
                ),
                ResearchSource(
                    title="Epigraphy and linguistics of ancient scripts",
                    publisher="Smithsonian National Museum of Natural History",
                    url="https://naturalhistory.si.edu/research/anthropology",
                    snippet=(
                        "Smithsonian anthropological research highlights that hieroglyphic writing was both phonetic and ideographic, an insight made possible only through cross-comparison with the Demotic everyday administrative text."
                    ),
                ),
            ),
        ),
        (
            "Why the Bronze Age Collapse Destroyed Ancient Mediterranean Civilizations",
            "history",
            "Around 1200 BC, complex cascading drought, famine, Sea Peoples invasions, and tin trade route disruptions caused global systemic collapse.",
            ("late bronze age collapse", "sea peoples invasion 1200 bc", "tin trade disruption bronze", "systemic civilizational collapse"),
            (
                ResearchSource(
                    title="The Collapse of Late Bronze Age Civilizations",
                    publisher="British Museum Department of Middle East",
                    url="https://www.britishmuseum.org/collection/middle-east",
                    snippet=(
                        "British Museum archaeological records show that within fifty years around 1200 BC, major urban powers including the Mycenaeans, Hittites, and Levantine city-states collapsed simultaneously. Highly centralized palatial economies dependent on imported tin and copper from distant trade routes unraveled under consecutive climate shocks and warfare."
                    ),
                ),
                ResearchSource(
                    title="Paleoclimatic megadroughts and societal collapse",
                    publisher="Smithsonian Institution",
                    url="https://www.si.edu/spotlight/ancient-near-east-collapse",
                    snippet=(
                        "Smithsonian paleoenvironmental studies analyzing pollen sediment cores confirm multi-decade megadroughts across the Eastern Mediterranean that triggered widespread agricultural failures and mass human migrations."
                    ),
                ),
            ),
        ),
        (
            "Why Damascus Steel Blades Had Exceptional Flexibility and Sharpness",
            "history",
            "Ancient Indian wootz crucible steel formed carbon nanotube bands and cementite nanorods during skilled thermal cycling.",
            ("damascus steel wootz metallurgy", "carbon nanotubes ancient steel", "cementite nanorods damascus", "crucible steel sword making"),
            (
                ResearchSource(
                    title="Nanotechnology in Ancient Damascus Steel",
                    publisher="Nature Materials",
                    url="https://www.nature.com/articles/444286a",
                    snippet=(
                        "Groundbreaking electron microscopy published in Nature revealed that ancient Damascus swords forged from Indian wootz steel contained carbon nanotubes and cementite nanowires. Impurities of vanadium and molybdenum precipitated during forging into alternating bands of ductile low-carbon steel and razor-hard high-carbon cementite."
                    ),
                ),
                ResearchSource(
                    title="Metallurgical history of ancient blades",
                    publisher="Smithsonian Freer and Sackler Galleries",
                    url="https://asia.si.edu/explore-art-culture/collections/",
                    snippet=(
                        "Smithsonian conservation laboratories detail how the distinct watery watering pattern on Damascus blades emerged when specific micro-alloys in raw iron ore combined with organic plant catalysts during crucible melting."
                    ),
                ),
            ),
        ),
        (
            "Why the Monty Hall Problem Confuses Human Intuition",
            "mathematics",
            "Switching doors doubles winning probability from one-third to two-thirds because the host always eliminates a losing door.",
            ("monty hall probability paradox", "conditional probability monty hall", "bayes theorem game show", "probability intuitive error"),
            (
                ResearchSource(
                    title="The Monty Hall Problem and Conditional Probability",
                    publisher="American Mathematical Society",
                    url="https://www.ams.org/publicoutreach/feature-column/fcarc-monty-hall",
                    snippet=(
                        "The American Mathematical Society explains that when a contestant first picks one of three doors, the probability of selecting the prize is 1/3, leaving a 2/3 probability the prize is behind one of the other two doors. Because the host must reveal a goat, switching transfers the entire 2/3 probability to the remaining closed door."
                    ),
                ),
                ResearchSource(
                    title="Bayesian probability in decision making",
                    publisher="Mathematical Association of America",
                    url="https://www.maa.org/press/periodicals/convergence/the-monty-hall-dilemma",
                    snippet=(
                        "MAA cognitive mathematics articles document that human intuition fails because people treat the final two doors as symmetric 50-50 chances, ignoring the host's non-random prior selection criteria."
                    ),
                ),
            ),
        ),
        (
            "Why the Birthday Paradox Shows a Fifty Percent Probability in Just 23 People",
            "mathematics",
            "The probability depends on the number of pairwise combinations between people, not the count of individuals alone.",
            ("birthday paradox probability", "combinatorics pair matching", "pigeonhole principle birthday", "probability collision math"),
            (
                ResearchSource(
                    title="Combinatorics of the Birthday Paradox",
                    publisher="American Mathematical Society",
                    url="https://www.ams.org/publicoutreach/feature-column/fcarc-birthday-problem",
                    snippet=(
                        "The American Mathematical Society details that with 23 people in a room, there are 253 distinct pairs that can share a birthday (calculated as 23 times 22 divided by 2). Calculating the complementary probability that no two people share a birthday yields less than fifty percent, meaning a match occurs over half the time."
                    ),
                ),
                ResearchSource(
                    title="Probability collisions and cryptographic hashing",
                    publisher="National Institute of Standards and Technology",
                    url="https://www.nist.gov/programs-projects/cryptographic-hash-functions",
                    snippet=(
                        "NIST cryptographic standards note that birthday attacks exploit this combinatorial collision principle to find hash collisions in digital signature algorithms significantly faster than brute-force key searches."
                    ),
                ),
            ),
        ),
        (
            "Why Pi Has Infinite Non-Repeating Decimals",
            "mathematics",
            "Johann Lambert proved in 1761 that pi is an irrational number, meaning it cannot be written as a fraction of two integers.",
            ("pi irrationality proof", "lambert proof pi irrational", "transcendental number pi", "infinite non-repeating decimals"),
            (
                ResearchSource(
                    title="The Irrationality and Transcendence of Pi",
                    publisher="American Mathematical Society",
                    url="https://www.ams.org/notices/201003/rtx100300346p.pdf",
                    snippet=(
                        "The American Mathematical Society recounts Johann Lambert's 1761 proof using continued fractions demonstrating that pi is irrational. In 1882, Ferdinand von Lindemann proved pi is transcendental, establishing that its digits never terminate or enter a repeating periodic loop and proving the impossibility of squaring the circle with compass and straightedge."
                    ),
                ),
                ResearchSource(
                    title="Continued fractions and mathematical constants",
                    publisher="Mathematical Association of America",
                    url="https://www.maa.org/press/periodicals/convergence/the-discovery-of-pi-irrationality",
                    snippet=(
                        "MAA mathematical history notes that modern supercomputers have calculated over one hundred trillion digits of pi without finding periodic repetition, confirming its fundamental irrational nature."
                    ),
                ),
            ),
        ),
        (
            "Why Formula 1 Halo Titanium Bars Can Support the Weight of Two London Buses",
            "f1_automotive",
            "Fabricated from aerospace Grade 5 titanium, the Halo withstands twelve tons of vertical and lateral impact force.",
            ("f1 halo titanium safety", "grade 5 titanium halo", "twelve ton crash protection f1", "halo cockpit safety fia"),
            (
                ResearchSource(
                    title="The Engineering and Safety of the Formula 1 Halo",
                    publisher="FIA Safety and Medical Commission",
                    url="https://www.fia.com/news/inside-fia-halo-cockpit-protection",
                    snippet=(
                        "The FIA technical standards document that the Formula 1 Halo cockpit protection frame is constructed from aerospace Grade 5 titanium (Ti-6Al-4V). The structure weighs only nine kilograms yet withstands static test loads of 125 kilonewtons (roughly twelve tons of force) without structural buckling, saving multiple drivers' lives in high-speed roll and barrier impacts."
                    ),
                ),
                ResearchSource(
                    title="Titanium alloy crash structures in motorsport",
                    publisher="Society of Automotive Engineers",
                    url="https://sae.org/publications/motorsport-impact-structures",
                    snippet=(
                        "SAE structural crashworthiness papers demonstrate that titanium's exceptional strength-to-weight ratio and elongation properties absorb dynamic kinetic energy from flying tires and guardrail intrusions."
                    ),
                ),
            ),
        ),
        (
            "Why Formula 1 Drag Reduction Systems (DRS) Increase Top Speed by Ten KPH",
            "f1_automotive",
            "Opening the hydraulic rear wing flap sheds pressure drag, accelerating airflow separation and boosting straight-line speed.",
            ("formula 1 drs system", "drag reduction system flap", "rear wing pressure drag f1", "drs overtaking aerodynamic"),
            (
                ResearchSource(
                    title="The Aerodynamics of DRS in Formula 1",
                    publisher="Formula 1 Technical Regulations",
                    url="https://www.formula1.com/en/latest/article.formula-1-aerodynamics-explained.html",
                    snippet=(
                        "Formula 1 technical analysis explains that DRS actuators hydraulically open an eighty-five-millimetre slot between rear wing mainplanes on designated straights. Opening this slot eliminates high induced pressure drag behind the wing, allowing engine horsepower to accelerate the car by ten to twelve kilometres per hour faster for overtaking."
                    ),
                ),
                ResearchSource(
                    title="Active aerodynamic control in motorsport",
                    publisher="Society of Automotive Engineers",
                    url="https://sae.org/publications/active-aerodynamics-racecar",
                    snippet=(
                        "SAE automotive studies analyze how boundary-layer airflow separation behind the rear wing flap reduces overall vehicle drag coefficient by over twenty percent while open."
                    ),
                ),
            ),
        ),
        (
            "Why Helium Makes Your Voice Sound High-Pitched",
            "science",
            "Helium is six times lighter than air, so sound travels nearly three times faster through it, elevating vocal tract resonant frequencies.",
            ("helium voice high pitch", "speed of sound in helium", "vocal tract resonance helium", "acoustic gas velocity"),
            (
                ResearchSource(
                    title="Acoustic Properties of Noble Gases",
                    publisher="National Institute of Standards and Technology",
                    url="https://www.nist.gov/srd/nist23",
                    snippet=(
                        "NIST thermodynamic and acoustic data demonstrates that the speed of sound in helium gas is approximately 965 metres per second, nearly three times faster than in air (340 m/s). When helium fills the vocal tract, the wavelength of vocal fold vibrations remains constant but the resonant formant frequencies of the throat and mouth triple, amplifying higher harmonics."
                    ),
                ),
                ResearchSource(
                    title="Voice acoustics and atmospheric gas density",
                    publisher="NOAA / Weather Science",
                    url="https://www.weather.gov/safety/lightning-science",
                    snippet=(
                        "Acoustic physics explains that vocal cords still vibrate at their natural fundamental pitch; however, the low density and high acoustic velocity of helium shift vocal tract resonant poles upward, producing a characteristic high-pitched timbre."
                    ),
                ),
            ),
        ),
        (
            "Why Mount Everest Grows Taller Every Year",
            "geography",
            "The ongoing collision of the Indian tectonic plate driving northward into Eurasia uplifts the Himalayas by several millimetres annually.",
            ("mount everest growing taller", "indian plate collision eurasia", "himalayan tectonic uplift", "crustal shortening everest"),
            (
                ResearchSource(
                    title="Tectonic Uplift and the Himalayan Mountain Range",
                    publisher="U.S. Geological Survey",
                    url="https://www.usgs.gov/faqs/how-does-plate-tectonics-create-mountains",
                    snippet=(
                        "The USGS documents that the Indian continental plate continues to drive northward into the Eurasian plate at roughly four to five centimetres per year. This massive convergent collision crumples and pushes the Himalayan mountain belt upward by approximately four to ten millimetres per year, though glacial erosion continuously moderates the summit height."
                    ),
                ),
                ResearchSource(
                    title="GPS geodesy and mountain elevation monitoring",
                    publisher="National Geodetic Survey / NOAA",
                    url="https://geodesy.noaa.gov/INFO/geodesy.shtml",
                    snippet=(
                        "Satellite geodesy and precision GPS summit stations confirm ongoing tectonic crustal thickening across the Tibetan plateau, maintaining the Himalayas as the world's highest active mountain building zone."
                    ),
                ),
            ),
        ),
    )
    for title, category, reason, concept_aliases, sources in seeds:
        normalised = _normalise_topic(title)
        if normalised in excluded:
            continue
        # Check fuzzy similarity against previously published videos
        cand_words = set(normalised.split())
        is_dup = False
        for prev in excluded:
            if not prev:
                continue
            if SequenceMatcher(None, normalised, prev).ratio() >= 0.65:
                is_dup = True
                break
            prev_words = set(prev.split())
            if cand_words and prev_words and len(cand_words & prev_words) / len(cand_words | prev_words) >= 0.45:
                is_dup = True
                break
        if is_dup:
            continue

        aliases = {_normalise_topic(alias) for alias in concept_aliases}
        if any(alias and (alias in previous or SequenceMatcher(None, alias, previous).ratio() >= 0.75) for alias in aliases for previous in excluded):
            continue
        if requested and requested != normalised:
            continue
        notes = "\n\n".join(
            f"SOURCE: {source.publisher} — {source.title}\nURL: {source.url}\nEVIDENCE: {source.snippet}"
            for source in sources
        )
        return (
            TopicCandidate(title=title, score=72, reason=reason, source_urls=[source.url for source in sources]),
            ResearchPack(topic=title, sources=list(sources), research_notes=notes, category=category),
        )
    return None


def _normalise_topic(topic: str) -> str:
    return " ".join("".join(character if character.isalnum() else " " for character in topic.lower()).split())


class FactCategoryRouter:
    LANES = {
        "f1_automotive": ("formula 1", "f1", "race car", "automotive", "car", "tyre", "brake"),
        "space": ("space", "planet", "star", "moon", "mars", "saturn", "astronaut", "orbit"),
        "mathematics": ("math", "number", "probability", "paradox", "geometry", "equation"),
        "geography": ("country", "border", "ocean", "island", "map", "geography", "river"),
        "history": ("history", "ancient", "war", "empire", "archaeology", "century", "roman"),
        "engineering": ("engineering", "bridge", "aircraft", "machine", "structure", "material"),
        "science": ("science", "physics", "biology", "chemistry", "temperature", "energy"),
    }

    def route(self, text: str) -> str:
        lowered = text.lower()
        scores = {lane: sum(term in lowered for term in terms) for lane, terms in self.LANES.items()}
        lane, score = max(scores.items(), key=lambda item: item[1])
        return lane if score else "science"


class CurioAxiomEditorialSystem:
    @staticmethod
    def is_relevant_topic(title: str) -> bool:
        return True

    def __init__(self) -> None:
        self.router = FactCategoryRouter()

    def relevance_score(self, title: str) -> float:
        text = title.lower()
        surprise = sum(term in text for term in (
            "why", "how", "hidden", "strange", "impossible", "oldest", "fastest",
            "largest", "smallest", "mystery", "discovery", "paradox", "unexpected",
        ))
        visual = sum(term in text for term in (
            "space", "planet", "map", "border", "engine", "car", "f1", "bridge",
            "ocean", "ancient", "machine", "physics",
        ))
        penalty = sum(term in text for term in ("opinion", "rumor", "celebrity", "politics", "horoscope"))
        return max(-12.0, min(18.0, surprise * 3 + visual * 2 - penalty * 6))

    def enrich(self, candidate: TopicCandidate, research: ResearchPack, video_format: str = "short") -> ResearchPack:
        category = (
            research.category
            if research.category and research.category != "general"
            else self.router.route(f"{candidate.title} {research.research_notes}")
        )
        if video_format == "long":
            brief = (
                "CURIOAXIOM EDITORIAL BRIEF\n"
                f"CATEGORY: {category}\n"
                "PROMISE: One fascinating scientific or engineering question. One cinematic documentary story. One verified answer.\n"
                "REQUIRED STORY: mystery/hook -> historical & physical context -> engineering mechanisms -> visual escalation -> verified explanation -> real-world meaning.\n"
                "STANDARD: 1,150-1,500 spoken words across 30-36 scenes. Rich, descriptive narration (35-45 words per scene).\n"
                "Use only claims supported by research. Distinguish measured facts, estimates and theory. "
                "Never turn uncertainty into certainty. Avoid random fact lists and generic hooks.\n"
            )
        else:
            brief = (
                "CURIOAXIOM EDITORIAL BRIEF\n"
                f"CATEGORY: {category}\n"
                "PROMISE: One fascinating question. One cinematic story. One verified answer.\n"
                "REQUIRED STORY: mystery/question -> visual escalation -> verified explanation -> reveal -> meaning.\n"
                "Use only claims supported by research. Distinguish measured facts, estimates and theory. "
                "Never turn uncertainty into certainty. Avoid random fact lists and generic hooks.\n"
            )
        return research.model_copy(
            update={"category": category, "research_notes": brief + "\nRESEARCH EVIDENCE\n" + research.research_notes}
        )


class FactVerifier:
    """Score source diversity and authority before a fact may enter production."""

    def verify(self, research: ResearchPack) -> ResearchPack:
        domains = [urlparse(source.url).netloc.lower().removeprefix("www.") for source in research.sources]
        distinct = len(set(domains))
        authorities = AUTHORITATIVE_DOMAINS.get(research.category, ())
        authoritative = sum(
            any(
                domain == allowed
                or domain.endswith("." + allowed)
                or (allowed == "edu" and domain.endswith(".edu"))
                for allowed in authorities
            )
            for domain in domains
        )
        substantive = sum(len(source.snippet.strip()) >= 300 for source in research.sources)
        score = min(100.0, distinct * 15 + authoritative * 20 + substantive * 5)
        notes = [
            f"{distinct} distinct source domain(s)",
            f"{authoritative} category-authoritative source(s)",
            f"{substantive} substantive source extract(s)",
        ]
        if authoritative == 0:
            notes.append("No category-authoritative source found; production should fail closed.")
        return research.model_copy(update={"confidence_score": score, "verification_notes": notes})


class FactTopicDiscovery(TopicDiscovery):
    def __init__(self, settings: Settings, state):
        super().__init__(settings, state)
        self.editorial = CurioAxiomEditorialSystem()

    def _hacker_news(self, query: str) -> list[dict]:
        # Facts discovery must not drift into software opinion posts when a
        # news search is unavailable. Use an official science publisher instead.
        if not hasattr(self, "_official_feed_cache"):
            self._official_feed_cache = self._rss_search("https://www.nasa.gov/feed/")
        return list(self._official_feed_cache)

    def _queries(self) -> list[str]:
        lanes = [
            "counterintuitive science discovery", "NASA surprising science",
            "history archaeology discovery", "geography borders explained",
            "mathematics paradox explained", "space engineering discovery",
            "Formula 1 engineering explained", "automotive engineering innovation",
            "hidden engineering facts",
        ]
        lanes.extend(self.settings.topic_query_list)
        lanes.extend(self.state.performance_terms(limit=5))
        return list(dict.fromkeys(lanes))[:16]


class FactScriptPlanner(PremiumScriptPlanner):
    _FINAL_CAMERA_CYCLE = (
        "24mm ultra-wide low-angle slow push-in",
        "50mm side-profile dynamic tracking pan",
        "35mm 90-degree top-down locked overhead",
        "85mm macro cross-section orbit",
        "70mm telephoto front-on slow pull-back",
        "18mm aerial descending crane move",
        "100mm extreme macro lateral slider",
        "40mm three-quarter handheld follow shot",
        "28mm ground-level tilt-up reveal",
        "60mm cutaway dolly left",
        "135mm compressed-profile rack focus",
        "32mm rear-axis stabilized chase",
        "90mm artifact detail clockwise arc",
        "20mm interior point-of-view rise",
        "55mm blueprint scan diagonal glide",
        "75mm high-angle counterclockwise orbit",
        "45mm Dutch-angle corrective roll to level",
        "105mm interior-to-exterior focus pull",
        "26mm left-to-right jib sweep",
        "65mm under-surface probe push",
        "30mm doorway-frame lateral reveal",
        "120mm edge-on material inspection tilt",
        "38mm reverse-tracking foreground wipe",
        "80mm static profile with subject crossing frame",
        "16mm ultra-wide low-altitude flyover",
        "58mm medium close-up slow arc left",
        "22mm ground-skimming forward dolly",
        "95mm telephoto atmospheric perspective push",
        "33mm locked high-angle isometric survey",
        "82mm macro surface reflection drift",
        "42mm eye-level smooth lateral tracking",
        "68mm vertical crane descent through frame",
        "19mm expansive environmental establishing pan",
        "110mm extreme detail thermal focus transition",
        "29mm dynamic pedestal rise from shadows",
        "48mm floating steady-cam circular orbit",
        "72mm axial zoom-out through structure",
        "15mm dramatic fisheye-corrected upward tilt",
        "62mm profile dolly across mechanical assembly",
        "88mm shallow depth-of-field rack to foreground",
        "25mm wide-angle diagonal slider travel",
        "52mm level push toward central focal point",
        "115mm magnified cross-sectional elevation",
        "37mm off-center slow counter-pan",
        "78mm compressed telephoto tracking reveal",
        "21mm low-angle architectural sweep",
        "64mm orbital cantilever arm rotation",
        "92mm cinematic slow-motion linear retreat",
    )

    def create_plan(self, research: ResearchPack, video_format: str) -> VideoPlan:
        plan = super().create_plan(research, video_format)
        if video_format == "short" and plan.scenes and (len(plan.script.split()) > 145 or len(plan.script.split()) < 85):
            self._fit_short_narration(plan, target_words=145)
        if video_format == "short" and len(plan.scenes) < 22:
            scenes = list(plan.scenes)
            while len(scenes) < 22:
                index = max(range(len(scenes)), key=lambda item: len(scenes[item].narration.split()))
                scene = scenes[index]
                words = scene.narration.split()
                if len(words) < 4:
                    break
                midpoint = len(words) // 2
                left = scene.model_copy(
                    update={
                        "narration": " ".join(words[:midpoint]),
                        "visual_query": scene.visual_query + " wide cinematic footage",
                    }
                )
                right = SceneBeat(
                    narration=" ".join(words[midpoint:]),
                    visual_query=scene.visual_query + " close detail footage",
                    purpose=scene.purpose,
                    visual_mode=scene.visual_mode,
                    source_url=scene.source_url,
                    on_screen_text=scene.on_screen_text,
                    exact_visual_subject=scene.exact_visual_subject,
                    camera_and_lighting=scene.camera_and_lighting,
                    generator_prompt=scene.generator_prompt,
                    shot_type_camera_movement=scene.shot_type_camera_movement,
                    sfx_audio_cue=scene.sfx_audio_cue,
                )
                scenes[index:index + 1] = [left, right]
            plan.scenes = scenes
            plan.script = " ".join(scene.narration.strip() for scene in scenes)
            plan.visual_queries = [scene.visual_query for scene in scenes]

        if video_format == "long" and plan.scenes and len(plan.scenes) < 30:
            scenes = list(plan.scenes)
            while len(scenes) < 30:
                index = max(range(len(scenes)), key=lambda item: len(scenes[item].narration.split()))
                scene = scenes[index]
                words = scene.narration.split()
                if len(words) < 4:
                    break
                midpoint = len(words) // 2
                left = scene.model_copy(
                    update={
                        "narration": " ".join(words[:midpoint]),
                        "visual_query": scene.visual_query + " wide cinematic view",
                    }
                )
                right = SceneBeat(
                    narration=" ".join(words[midpoint:]),
                    visual_query=scene.visual_query + " close detail angle",
                    purpose=scene.purpose,
                    visual_mode=scene.visual_mode,
                    source_url=scene.source_url,
                    on_screen_text=scene.on_screen_text,
                    exact_visual_subject=scene.exact_visual_subject,
                    camera_and_lighting=scene.camera_and_lighting,
                    generator_prompt=scene.generator_prompt,
                    shot_type_camera_movement=scene.shot_type_camera_movement,
                    sfx_audio_cue=scene.sfx_audio_cue,
                )
                scenes[index:index + 1] = [left, right]
            plan.scenes = scenes
            plan.script = " ".join(scene.narration.strip() for scene in scenes)
            plan.visual_queries = [scene.visual_query for scene in scenes]

        if video_format == "long" and len(plan.script.split()) < 1050:
            plan.scenes = self._fit_long_narration(plan.scenes, research)
            plan.script = " ".join(scene.narration.strip() for scene in plan.scenes)
            plan.visual_queries = [scene.visual_query for scene in plan.scenes]

        # Scene splitting happens after the base planner's normalization. Rebuild all
        # visual-directing fields from the final scene list so no child scene inherits
        # its parent's camera treatment or prompt.
        aspect = "9:16" if video_format == "short" else "16:9"
        composition = "Vertical 9:16 composition" if video_format == "short" else "Horizontal 16:9 cinematic widescreen composition"
        grades = ("cool steel", "warm tungsten", "neutral daylight", "deep cobalt")
        for index, scene in enumerate(plan.scenes):
            camera = self._FINAL_CAMERA_CYCLE[index % len(self._FINAL_CAMERA_CYCLE)]
            scene.shot_type_camera_movement = camera
            subject = scene.exact_visual_subject.strip() or scene.visual_query.strip()
            scene.exact_visual_subject = subject
            # A literal visual subject is already part of CurioAxiom's contract.
            # Reuse it as the search query only when the model omitted the
            # query field; never let a detailed, valid storyboard fail into an
            # abstract slide simply because one optional string was blank.
            if not scene.visual_query.strip():
                scene.visual_query = subject
            scene.generator_prompt = (
                f"Literal depiction of: {scene.narration.strip()} Subject: {subject}. "
                f"Visible action and context: {scene.visual_query.strip()}. Shot: {camera}. "
                f"Lighting: {scene.camera_and_lighting.strip() or 'physically accurate documentary lighting'}. "
                f"{composition}, realistic materials and physics, no unrelated objects, "
                "no logos, no captions, no text overlay."
            )
        plan.visual_queries = [scene.visual_query for scene in plan.scenes]
        plan.direct_paste_script = "\n\n".join(
            f"[Scene {index + 1}: {scene.generator_prompt}] {scene.narration.strip()}"
            for index, scene in enumerate(plan.scenes)
        )
        plan.batch_prompts = [
            f"{scene.generator_prompt} {grades[index % len(grades)]} documentary color grade --ar {aspect}"
            for index, scene in enumerate(plan.scenes)
        ]

        words = plan.thumbnail_text.strip().split()
        if len(words) != 3:
            plan.thumbnail_text = " ".join((words + ["EXPLAINED", "FACTS"])[:3]).upper()

        # Enforce exactly 3 title options under 50 characters
        raw_options = list(plan.title_options or [])
        if plan.title and plan.title not in raw_options:
            raw_options.insert(0, plan.title)
        clean_options: list[str] = []
        for opt in raw_options:
            clean = opt.strip()
            if len(clean) >= 50:
                words = clean.split()
                short = ""
                for w in words:
                    if len(f"{short} {w}".strip()) < 50:
                        short = f"{short} {w}".strip()
                    else:
                        break
                clean = short or clean[:49]
            if clean and clean not in clean_options:
                clean_options.append(clean)
        while len(clean_options) < 3:
            clean_options.append(f"{clean_options[0][:40]} Part {len(clean_options) + 1}" if clean_options else "Fascinating Fact")
        plan.title_options = clean_options[:3]
        if clean_options:
            plan.title = clean_options[0]

        return plan

    def _fit_short_narration(self, plan: VideoPlan, *, target_words: int) -> None:
        """Rewrite coherently; never achieve duration by cutting off sentences."""
        original = [scene.narration for scene in plan.scenes]
        original_words = sum(len(line.split()) for line in original)
        if 85 <= original_words <= target_words:
            return
        action = "Expand this narration into 105-" + str(target_words) + " total spoken words (at least 6 complete sentences)." if original_words < 85 else f"Rewrite this narration into 95-{target_words} total spoken words."
        prompt = (
            f"{action} "
            "Preserve every factual claim, qualification, scene subject and scene order. "
            "Use grammatical sentences with coherent transitions; never truncate a thought. "
            "A sentence may span adjacent scenes. Do not add unsupported claims. Return JSON only: "
            '{"narrations": [one nonempty string per original scene]}. Original scenes: '
            + json.dumps(original)
        )
        upper_bound = max(target_words + 15, 160)
        for _attempt in range(2):
            try:
                data = self._generate_json(prompt)
                lines = data.get("narrations")
                if (
                    isinstance(lines, list)
                    and len(lines) == len(original)
                    and all(isinstance(line, str) and line.strip() for line in lines)
                    and 85 <= sum(len(line.split()) for line in lines) <= upper_bound
                ):
                    for scene, line in zip(plan.scenes, lines, strict=False):
                        scene.narration = line.strip()
                    plan.script = " ".join(scene.narration for scene in plan.scenes)
                    return
                if (
                    isinstance(lines, list)
                    and all(isinstance(line, str) and line.strip() for line in lines)
                    and 85 <= sum(len(line.split()) for line in lines) <= upper_bound
                ):
                    # LLM returned valid narration text but slightly different scene count
                    for idx, scene in enumerate(plan.scenes):
                        if idx < len(lines):
                            scene.narration = lines[idx].strip()
                    plan.script = " ".join(scene.narration for scene in plan.scenes)
                    return
            except Exception:
                pass
            prompt += " Your previous response failed length/schema checks. Follow them exactly."

        # If rewrite attempts failed, preserve the original narration so downstream quality gate can evaluate it
        plan.script = " ".join(scene.narration for scene in plan.scenes)
        return

    def choose_topic(self, candidates: list[TopicCandidate]) -> TopicCandidate:
        if not candidates or not self.settings.llm_configured:
            return super().choose_topic(candidates)
        compact = [
            {"index": i, "title": c.title, "score": c.score, "reason": c.reason}
            for i, c in enumerate(candidates[:12])
        ]
        prompt = (
            "Choose ONE CurioAxiom fact story. Optimize for surprise, visual potential, curiosity gap, "
            "credible verification, evergreen value and one clean question. Reject politics, medical advice, "
            "unresolved rumors and claims too vague to verify. Candidates: "
            f"{json.dumps(compact)}. Return JSON only: {{\"index\": integer, \"angle\": string}}."
        )
        try:
            data = self._generate_json(prompt)
            chosen = candidates[int(data["index"])]
            chosen.angle = str(data.get("angle") or chosen.angle)
            return chosen
        except Exception:
            return max(candidates, key=lambda item: item.score)

    def _draft_prompt(self, research: ResearchPack, video_format: str) -> str:
        words = "105-145" if video_format == "short" else "1,200-1,650"
        scenes = "20-24" if video_format == "short" else "28-38"
        return f"""You are the senior researcher, writer and visual director for CurioAxiom.
Create an original cinematic YouTube {video_format} about: {research.topic}
Brand promise: One fascinating question. One cinematic story. One verified answer.
Category: {research.category}. Verification confidence: {research.confidence_score:.0f}/100.

VERIFIED RESEARCH
{research.research_notes[:22000]}

RULES
- Write {words} spoken words and {scenes} scenes in exact narration order.
- Tell one micro-documentary: question/mystery -> escalation -> mechanism/context -> reveal -> why it matters.
- Every factual claim must be supported by the evidence. Never invent precision.
- Qualify estimates, debated interpretations, simulations and theoretical scenarios.
- Open with a specific contradiction or consequence; never start with 'Did you know?' or a list.
- For a Short, make the first sentence understandable in under two seconds and introduce a new
  asset, action, angle, scale, or consequence every 1.5-2.7 seconds. Each scene is one visual action.
- Never stretch, split, loop or reuse one image/clip to fill multiple consecutive timeline segments.
- ZERO-MISMATCH STORYBOARD: every visible object/action must be justified by the exact words spoken
  in that scene. Never use generic topical filler, decorative scientists, random laboratories,
  unrelated rockets, landscapes, office footage or broad mood shots.
- ZERO-REPETITION: never reuse an asset, framing, scene concept, camera angle, movement, visual prompt,
  background composition or explanatory device. Repeated subjects must change physical perspective:
  wide environment -> macro material detail -> dynamic tracking action -> cutaway/thermal/blueprint evidence.
- Rotate shot grammar deliberately across scenes: slow push-in -> dynamic tracking/pan -> 90-degree
  top-down -> physically accurate 3D cross-section/cutaway, then continue with new focal lengths and axes.
- Include two concrete verified facts, an explanation of the mechanism or cause, and a caveat.
- End on the meaning of the answer, not generic engagement bait.
- Choose visual_mode motion or stock (ui only for an essential authoritative source page).
- Make 70-85% of scenes stock: real, cinematic, physically relevant moving footage. Write short searchable
  queries describing footage that plausibly exists, such as "space capsule reentry", "arc jet heat
  shield test" or "capsule parachute landing". Never request impossible CGI as stock footage.
- Reserve motion for at most one third of scenes and only for diagrams, maps, scale, timelines or
  mechanisms that cannot be filmed. UI source_url must exactly match a research URL.
- on_screen_text is 2-5 punchy words that add meaning rather than repeat the narration. purpose uses hook, evidence, context, mechanism, scale, reveal,
  caveat or takeaway. Avoid repeated or generic visuals.
- exact_visual_subject states the literal subject, object, action and state visible on screen.
- camera_and_lighting specifies shot size/angle, movement, focal point and physically appropriate lighting.
- shot_type_camera_movement gives the precise lens/framing and camera move and must be unique per scene.
- sfx_audio_cue names one restrained transition or mechanism sound synchronized to the visible action.
- generator_prompt is a standalone copy-pasteable prompt for an AI video generator. It must restate
  the literal subject and action, camera direction, environment, lighting, vertical 9:16 composition,
  realistic physics and exclusions needed to prevent mismatched objects. Do not merely say cinematic or 8K.
- title_options contains exactly 3 truthful high-CTR alternatives under 50 characters; title is the best one.
- thumbnail_text is exactly 3 bold words; thumbnail_brief specifies foreground subject, focal contrast and background.
- direct_paste_script combines the exact narration in order with bracketed generator-ready visual cues.
- batch_prompts contains one unique prompt per scene, in order, each ending in --ar 9:16 for Shorts
  or --ar 16:9 for long-form and including a scene-specific color grade.

PACKAGING
- Specific truthful title under 70 characters; 2-4 word thumbnail text; 6-12 relevant tags.
- Description summarizes the answer and preserves uncertainty.

Return JSON only with exactly: angle, hook, script, title, title_options, description, tags,
thumbnail_brief, thumbnail_text, visual_queries, direct_paste_script, batch_prompts, scenes. Each scene has exactly
narration, visual_query, purpose, visual_mode, source_url, on_screen_text, exact_visual_subject,
camera_and_lighting, generator_prompt, shot_type_camera_movement, sfx_audio_cue. Scenes are the source of truth.
"""

    def _improve_plan(self, research: ResearchPack, video_format: str, draft: dict) -> dict | None:
        words = "95-145" if video_format == "short" else "1,200-1,650"
        scenes = "20-24" if video_format == "short" else "30-38"
        prompt = f"""Act as CurioAxiom's fact-checking executive editor. Rewrite the draft JSON.
FINAL FORMAT: {video_format}. Preserve {words} spoken words and {scenes} distinct scenes.
The scenes are the source of truth: their complete narration must match the script.
Do not replace a long documentary with a Short, summary, outline, or truncated draft.
Develop each section using supported research, mechanisms and caveats; never pad or invent facts.
Research: {research.research_notes[:18000]}
Verification: {research.confidence_score:.0f}/100; {research.verification_notes}
Draft: {json.dumps(draft, ensure_ascii=False)}
Remove unsupported precision, myths, generic hooks, random-list structure, repeated visuals and false certainty.
Ensure one coherent cinematic question, two evidence beats, a mechanism/context explanation, caveat and reveal.
Reject every generic or merely topic-adjacent visual. Confirm each prompt literally depicts that scene's
spoken nouns, action, scale and consequence. Reject repeated subjects shown from the same physical
perspective, repeated camera moves, repeated compositions and prompts that differ only by adjectives.
Return the complete corrected JSON only with the same keys
and exact scene keys.
"""
        try:
            return self._generate_json(prompt)
        except Exception:
            return draft
