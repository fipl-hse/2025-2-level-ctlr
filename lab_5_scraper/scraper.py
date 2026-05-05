"""
Crawler implementation.
"""
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent))

# pylint: disable=too-many-arguments, too-many-instance-attributes, unused-import, undefined-variable, unused-argument
import datetime
import json
import pathlib

import requests
import regex as re
from bs4 import BeautifulSoup, Tag

from core_utils.article.article import Article
from core_utils.config_dto import ConfigDTO

class IncorrectSeedURLError(Exception):
    """Raised when seed URL does not match standard pattern."""
    pass


class NumberOfArticlesOutOfRangeError(Exception):
    """Raised when total number of articles is out of range 1-150."""
    pass


class IncorrectNumberOfArticlesError(Exception):
    """Raised when total number of articles is not integer or less than 0."""
    pass


class IncorrectHeadersError(Exception):
    """Raised when headers are not in a form of dictionary."""
    pass


class IncorrectEncodingError(Exception):
    """Raised when encoding is not specified as a string."""
    pass


class IncorrectTimeoutError(Exception):
    """Raised when timeout value is not a positive integer less than 60."""
    pass


class IncorrectVerifyError(Exception):
    """Raised when verify certificate or headless mode value is not boolean."""
    pass


class Config:
    """
    Class for unpacking and validating configurations.
    """

    def __init__(self, path_to_config: pathlib.Path) -> None:
        """
        Initialize an instance of the Config class.

        Args:
            path_to_config (pathlib.Path): Path to configuration.
        """
        self.path_to_config = path_to_config

        self._seed_urls: list[str] = []
        self._num_articles: int = 0
        self._headers: dict[str, str] = {}
        self._encoding: str = ""
        self._timeout: int = 0
        self._should_verify_certificate: bool = False
        self._headless_mode: bool = False
        
        self._validate_config_content()

    def _extract_config_content(self) -> ConfigDTO:
        """
        Get config values.

        Returns:
            ConfigDTO: Config values
        """
        with open(self.path_to_config, 'r', encoding='utf-8') as file:
            config_data = json.load(file)
        
        return ConfigDTO(
            seed_urls=config_data.get('seed_urls', []),
            total_articles_to_find_and_parse=config_data.get('total_articles_to_find_and_parse', 0),
            headers=config_data.get('headers', {}),
            encoding=config_data.get('encoding', 'utf-8'),
            timeout=config_data.get('timeout', 30),
            should_verify_certificate=config_data.get('should_verify_certificate', True),
            headless_mode=config_data.get('headless_mode', False)
        )

    def _validate_config_content(self) -> None:
        """
        Ensure configuration parameters are not corrupt.
        """
        config_dto = self._extract_config_content()

        if not isinstance(config_dto.seed_urls, list):
            raise IncorrectSeedURLError("Seed URLs must be a list")

        if not config_dto.seed_urls:
            raise IncorrectSeedURLError("Seed URLs cannot be empty")

        url_pattern = re.compile(r'^https?://(www\.)?')
        for url in config_dto.seed_urls:
            if not isinstance(url, str):
                raise IncorrectSeedURLError(f"Seed URL must be a string: {url}")
            if not url_pattern.match(url):
                raise IncorrectSeedURLError(f"Invalid seed URL format: {url}")

        total = config_dto.total_articles_to_find_and_parse
        if not isinstance(total, int):
            raise IncorrectNumberOfArticlesError(
                "Total articles must be an integer"
            )

        if total < 0:
            raise IncorrectNumberOfArticlesError(
                "Total articles cannot be negative"
            )

        if total < 1 or total > 150:
            raise NumberOfArticlesOutOfRangeError(
                "Total articles must be between 1 and 150"
            )

        if not isinstance(config_dto.headers, dict):
            raise IncorrectHeadersError("Headers must be a dictionary")

        if not isinstance(config_dto.encoding, str):
            raise IncorrectEncodingError("Encoding must be a string")

        timeout = config_dto.timeout
        if not isinstance(timeout, int):
            raise IncorrectTimeoutError("Timeout must be an integer")

        if timeout <= 0 or timeout > 60:
            raise IncorrectTimeoutError(
                "Timeout must be between 1 and 60 seconds"
            )

        if not isinstance(config_dto.should_verify_certificate, bool):
            raise IncorrectVerifyError(
                "Verify certificate must be a boolean"
            )

        if not isinstance(config_dto.headless_mode, bool):
            raise IncorrectVerifyError("Headless mode must be a boolean")

        self._seed_urls = config_dto.seed_urls
        self._num_articles = config_dto.total_articles_to_find_and_parse
        self._headers = config_dto.headers
        self._encoding = config_dto.encoding
        self._timeout = config_dto.timeout
        self._should_verify_certificate = config_dto.should_verify_certificate
        self._headless_mode = config_dto.headless_mode

    def get_seed_urls(self) -> list[str]:
        """
        Retrieve seed urls.

        Returns:
            list[str]: Seed urls
        """
        return self._seed_urls

    def get_num_articles(self) -> int:
        """
        Retrieve total number of articles to scrape.

        Returns:
            int: Total number of articles to scrape
        """
        return self._num_articles

    def get_headers(self) -> dict[str, str]:
        """
        Retrieve headers to use during requesting.

        Returns:
            dict[str, str]: Headers
        """
        return self._headers

    def get_encoding(self) -> str:
        """
        Retrieve encoding to use during parsing.

        Returns:
            str: Encoding
            str. Encoding
        """
        return self._encoding

    def get_timeout(self) -> int:
        """
        Retrieve number of seconds to wait for response.

        Returns:
            int: Number of seconds to wait for response
        """
        return self._timeout
        

    def get_verify_certificate(self) -> bool:
        """
        Retrieve whether to verify certificate.

        Returns:
            bool: Whether to verify certificate or not
        """
        return self._should_verify_certificate

    def get_headless_mode(self) -> bool:
        """
        Retrieve whether to use headless mode.

        Returns:
            bool: Whether to use headless mode or not
        """
        return self._headless_mode


def make_request(url: str, config: Config) -> requests.models.Response:
    """
    Deliver a response from a request with given configuration.

    Args:
        url (str): Site url
        config (Config): Configuration

    Returns:
        requests.models.Response: A response from a request
    """


class Crawler:
    """
    Crawler implementation.
    """

    #: Url pattern
    url_pattern: re.Pattern | str

    def __init__(self, config: Config) -> None:
        """
        Initialize an instance of the Crawler class.

        Args:
            config (Config): Configuration
        """

    def _extract_url(self, article_bs: Tag) -> str:
        """
        Find and retrieve url from HTML.

        Args:
            article_bs (bs4.Tag): Tag instance

        Returns:
            str: Url from HTML
        """

    def find_articles(self) -> None:
        """
        Find articles.
        """

    def get_search_urls(self) -> list:
        """
        Get seed_urls param.

        Returns:
            list: seed_urls param
        """


# 10


class CrawlerRecursive(Crawler):
    """
    Recursive implementation.

    Get one URL of the title page and find requested number of articles recursively.
    """

    def __init__(self, config: Config) -> None:
        """
        Initialize an instance of the CrawlerRecursive class.

        Args:
            config (Config): Configuration
        """

    def find_articles(self) -> None:
        """
        Find number of article urls requested.
        """


# 4, 6, 8, 10


class HTMLParser:
    """
    HTMLParser implementation.
    """

    def __init__(self, full_url: str, article_id: int, config: Config) -> None:
        """
        Initialize an instance of the HTMLParser class.

        Args:
            full_url (str): Site url
            article_id (int): Article id
            config (Config): Configuration
        """

    def _fill_article_with_text(self, article_soup: BeautifulSoup) -> None:
        """
        Find text of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """

    def _fill_article_with_meta_information(self, article_soup: BeautifulSoup) -> None:
        """
        Find meta information of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """

    def unify_date_format(self, date_str: str) -> datetime.datetime:
        """
        Unify date format.

        Args:
            date_str (str): Date in text format

        Returns:
            datetime.datetime: Datetime object
        """

    def parse(self) -> Article | bool:
        """
        Parse each article.

        Returns:
            Article | bool: Article instance, False in case of request error
        """


def prepare_environment(base_path: pathlib.Path | str) -> None:
    """
    Create ASSETS_PATH folder if no created and remove existing folder.

    Args:
        base_path (pathlib.Path | str): Path where articles stores
    """


def main() -> None:
    """
    Entrypoint for scraper module.
    """


if __name__ == "__main__":
    main()
