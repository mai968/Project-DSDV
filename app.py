#!flask/bin/python
from flask import Flask, jsonify, render_template, request
import pandas as pd
import json
import os

app = Flask(__name__)

# =========================
# Load data once at startup
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MOVIE_PATH = os.path.join(BASE_DIR, "movie_new.csv")
MAP_PATH = os.path.join(BASE_DIR, "map.json")

movies_df = pd.read_csv(MOVIE_PATH)

# Columns in movie_new.csv:
# ['Movie_Title', 'Year', 'Director', 'Actors', 'Rating', 'Runtime(Mins)',
#  'Censor', 'main_genre', 'side_genre', 'Country', 'Total_Gross', 'Total_Budget']

REQUIRED_COLS = [
    "Movie_Title", "Year", "Director", "Rating", "main_genre",
    "Country", "Total_Gross", "Total_Budget"
]
missing = [c for c in REQUIRED_COLS if c not in movies_df.columns]
if missing:
    raise RuntimeError("movie_new.csv missing required columns: %s" % ", ".join(missing))

# Clean basic types
movies_df["Year"] = pd.to_numeric(movies_df["Year"], errors="coerce")
movies_df["Rating"] = pd.to_numeric(movies_df["Rating"], errors="coerce")
movies_df["Total_Gross"] = pd.to_numeric(movies_df["Total_Gross"], errors="coerce")
movies_df["Total_Budget"] = pd.to_numeric(movies_df["Total_Budget"], errors="coerce")

movies_df = movies_df.dropna(subset=["Year", "Rating"])

YEAR_MIN = int(movies_df["Year"].min())
YEAR_MAX = int(movies_df["Year"].max())

GENRES = sorted(movies_df["main_genre"].dropna().unique().tolist())


def filter_movies(genre: str = None, start_year: int = None, end_year: int = None):
    """Lọc dataset theo main_genre + khoảng năm."""
    df = movies_df.copy()

    if genre:
        df = df[df["main_genre"].astype(str).str.lower() == genre.lower()]

    if start_year is None:
        start_year = YEAR_MIN
    if end_year is None:
        end_year = YEAR_MAX

    df = df[(df["Year"] >= start_year) & (df["Year"] <= end_year)]
    return df


# ==============
# PAGE ROUTE
# ==============
@app.route("/")
def index():
    # Load world map geojson
    with open(MAP_PATH, "r") as f:
        world = json.load(f)

    return render_template(
        "test.html",
        world_geojson=world,
        year_min=YEAR_MIN,
        year_max=YEAR_MAX,
    )


# ===================
# API 1: Filters meta
# ===================
@app.route("/api/filters")
def api_filters():
    """
    Trả về list main_genre + min/max year để fill bộ lọc bên phải & thanh trượt năm.
    """
    return jsonify(
        {
            "genres": GENRES,
            "year_min": YEAR_MIN,
            "year_max": YEAR_MAX,
        }
    )


# ===============================
# API 2: Summary for heatmap data
# ===============================
@app.route("/api/summary")
def api_summary():
    """
    Dùng cho Heatmap:
    - Lọc theo (genre, start_year, end_year)
    - Group theo Country:
        + avg Rating
        + số phim
        + số đạo diễn
    """
    genre = request.args.get("genre", default=None, type=str)
    start_year = request.args.get("start_year", default=None, type=int)
    end_year = request.args.get("end_year", default=None, type=int)

    df = filter_movies(genre, start_year, end_year)

    if df.empty:
        return jsonify(
            {
                "min_rating": None,
                "max_rating": None,
                "countries": [],
            }
        )

    grouped = df.groupby("Country")

    avg_rating = grouped["Rating"].mean()
    movie_count = grouped["Movie_Title"].count()
    director_count = grouped["Director"].nunique()

    min_rating = float(avg_rating.min())
    max_rating = float(avg_rating.max())

    records = []
    for country in avg_rating.index:
        records.append(
            {
                "country": country,
                "avg_rating": round(float(avg_rating[country]), 2),
                "movie_count": int(movie_count.get(country, 0)),
                "director_count": int(director_count.get(country, 0)),
            }
        )

    return jsonify(
        {
            "min_rating": min_rating,
            "max_rating": max_rating,
            "countries": records,
        }
    )
# =======================================
# API 3: Country detail for bar charts
# =======================================
@app.route("/api/country_detail")
def api_country_detail():
    """
    Khi click 1 country trên map:
    - Lọc theo (genre, year range, country)
    - Bar chart 1: list {director, movie_count}
    - Bar chart 2: top director + 1–5 phim
    """
    genre = request.args.get("genre", default=None, type=str)
    start_year = request.args.get("start_year", default=None, type=int)
    end_year = request.args.get("end_year", default=None, type=int)
    country = request.args.get("country", default=None, type=str)

    if not country:
        return jsonify({"error": "country parameter is required"}), 400

    df = filter_movies(genre, start_year, end_year)
    df = df[df["Country"] == country]

    if df.empty:
        return jsonify(
            {
                "country": country,
                "genre": genre,
                "start_year": start_year,
                "end_year": end_year,
                "directors": [],
                "top_director": None,
            }
        )

    # Directors bar chart: số phim / đạo diễn
    dir_counts = (
        df.groupby("Director")["Movie_Title"]
        .count()
        .sort_values(ascending=False)
    )

    directors_list = [
        {"director": name, "movie_count": int(count)}
        for name, count in dir_counts.head(10).items()
    ]

    top_director_name = dir_counts.index[0] if not dir_counts.empty else None

    top_director_data = None
    if top_director_name:
        df_top = df[df["Director"] == top_director_name].copy()
        df_top = df_top.sort_values("Total_Gross", ascending=False).head(5)

        movies = []
        for _, row in df_top.iterrows():
            movies.append(
                {
                    "title": row["Movie_Title"],
                    "total_gross": float(row["Total_Gross"]) if not pd.isna(row["Total_Gross"]) else None,
                    "total_budget": float(row["Total_Budget"]) if not pd.isna(row["Total_Budget"]) else None,
                }
            )

        top_director_data = {"name": top_director_name, "movies": movies}

    return jsonify(
        {
            "country": country,
            "genre": genre,
            "start_year": start_year,
            "end_year": end_year,
            "directors": directors_list,
            "top_director": top_director_data,
        }
    )
if __name__ == "__main__":
    app.run(debug=True)
