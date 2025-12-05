#!flask/bin/python
from flask import Flask, jsonify, render_template, request, redirect
import pandas as pd
import numpy as np
import os, sys
import json
import csv
from math import *

app = Flask(__name__)


# Thay phần trong route '/' của bạn
@app.route('/')
def index():
    # 1. Đọc dữ liệu phim
    df = pd.read_csv("movie.csv")  # file của bạn

    # 2. Tính trung bình IMDbRating theo Country (dùng Country làm key)
    avg_rating = df.groupby('Country')['Rating'].mean().round(2)
    rating_dict = avg_rating.to_dict()

    # 3. Đọc GeoJSON thế giới
    with open('map.json') as f:
        world = json.load(f)

    # 4. Gắn avg rating vào từng feature
    min_val = avg_rating.min()
    max_val = avg_rating.max()

    for feature in world['features']:
        country_name = feature['properties'].get('name', '')
        code = feature['id']

        # Nhiều nước tên trong GeoJSON khác với CSV → map thủ công một chút
        name_mapping = {
            "United States": "USA",
            "United States of America": "USA",
            "America": "USA",
            "United Kingdom": "UK",
        }
        lookup_name = name_mapping.get(country_name, country_name)

        rating = rating_dict.get(lookup_name)
        feature['properties']['avgIMDbRating'] = rating if rating is not None else None
        feature['properties']['minRating'] = min_val
        feature['properties']['maxRating'] = max_val

    # 5. Danh sách quốc gia có phim (cho dropdown radar)
    countries_with_data = avg_rating.index.tolist()

    return render_template('test.html',
                           geojson=world,
                           min_rating=min_val,
                           max_rating=max_val,
                           countries=countries_with_data)

if __name__ == '__main__':
    app.run(debug=True)
