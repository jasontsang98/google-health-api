"""Streamlit dashboard for the Google Health exercise fact tables."""

from datetime import date, timedelta
from pathlib import Path

import duckdb
import altair as alt
import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "health.duckdb"
SPORT_GREEN = "#2da44e"
ZONE_ORDER = ["Light", "Moderate", "Vigorous", "Peak"]
ZONE_COLORS = {
    "Light": "#1f6feb",
    "Moderate": "#2da44e",
    "Vigorous": "#d29922",
    "Peak": "#cf222e",
}

st.set_page_config(page_title="Google Health Exercise Dashboard", page_icon="+", layout="wide")

st.markdown(
    f"""
    <style>
    .stMetric {{ border-top: 3px solid {SPORT_GREEN}; padding-top: 0.5rem; }}
    .calendar-shell {{ width: fit-content; max-width: 100%; margin: 0 auto; overflow-x: auto; }}
    .calendar-layout {{ display: flex; gap: 8px; align-items: flex-start; width: max-content; padding: 8px 0 18px; }}
    .weekday-labels {{ display: grid; grid-template-rows: repeat(7, 20px); gap: 4px; min-width: 34px; color: #8b949e; font-size: 0.7rem; line-height: 20px; }}
    .heatmap {{ display: grid; grid-auto-flow: column; grid-template-rows: repeat(7, 20px); gap: 4px; flex: none; }}
    .heat-cell {{ width: 20px; height: 20px; border: 1px solid #30363d; border-radius: 4px; box-sizing: border-box; background: #161b22; }}
    .calendar-months {{ display: flex; gap: 4px; width: max-content; margin-left: 42px; color: #8b949e; font-size: 0.7rem; }}
    .calendar-month {{ width: 20px; min-width: 20px; text-align: center; }}
    .heat-cell.level-1 {{ background: #9be9a8; }}
    .heat-cell.level-2 {{ background: #40c463; }}
    .heat-cell.level-3 {{ background: #30a14e; }}
    .heat-cell.level-4 {{ background: #216e39; }}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data
def load_dashboard_data(database_path: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    exercise_query = """
        select *
        from fct_exercise
        where upper(exercise_type) <> 'WALKING'
    """
    metrics_query = """
        select data_point_id, exercise_type, metric_group, metric_name, metric_value, metric_unit
        from int_exercise_metrics
        where upper(exercise_type) <> 'WALKING'
    """
    badminton_query = "select * from fct_badminton"
    with duckdb.connect(database_path, read_only=True) as connection:
        exercises = connection.sql(exercise_query).df()
        metrics = connection.sql(metrics_query).df()
        badminton = connection.sql(badminton_query).df()
    if not metrics.empty:
        metric_values = metrics.pivot_table(
            index="data_point_id",
            columns="metric_name",
            values="metric_value",
            aggfunc="max",
        ).reset_index()
        metric_values.columns.name = None
        exercises = exercises.merge(metric_values, on="data_point_id", how="left")
    return exercises, metrics, badminton


def render_heatmap(filtered: pd.DataFrame, end_date: date, days: int) -> None:
    start_date = end_date - timedelta(days=days - 1)
    daily = filtered.groupby("start_date").size().to_dict()
    dates = pd.date_range(start=start_date, end=end_date, freq="D").date
    max_sessions = max(daily.values(), default=1)
    cells: list[str] = ["<div></div>"] * start_date.weekday()
    for current_date in dates:
        count = daily.get(current_date, 0)
        if count == 0:
            level = 0
        else:
            level = min(4, max(1, int((count / max_sessions) * 4)))
        cells.append(
            f'<div class="heat-cell level-{level}" title="{current_date}: {count} session(s)"></div>'
        )
    weekday_labels = "".join(
        f"<span>{label}</span>" for label in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    )
    week_count = (len(cells) + 6) // 7
    month_labels = []
    last_month_label = None
    for week_index in range(week_count):
        week_start = start_date - timedelta(days=start_date.weekday()) + timedelta(days=week_index * 7)
        week_end = week_start + timedelta(days=6)
        week_dates = [current_date for current_date in dates if week_start <= current_date <= week_end]
        month_label = ""
        if week_dates:
            month_starts = [current_date for current_date in week_dates if current_date.day <= 7]
            if week_index == 0:
                month_label = week_dates[0].strftime("%b")
            elif month_starts:
                month_label = month_starts[0].strftime("%b")
        if month_label == last_month_label:
            month_label = ""
        elif month_label:
            last_month_label = month_label
        month_labels.append(f'<span class="calendar-month">{month_label}</span>')
    calendar_html = (
        '<div class="calendar-shell">'
        f'<div class="calendar-months">{"".join(month_labels)}</div>'
        '<div class="calendar-layout">'
        f'<div class="weekday-labels">{weekday_labels}</div>'
        f'<div class="heatmap" style="grid-template-columns: repeat({week_count}, 20px);">'
        + "".join(cells)
        + "</div></div></div>"
    )
    st.markdown(calendar_html, unsafe_allow_html=True)
    st.caption(f"{start_date} to {end_date} · darker green means more sessions")


def format_metric(value: float | int | None, suffix: str = "") -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{value:,.1f}{suffix}"


def render_overview(exercises: pd.DataFrame) -> None:
    st.subheader("Overview")
    with st.sidebar:
        st.header("Overview filters")
        type_options = sorted(exercises["exercise_type"].dropna().unique())
        selected_types = st.multiselect("Exercise types", type_options, default=type_options)

    end_date = exercises["start_date"].max()
    range_days = 365
    start_date = end_date - timedelta(days=range_days - 1)
    filtered = exercises[
        exercises["exercise_type"].isin(selected_types)
        & exercises["start_date"].between(start_date, end_date)
    ].copy()

    total_duration = filtered["active_duration_seconds"].sum()
    average_hr = filtered.get("average_heart_rate_beats_per_minute", pd.Series(dtype=float)).mean()
    average_calories = filtered.get("calories_kcal", pd.Series(dtype=float)).mean()
    summary = st.columns(4)
    summary[0].metric("Sessions", f"{len(filtered):,}")
    summary[1].metric("Active minutes", format_metric(total_duration / 60 if pd.notna(total_duration) else None))
    summary[2].metric("Average calories", format_metric(average_calories))
    summary[3].metric("Average heart rate", format_metric(average_hr, " bpm"))

    st.subheader("Sessions over time")
    render_heatmap(filtered, end_date, range_days)

    st.subheader("Average by exercise type")
    average_by_type = (
        filtered.groupby("exercise_type")
        .agg(
            average_active_minutes=("active_duration_seconds", lambda values: values.mean() / 60),
            average_calories=("calories_kcal", "mean"),
            average_heart_rate=("average_heart_rate_beats_per_minute", "mean"),
        )
        .sort_index()
    )
    st.dataframe(average_by_type.round(1), width="stretch")
    chart_columns = st.columns(3)
    with chart_columns[0]:
        st.caption("Average active minutes per session")
        st.bar_chart(average_by_type["average_active_minutes"], color=SPORT_GREEN)
    with chart_columns[1]:
        st.caption("Average calories per session")
        st.bar_chart(average_by_type["average_calories"], color="#d29922")
    with chart_columns[2]:
        st.caption("Average heart rate")
        st.bar_chart(average_by_type["average_heart_rate"], color="#1f6feb")

    st.subheader("Exercise records")
    st.dataframe(
        filtered[
            [
                "data_point_id",
                "exercise_type",
                "display_name",
                "start_time",
                "end_time",
                "active_duration_seconds",
                "data_source_platform",
            ]
        ].sort_values("start_time", ascending=False),
        width="stretch",
        hide_index=True,
    )


def render_exercise_detail(exercises: pd.DataFrame, badminton: pd.DataFrame) -> None:
    st.subheader("By exercise")
    options = ["BADMINTON"] if not badminton.empty else []
    if not options:
        st.info("No badminton fact data is available yet.")
        return
    selected_type = st.selectbox("Exercise type to view", options)
    selected = exercises[exercises["exercise_type"] == selected_type].copy()
    duplicate_metric_columns = [
        column for column in badminton.columns
        if column != "data_point_id" and column in selected.columns
    ]
    selected = selected.drop(columns=duplicate_metric_columns)
    selected = selected.merge(badminton, on="data_point_id", how="inner")

    summary = st.columns(4)
    summary[0].metric("Sessions", f"{len(selected):,}")
    summary[1].metric("Average active minutes", format_metric(selected["active_duration_seconds"].mean() / 60))
    summary[2].metric("Average calories", format_metric(selected["calories_kcal"].mean()))
    summary[3].metric(
        "Average heart rate",
        format_metric(selected["average_heart_rate_beats_per_minute"].mean(), " bpm"),
    )

    st.subheader("Badminton trends")
    trend = selected.set_index("start_time").sort_index()
    chart_columns = st.columns(3)
    with chart_columns[0]:
        st.caption("Calories per session")
        st.line_chart(trend["calories_kcal"], color="#d29922")
    with chart_columns[1]:
        st.caption("Average heart rate")
        st.line_chart(trend["average_heart_rate_beats_per_minute"], color="#1f6feb")
    with chart_columns[2]:
        st.caption("Steps per session")
        st.line_chart(trend["steps"], color=SPORT_GREEN)

    selected["start_time"] = pd.to_datetime(selected["start_time"])

    zone_trend = selected[
        [
            "start_time",
            "light_zone_seconds",
            "moderate_zone_seconds",
            "vigorous_zone_seconds",
            "peak_zone_seconds",
        ]
    ].copy()
    zone_trend["Light"] = zone_trend.pop("light_zone_seconds") / 60
    zone_trend["Moderate"] = zone_trend.pop("moderate_zone_seconds") / 60
    zone_trend["Vigorous"] = zone_trend.pop("vigorous_zone_seconds") / 60
    zone_trend["Peak"] = zone_trend.pop("peak_zone_seconds") / 60
    zone_percentage_trend = zone_trend.copy()
    zone_percentage_trend["session_minutes"] = selected["active_duration_seconds"] / 60
    for zone in ZONE_ORDER:
        zone_percentage_trend[zone] = (
            zone_percentage_trend[zone]
            .div(zone_percentage_trend["session_minutes"].where(lambda values: values > 0))
            .mul(100)
            .round(2)
        )

    zone_view = st.radio(
        "Zone trend view",
        ["Minutes", "Share of active session (%)"],
        horizontal=True,
        index=0,
    )
    if zone_view == "Minutes":
        zone_chart_data = zone_trend
        zone_value_column = "minutes"
        zone_axis_title = "Minutes"
        zone_tooltip_format = ".1f"
    else:
        zone_chart_data = zone_percentage_trend
        zone_value_column = "percentage"
        zone_axis_title = "Share of active session (%)"
        zone_tooltip_format = ".2f"

    st.subheader("Heart-rate zone trend")
    zone_trend_chart = (
        alt.Chart(zone_chart_data)
        .transform_fold(ZONE_ORDER, as_=["zone", zone_value_column])
        .mark_line(point=True)
        .encode(
            x=alt.X("start_time:T", title="Session"),
            y=alt.Y(
                f"{zone_value_column}:Q",
                title=zone_axis_title,
                axis=alt.Axis(format=zone_tooltip_format),
            ),
            color=alt.Color(
                "zone:N",
                sort=ZONE_ORDER,
                scale=alt.Scale(
                    domain=ZONE_ORDER,
                    range=[ZONE_COLORS[zone] for zone in ZONE_ORDER],
                ),
                legend=alt.Legend(title="Zone"),
            ),
            tooltip=[
                alt.Tooltip("start_time:T", title="Session"),
                alt.Tooltip("zone:N", title="Zone"),
                alt.Tooltip(
                    f"{zone_value_column}:Q",
                    title=zone_axis_title,
                    format=zone_tooltip_format,
                ),
            ],
        )
        .properties(height=320)
    )
    st.altair_chart(zone_trend_chart, use_container_width=True)

    session_options = selected["start_time"].sort_values(ascending=False).tolist()
    selected_start_time = st.selectbox(
        "Session id (start time)",
        session_options,
        format_func=lambda value: value.strftime("%Y-%m-%d %H:%M:%S"),
    )
    session = selected.loc[selected["start_time"] == selected_start_time].iloc[0]

    st.subheader("Selected badminton session")
    session_kpis = st.columns(4)
    session_kpis[0].metric(
        "Active minutes",
        format_metric(session["active_duration_seconds"] / 60),
    )
    session_kpis[1].metric("Average heart rate", format_metric(
        session["average_heart_rate_beats_per_minute"], " bpm"
    ))
    session_kpis[2].metric("Calories", format_metric(session["calories_kcal"]))
    session_kpis[3].metric("Steps", f'{session["steps"]:,.0f}')

    zone_columns = {
        "Light": "light_zone_seconds",
        "Moderate": "moderate_zone_seconds",
        "Vigorous": "vigorous_zone_seconds",
        "Peak": "peak_zone_seconds",
    }
    zone_details = pd.DataFrame(
        {
            "zone": list(zone_columns),
            "minutes": [session[column] / 60 for column in zone_columns.values()],
        }
    ).set_index("zone").reindex(ZONE_ORDER)
    st.subheader("Heart-rate zones")
    zone_chart = (
        alt.Chart(zone_details.reset_index())
        .mark_bar()
        .encode(
            x=alt.X("zone:N", sort=ZONE_ORDER, title=None),
            y=alt.Y("minutes:Q", title="Minutes"),
            color=alt.Color(
                "zone:N",
                scale=alt.Scale(
                    domain=ZONE_ORDER,
                    range=[ZONE_COLORS[zone] for zone in ZONE_ORDER],
                ),
                legend=None,
            ),
            tooltip=[alt.Tooltip("zone:N", title="Zone"), alt.Tooltip("minutes:Q", format=".1f")],
        )
        .properties(height=280)
    )
    st.altair_chart(zone_chart, use_container_width=True)
    styled_zones = zone_details.style.apply(
        lambda row: [f"background-color: {ZONE_COLORS[row.name]}33"] * len(row), axis=1
    ).format({"minutes": "{:.1f}"})
    st.dataframe(styled_zones, width="stretch")


def main() -> None:
    st.title("Google Health Exercise Dashboard")
    st.caption("Walking is excluded as noise. Data source: dbt fact tables in health.duckdb")
    if not DATABASE.exists():
        st.error("health.duckdb was not found. Run dbt build before starting the dashboard.")
        st.stop()

    exercises, _, badminton = load_dashboard_data(str(DATABASE))
    if exercises.empty:
        st.warning("No non-walking exercise records are available.")
        st.stop()
    exercises["start_date"] = pd.to_datetime(exercises["start_time"]).dt.date

    overview_tab, exercise_tab = st.tabs(["Overview", "By exercise"])
    with overview_tab:
        render_overview(exercises)
    with exercise_tab:
        render_exercise_detail(exercises, badminton)


if __name__ == "__main__":
    main()
