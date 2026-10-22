from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Text, DECIMAL, Table, Column, UniqueConstraint
from sqlalchemy.orm import mapped_column, Mapped, relationship

from src.database.base import Base

movie_genres = Table(
    "movie_genres",
    Base.metadata,
    Column("movie_id", ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True),
    Column("genre_id", ForeignKey("genres.id", ondelete="RESTRICT"), primary_key=True),
)
movie_stars = Table(
    "movie_stars",
    Base.metadata,
    Column("movie_id", ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True),
    Column("star_id", ForeignKey("stars.id", ondelete="RESTRICT"), primary_key=True),
)
movie_directors = Table(
    "movie_directors",
    Base.metadata,
    Column("movie_id", ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "director_id", ForeignKey("directors.id", ondelete="RESTRICT"), primary_key=True
    ),
)


class UniqueNameBase(Base):
    __abstract__ = True

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)


class Genre(UniqueNameBase):
    __tablename__ = "genres"

    movies: Mapped[list["Movie"]] = relationship(
        secondary=movie_genres, back_populates="genres"
    )


class Star(UniqueNameBase):
    __tablename__ = "stars"

    movies: Mapped[list["Movie"]] = relationship(
        secondary=movie_stars, back_populates="stars"
    )


class Director(UniqueNameBase):
    __tablename__ = "directors"

    movies: Mapped[list["Movie"]] = relationship(
        secondary=movie_directors,
        back_populates="directors",
    )


class Certification(UniqueNameBase):
    __tablename__ = "certifications"

    movies: Mapped[list["Movie"]] = relationship(
        "Movie", back_populates="certification"
    )


class Movie(Base):
    __tablename__ = "movies"

    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[UUID] = mapped_column(unique=True, default=uuid4)
    name: Mapped[str]
    year: Mapped[int]
    time: Mapped[int]
    imdb: Mapped[float]
    votes: Mapped[int]
    meta_score: Mapped[float | None]
    gross: Mapped[float | None]
    description: Mapped[str] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(DECIMAL(10, 2))
    certification_id: Mapped[int] = mapped_column(
        ForeignKey("certifications.id", ondelete="RESTRICT")
    )

    certification: Mapped[Certification] = relationship(
        "Certification", back_populates="movies"
    )
    genres: Mapped[list[Genre]] = relationship(
        secondary=movie_genres, back_populates="movies"
    )
    stars: Mapped[list[Star]] = relationship(
        secondary=movie_stars, back_populates="movies"
    )
    directors: Mapped[list[Director]] = relationship(
        secondary=movie_directors, back_populates="movies"
    )

    __table_args__ = (
        UniqueConstraint("name", "year", "time", name="uq_movies_name_year_time"),
    )
