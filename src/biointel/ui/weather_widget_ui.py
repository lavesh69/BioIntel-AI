"""Streamlit worldwide weather UI with truthful provider and cache states."""
from __future__ import annotations

from typing import Any

import streamlit as st

from biointel.services.weather_environment_engine import (
    STATUS_CACHED,
    STATUS_LIVE,
    STATUS_LIVE_FALLBACK,
    STATUS_STALE_CACHED,
    WeatherEnvironmentEngine,
)
from biointel.ui.browser_geolocation import one_shot_geolocation


@st.cache_resource(show_spinner=False)
def _weather_engine() -> WeatherEnvironmentEngine:
    return WeatherEnvironmentEngine()


def _display(value: Any, suffix: str = "") -> str:
    return "Unavailable" if value is None else f"{value}{suffix}"


def _condition_emoji(condition: Any) -> str:
    text = str(condition or "").casefold()
    if any(word in text for word in ("thunder", "hail")):
        return "⛈️"
    if any(word in text for word in ("snow", "sleet", "blizzard")):
        return "🌨️"
    if any(word in text for word in ("rain", "drizzle", "shower")):
        return "🌧️"
    if any(word in text for word in ("fog", "mist", "haze")):
        return "🌫️"
    if any(word in text for word in ("partly", "mainly clear")):
        return "🌤️"
    if any(word in text for word in ("cloud", "overcast")):
        return "☁️"
    if any(word in text for word in ("clear", "sunny")):
        return "☀️"
    return "🌍"


def _compact_location(value: Any, limit: int = 92) -> str:
    text = " ".join(str(value or "Selected location").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip(" ,") + "…"


def _status_badge(status: str) -> tuple[str, str, str]:
    if status in {STATUS_LIVE, STATUS_LIVE_FALLBACK}:
        return "Live API", "green", "🟢"
    if status == STATUS_CACHED:
        return "Cached weather", "blue", "🔵"
    if status == STATUS_STALE_CACHED:
        return "Stale cache", "orange", "🟠"
    return status or "Unavailable", "red", "🔴"


def _remember_recent(location: dict[str, Any]) -> None:
    recent = list(st.session_state.get("weather_recent_locations", []))
    key = f"{location['latitude']:.5f},{location['longitude']:.5f}"
    record = dict(location, key=key)
    recent = [item for item in recent if item.get("key") != key]
    st.session_state["weather_recent_locations"] = [record, *recent][:8]


def _current_location_control(engine: WeatherEnvironmentEngine) -> None:
    st.caption("📍 Auto-detect uses one browser request · no continuous tracking or automatic storage")
    result = one_shot_geolocation(key="weather_browser_location")
    error = getattr(result, "error", "")
    location = getattr(result, "location", None)
    if error:
        st.info(error)
    if location:
        latitude = getattr(location, "latitude", None)
        longitude = getattr(location, "longitude", None)
        if latitude is None and isinstance(location, dict):
            latitude, longitude = location.get("latitude"), location.get("longitude")
        if latitude is not None and longitude is not None:
            coordinates = engine.reverse_geocode(latitude, longitude) or {
                "name": f"Current location ({latitude:.5f}, {longitude:.5f})",
                "latitude": latitude,
                "longitude": longitude,
                "country": "",
                "admin1": "",
                "timezone": "UTC",
            }
            if st.button("Use this one-time location", icon=":material/my_location:"):
                st.session_state["weather_selected_location"] = coordinates
                _remember_recent(coordinates)
                st.rerun()


def _location_search(engine: WeatherEnvironmentEngine) -> dict[str, Any] | None:
    with st.form("weather_location_search", border=False):
        with st.container(horizontal=True, vertical_alignment="bottom"):
            query = st.text_input(
                "City, region, country, postal code, or latitude/longitude",
                placeholder="Examples: Cambridge UK · 02139 · 28.6139, 77.2090",
                key="weather_search_query",
            )
            submitted = st.form_submit_button("Search", icon=":material/search:", type="primary")
    if submitted:
        with st.spinner("Searching worldwide locations…"):
            st.session_state["weather_search_results"] = engine.geocode_location_search(query)
        if not st.session_state["weather_search_results"]:
            st.session_state.pop("weather_selected_location", None)
    results = list(st.session_state.get("weather_search_results", []))
    if submitted and not results:
        st.warning("Location Not Found")
        if engine.last_geocode_error:
            st.caption(f"Provider state: {engine.last_geocode_status}. {engine.last_geocode_error}")
    if results:
        selected = st.selectbox(
            "Select the exact location",
            results,
            format_func=lambda item: (
                f"{item['name']} · {item.get('timezone', 'UTC')} · "
                f"{item['latitude']:.5f}, {item['longitude']:.5f}"
            ),
            key="weather_location_match",
        )
        if st.button("Use selected location", icon=":material/location_on:"):
            st.session_state["weather_selected_location"] = selected
            _remember_recent(selected)
            st.rerun()
    return st.session_state.get("weather_selected_location")


def _saved_locations(engine: WeatherEnvironmentEngine, selected: dict[str, Any] | None) -> None:
    with st.expander("Recent, favourite, and research locations", on_change="rerun"):
        recent = list(st.session_state.get("weather_recent_locations", []))
        saved = engine.load_saved_locations()
        if recent:
            recent_choice = st.selectbox("Recent locations", recent, format_func=lambda item: item["name"])
            if st.button("Open recent", icon=":material/history:"):
                st.session_state["weather_selected_location"] = recent_choice
                st.rerun()
        if selected:
            site_type = st.selectbox(
                "Save as",
                ["Favourite", "Research site", "Lab site", "Clinical partner site"],
            )
            if st.button("Save selected location", icon=":material/bookmark_add:"):
                engine.save_location(selected, location_type=site_type)
                st.success("Location saved. Precise coordinates were stored because you explicitly requested it.")
                st.rerun()
        if saved:
            remove = st.selectbox("Saved locations", saved, format_func=lambda item: f"{item['name']} · {item['type']}")
            with st.container(horizontal=True):
                if st.button("Open saved", icon=":material/bookmark:"):
                    st.session_state["weather_selected_location"] = remove
                    st.rerun()
                if st.button("Remove saved", icon=":material/delete:"):
                    engine.remove_saved_location(remove["key"])
                    st.rerun()
        elif not recent:
            st.info("No recent or saved locations yet.")


def _weather_header(weather: dict[str, Any]) -> None:
    status = weather["status"]
    label = (
        f"{status} · {weather['location_name']} · "
        f"{weather['latitude']:.5f}, {weather['longitude']:.5f}"
    )
    if status in {STATUS_LIVE, STATUS_LIVE_FALLBACK}:
        st.success(label)
    elif status in {STATUS_CACHED, STATUS_STALE_CACHED}:
        st.warning(label)
    else:
        st.error(label)
    if weather.get("error"):
        st.caption(f"Live provider note: {weather['error']}")


def _current_metrics(weather: dict[str, Any]) -> None:
    current = weather["current"]
    columns = st.columns(4)
    columns[0].metric("Temperature", _display(current.get("temperature"), f" {current['unit']}"))
    columns[0].caption(f"Feels like: {_display(current.get('feels_like'), ' ' + current['unit'])}")
    columns[1].metric("Condition", current.get("weather_condition", "Unavailable"))
    columns[1].caption(f"Cloud cover: {_display(current.get('cloud_cover_pct'), '%')}")
    columns[2].metric("Humidity", _display(current.get("humidity_pct"), "%"))
    columns[2].caption(f"Pressure: {_display(current.get('pressure_hpa'), ' hPa')}")
    columns[3].metric("Wind", _display(current.get("wind_speed_kmh"), " km/h"))
    columns[3].caption(
        f"Direction {_display(current.get('wind_direction_deg'), '°')} · "
        f"gusts {_display(current.get('wind_gusts_kmh'), ' km/h')}"
    )
    secondary = st.columns(4)
    secondary[0].metric("Precipitation", _display(current.get("precipitation_mm"), " mm"))
    secondary[1].metric("Visibility", _display(current.get("visibility_km"), " km"))
    secondary[2].metric("UV index", _display(current.get("uv_index")))
    secondary[3].metric("Sunrise / sunset", f"{current.get('sunrise') or '—'} / {current.get('sunset') or '—'}")


def _weather_views(engine: WeatherEnvironmentEngine, weather: dict[str, Any], unit: str) -> None:
    tabs = st.tabs(
        ["Hourly", "7-day", "Air quality", "Official alerts", "Compare sites", "Provenance"],
        on_change="rerun",
    )
    if tabs[0].open:
        with tabs[0]:
            rows = weather.get("hourly_24h", [])
            if rows:
                st.dataframe(rows, hide_index=True)
            else:
                st.info("Hourly forecast unavailable.")
    if tabs[1].open:
        with tabs[1]:
            rows = weather.get("daily_7d", [])
            if rows:
                st.dataframe(rows, hide_index=True)
            else:
                st.info("Daily forecast unavailable.")
    if tabs[2].open:
        with tabs[2]:
            aqi = weather["air_quality"]
            if not aqi.get("available"):
                st.warning("Air Quality Data Unavailable")
                if aqi.get("error"):
                    st.caption(aqi["error"])
            else:
                st.info(f"{aqi['status']} · {aqi['provenance']} · {aqi['data_source']}")
                metrics = st.columns(4)
                metrics[0].metric("US AQI", _display(aqi.get("aqi_index")))
                metrics[1].metric("PM2.5", _display(aqi.get("pm2_5_ug_m3"), " µg/m³"))
                metrics[2].metric("PM10", _display(aqi.get("pm10_ug_m3"), " µg/m³"))
                metrics[3].metric("Ozone", _display(aqi.get("o3_ug_m3"), " µg/m³"))
                st.caption(
                    f"NO₂ {_display(aqi.get('no2_ug_m3'))} · SO₂ {_display(aqi.get('so2_ug_m3'))} · "
                    f"CO {_display(aqi.get('co_ug_m3'))} · observation {aqi.get('observation_time')}"
                )
    if tabs[3].open:
        with tabs[3]:
            st.info(weather["alerts_status"])
            for alert in weather.get("alerts", []):
                with st.container(border=True):
                    st.write(f"**{alert.get('severity') or 'Severity unavailable'}** · {alert.get('affected_area') or 'Area unavailable'}")
                    st.write(alert.get("description") or "No description supplied.")
                    st.caption(
                        f"Authority: {alert.get('issuing_authority')} · issued {alert.get('issue_time')} · "
                        f"effective {alert.get('effective')} · expires {alert.get('expires')} · source {alert.get('source')}"
                    )
    if tabs[4].open:
        with tabs[4]:
            saved = engine.load_saved_locations()
            choices = st.multiselect(
                "Saved locations to compare",
                saved,
                format_func=lambda item: f"{item['name']} · {item['type']}",
            )
            if st.button("Compare selected sites", icon=":material/compare_arrows:"):
                if len(choices) < 2:
                    st.warning("Select at least two saved locations.")
                else:
                    with st.spinner("Retrieving each selected site…"):
                        st.dataframe(engine.compare_multiple_locations(choices, unit_temp=unit), hide_index=True)
    if tabs[5].open:
        with tabs[5]:
            st.json({
                "provider": weather["provider"],
                "provider_registry": weather["provider_registry"],
                "location": weather["location_name"],
                "timezone": weather.get("timezone"),
                "elevation_m": weather.get("elevation_m"),
                "observation_time": weather.get("observation_time"),
                "retrieved_at": weather.get("retrieved_at"),
                "delivery_state": weather["status"],
                "cache_age_seconds": weather.get("cache_age_seconds"),
                "cache_expires_at": weather.get("cache_expires_at"),
            })


def render_global_weather_widget() -> None:
    engine = _weather_engine()
    st.subheader("Global Weather & Environmental Conditions")
    st.caption("Worldwide search, exact result selection, one-shot current location, real forecasts, modelled AQI, and truthful cache provenance.")
    unit = st.segmented_control("Temperature unit", ["Celsius", "Fahrenheit"], default="Celsius", key="weather_unit")
    selected = _location_search(engine)
    _current_location_control(engine)
    _saved_locations(engine, selected)
    selected = st.session_state.get("weather_selected_location")
    if not selected:
        st.info("Search and select an exact location, enter coordinates, use a saved site, or explicitly request browser location.")
        return
    with st.container(horizontal=True):
        refresh = st.button("Force provider refresh", icon=":material/refresh:", type="primary")
        st.caption("Forced refresh invalidates the location cache and performs a new provider request.")
    if refresh:
        engine.invalidate_cache(selected["latitude"], selected["longitude"])
    with st.spinner("Refreshing live provider data…" if refresh else "Loading weather data…"):
        weather = engine.fetch_weather_and_forecast(
            selected["latitude"], selected["longitude"], selected["name"], unit_temp=unit or "Celsius", force_refresh=refresh,
        )
    st.session_state["weather_last_snapshot"] = weather
    _weather_header(weather)
    _current_metrics(weather)
    _weather_views(engine, weather, unit or "Celsius")


def render_compact_weather_card() -> None:
    """Render real weather as a compact single-line home status strip."""
    engine = _weather_engine()
    selected = st.session_state.get("weather_selected_location")
    snapshot = st.session_state.get("weather_last_snapshot")

    with st.container(border=True, gap=None, key="home_weather_strip"):
        if not selected:
            with st.container(
                horizontal=True,
                horizontal_alignment="distribute",
                vertical_alignment="center",
                gap="small",
            ):
                st.caption("🌦️ **Weather** · 📍 Location needed", width="stretch")
                with st.popover(
                    "Set location",
                    icon=":material/edit_location:",
                    type="tertiary",
                    width="content",
                ):
                    st.caption("Search once or use one-time browser auto-detect.")
                    selected = _location_search(engine)
                    _current_location_control(engine)
                    st.page_link(
                        "pages/274_System_Health_Connectivity_and_Weather_Widgets.py",
                        label="Open weather workspace",
                        icon=":material/public:",
                        width="stretch",
                    )
            if not selected:
                return

        snapshot_matches = (
            snapshot
            and snapshot.get("latitude") == selected.get("latitude")
            and snapshot.get("longitude") == selected.get("longitude")
        )
        if not snapshot_matches:
            unit = st.session_state.get("weather_unit") or "Celsius"
            with st.spinner("🌦️ Loading real weather…"):
                snapshot = engine.fetch_weather_and_forecast(
                    selected["latitude"],
                    selected["longitude"],
                    selected["name"],
                    unit_temp=unit,
                )
            st.session_state["weather_last_snapshot"] = snapshot

        current = snapshot["current"]
        status_label, _status_color, status_dot = _status_badge(snapshot["status"])
        condition = str(current.get("weather_condition") or "Unavailable")
        compact_condition = condition if len(condition) <= 28 else f"{condition[:27]}…"
        condition_emoji = _condition_emoji(condition)
        unit = str(current.get("unit") or "")
        location = _compact_location(snapshot.get("location_name"), limit=44)

        summary = (
            f"🌦️ **Weather** · 📍 **{location}** · "
            f"🌡️ {_display(current.get('temperature'), f' {unit}')} · "
            f"{condition_emoji} {compact_condition} · "
            f"💧 {_display(current.get('humidity_pct'), '%')} · "
            f"💨 {_display(current.get('wind_speed_kmh'), ' km/h')} · "
            f"🌧️ {_display(current.get('precipitation_mm'), ' mm')} · "
            f"👁️ {_display(current.get('visibility_km'), ' km')} · "
            f"{status_dot} {status_label}"
        )

        with st.container(
            horizontal=True,
            horizontal_alignment="distribute",
            vertical_alignment="center",
            gap="small",
        ):
            st.caption(summary, width="stretch")
            with st.popover(
                "Details",
                icon=":material/tune:",
                type="tertiary",
                width="content",
            ):
                st.caption(
                    f"Feels like {_display(current.get('feels_like'), f' {unit}')} · "
                    f"☁️ Cloud {_display(current.get('cloud_cover_pct'), '%')}"
                )
                st.caption(
                    f"🧭 Pressure {_display(current.get('pressure_hpa'), ' hPa')} · "
                    f"🌬️ Gusts {_display(current.get('wind_gusts_kmh'), ' km/h')} · "
                    f"☀️ UV {_display(current.get('uv_index'))}"
                )
                st.caption(
                    f"🕒 {snapshot.get('retrieved_at') or 'time unavailable'} · "
                    f"{snapshot.get('provider') or 'Provider unavailable'}"
                )
                if snapshot.get("error"):
                    st.warning(snapshot["error"], icon=":material/cloud_off:")
                with st.expander(
                    "Change location",
                    icon=":material/edit_location:",
                    on_change="rerun",
                ):
                    _location_search(engine)
                    _current_location_control(engine)
                st.page_link(
                    "pages/274_System_Health_Connectivity_and_Weather_Widgets.py",
                    label="Open full weather workspace",
                    icon=":material/public:",
                    width="stretch",
                )
                if st.button(
                    "Refresh weather",
                    icon=":material/refresh:",
                    key="home_weather_refresh",
                    width="stretch",
                ):
                    engine.invalidate_cache(selected["latitude"], selected["longitude"])
                    st.session_state.pop("weather_last_snapshot", None)
                    st.rerun()
