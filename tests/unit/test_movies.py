import json

import pytest
from pydantic import ValidationError

from src.movies.seed import load_movies, SEED_DATA_PATH
from tests.helpers import seed_movie_payload


def test_load_movies():
    movies = load_movies(SEED_DATA_PATH)
    assert len(movies) == 100


def test_load_movies_with_invalid_movie(tmp_path):
    path = tmp_path / "seed.json"
    data = [seed_movie_payload(year=1800)]
    path.write_text(json.dumps(data))

    with pytest.raises(ValidationError) as exc_info:
        load_movies(path)
    assert exc_info.value.errors()[0]["loc"] == (0, "year")
