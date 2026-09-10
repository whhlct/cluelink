from enum import Enum


class EntityType(str, Enum):
    PERSON = "person"
    MOVIE = "movie"
    TV_SHOW = "tv_show"
    SONG = "song"
    ALBUM = "album"
    ARTIST = "artist"
    BAND = "band"
    COMPANY = "company"
    PLACE = "place"
    COUNTRY = "country"
    GENRE = "genre"
    SPORTS_TEAM = "sports_team"
    BOOK = "book"
    OTHER = "other"


class RelationType(str, Enum):
    ACTED_IN = "acted_in"
    DIRECTED = "directed"
    WROTE = "wrote"
    PRODUCED = "produced"
    MEMBER_OF = "member_of"
    PERFORMED = "performed"
    FEATURED_ON = "featured_on"
    FOUNDED = "founded"
    OWNED_BY = "owned_by"
    BORN_IN = "born_in"
    LOCATED_IN = "located_in"
    BASED_ON = "based_on"
    HAS_GENRE = "has_genre"


class Source(str, Enum):
    WIKIDATA = "wikidata"
    TMDB = "tmdb"
