#!flask/bin/python
from flask import Flask, jsonify, render_template, request
import pandas as pd
import json
import os

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MOVIE_PATH = os.path.join(BASE_DIR, "movie_new.csv")
MAP_PATH = os.path.join(BASE_DIR, "map.json")

# ====================================
# Load dữ liệu một lần khi khởi động
# ====================================
movies_df = pd.read_csv(MOVIE_PATH)

# Cột trong movie_new.csv:
# ['Movie_Title', 'Year', 'Director', 'Actors', 'Rating', 'Runtime(Mins)',
#  'Censor', 'main_genre', 'side_genre', 'Country', 'Total_Gross',
#  'Total_Budget']

REQUIRED_COLS = [
    "Movie_Title", "Year", "Director", "Rating",
    "main_genre", "Country", "Total_Gross", "Total_Budget"
]
missing = [c for c in REQUIRED_COLS if c not in movies_df.columns]
if missing:
    raise RuntimeError("movie_new.csv thiếu cột: %s" % ", ".join(missing))

# Ép kiểu số
movies_df["Year"] = pd.to_numeric(movies_df["Year"], errors="coerce")
movies_df["Rating"] = pd.to_numeric(movies_df["Rating"], errors="coerce")
movies_df["Total_Gross"] = pd.to_numeric(movies_df["Total_Gross"], errors="coerce")
movies_df["Total_Budget"] = pd.to_numeric(movies_df["Total_Budget"], errors="coerce")

movies_df = movies_df.dropna(subset=["Year", "Rating"])

YEAR_MIN = int(movies_df["Year"].min())
YEAR_MAX = int(movies_df["Year"].max())
GENRES = sorted(movies_df["main_genre"].dropna().unique().tolist())


def filter_movies(genre=None, start_year=None, end_year=None):
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


# ======================
# ROUTE: Trang chính
# ======================
@app.route("/")
def index():
    with open(MAP_PATH, "r") as f:
        world = json.load(f)

    return render_template(
        "test.html",
        world_geojson=world,
        year_min=YEAR_MIN,
        year_max=YEAR_MAX,
    )


# ==========================
# API 1: trả meta filter
# ==========================
@app.route("/api/filters")
def api_filters():
    return jsonify(
        {
            "genres": GENRES,
            "year_min": YEAR_MIN,
            "year_max": YEAR_MAX,
        }
    )


# =============================================
# API 2: summary cho heatmap (country level)
# =============================================
@app.route("/api/summary")
def api_summary():
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


# =======================================================
# API 3: chi tiết 1 country (directors + movies scatter)
# =======================================================
@app.route("/api/country_detail")
def api_country_detail():
    """
    Đầu vào:
      - country (bắt buộc)
      - genre, start_year, end_year (filter)
    Trả về:
      - directors: cho bar ngang (top directors by movie_count)
      - top_directors: các đạo diễn có movie_count = max_count
        (mỗi đạo diễn: list phim để vẽ scatter)
    """
    country = request.args.get("country", default=None, type=str)
    if not country:
        return jsonify({"error": "country parameter is required"}), 400

    genre = request.args.get("genre", default=None, type=str)
    start_year = request.args.get("start_year", default=None, type=int)
    end_year = request.args.get("end_year", default=None, type=int)

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
                "top_directors": [],
            }
        )

    # Aggregate per director
    agg = (
        df.groupby("Director")
        .agg(
            movie_count=("Movie_Title", "count"),
            total_gross=("Total_Gross", "sum"),
        )
        .reset_index()
    )

    # Sort: movie_count ↓, total_gross ↓, Director ↑
    agg = agg.sort_values(
        ["movie_count", "total_gross", "Director"],
        ascending=[False, False, True],
    )

    # Danh sách cho bar ngang (top 15)
    directors_list = []
    for _, row in agg.head(15).iterrows():
        directors_list.append(
            {
                "director": row["Director"],
                "movie_count": int(row["movie_count"]),
                "total_gross": float(row["total_gross"]) if not pd.isna(row["total_gross"]) else 0.0,
            }
        )

    # Xử lý trường hợp có "đồng đạo diễn cao nhất"
    max_count = agg["movie_count"].max()
    top_rows = agg[agg["movie_count"] == max_count]

    top_directors = []
    for _, row in top_rows.iterrows():
        name = row["Director"]
        df_top = df[df["Director"] == name].copy()
        # lấy tối đa 5 phim, sort theo Gross
        df_top = df_top.sort_values("Total_Gross", ascending=False).head(5)

        movies = []
        for _, r in df_top.iterrows():
            movies.append(
                {
                    "title": r["Movie_Title"],
                    "budget": float(r["Total_Budget"]) if not pd.isna(r["Total_Budget"]) else 0.0,
                    "gross": float(r["Total_Gross"]) if not pd.isna(r["Total_Gross"]) else 0.0,
                    "rating": float(r["Rating"]) if not pd.isna(r["Rating"]) else None,
                }
            )

        top_directors.append(
            {
                "name": name,
                "movie_count": int(row["movie_count"]),
                "movies": movies,
            }
        )

    return jsonify(
        {
            "country": country,
            "genre": genre,
            "start_year": start_year,
            "end_year": end_year,
            "directors": directors_list,
            "top_directors": top_directors,
        }
    )


if __name__ == "__main__":
    app.run(debug=True)
