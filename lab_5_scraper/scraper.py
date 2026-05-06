"""
Crawler implementation.
"""

# pylint: disable=too-many-arguments, too-many-instance-attributes, unused-import, undefined-variable, unused-argument
import datetime
import json
import pathlib
import re

import requests
from bs4 import BeautifulSoup, Tag

from core_utils.article.article import Article
from core_utils.config_dto import ConfigDTO

class IncorrectSeedURLError(Exception):
    """Seed URL does not match standard pattern."""
    pass

class NumberOfArticlesOutOfRangeError(Exception):
    """Total number of articles is out of range from 1 to 150."""
    pass

class IncorrectNumberOfArticlesError(Exception):
    """Total number of articles to parse is not integer or less than 0."""
    pass

class IncorrectHeadersError(Exception):
    """Headers are not in a form of dictionary."""
    pass

class IncorrectEncodingError(Exception):
    """Encoding must be specified as a string."""
    pass

class IncorrectTimeoutError(Exception):
    """Timeout value must be a positive integer less than 60."""
    pass

class IncorrectVerifyError(Exception):
    """Verify certificate and headless mode values must either be True or False."""
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
        self._config = self._extract_config_content()
        self._validate_config_content()
        self._seed_urls = self._config.seed_urls
        self._num_articles = self._config.total_articles
        self._headers = self._config.headers
        self._encoding = self._config.encoding
        self._timeout = self._config.timeout
        self._should_verify_certificate = self._config.should_verify_certificate
        self._headless_mode = self._config.headless_mode

    def _extract_config_content(self) -> ConfigDTO:
        """
        Get config values.

        Returns:
            ConfigDTO: Config values
        """
        with open(self.path_to_config, "r", encoding="utf-8") as file:
            data = json.load(file)
        return ConfigDTO(**data)

    def _validate_config_content(self) -> None:
        """
        Ensure configuration parameters are not corrupt.
        """
        conf = self._config
        standard_pattern = re.compile(r"https?://(www\.)?")
        if not isinstance(conf.seed_urls, list):
            raise IncorrectSeedURLError()
        for url in conf.seed_urls: 
            if not isinstance(url, str) or not standard_pattern.match(url):
                raise IncorrectSeedURLError()
        if not isinstance(conf.total_articles, int):
            raise IncorrectNumberOfArticlesError()
        if conf.total_articles < 1 or conf.total_articles > 150:
            raise NumberOfArticlesOutOfRangeError()
        if not isinstance(conf.headers, dict):
            raise IncorrectHeadersError()
        if not isinstance(conf.encoding, str):
            raise IncorrectEncodingError()
        if not isinstance(conf.timeout, int) or conf.timeout <= 0 or conf.timeout > 60:
            raise IncorrectTimeoutError()
        if not isinstance(conf.should_verify_certificate, bool):
            raise IncorrectVerifyError()
        if not isinstance(conf.headless_mode, bool):
            raise IncorrectVerifyError()


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
    response = requests.get(
        url,
        headers=config.get_headers(),
        timeout=config.get_timeout(),
        verify=config.get_verify_certificate()
    )
    response.encoding = config.get_encoding()
    return response


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
        self.config = config
        self.urls = []


    def _extract_url(self, article_bs: Tag) -> str:
        """
        Find and retrieve url from HTML.

        Args:
            article_bs (bs4.Tag): Tag instance

        Returns:
            str: Url from HTML
        """
        href = article_bs.get("href")
        if not href:
            return ""
        if href.startswith(('http://', 'https://')):
            return href
        base = self.config.get_seed_urls()[0].rstrip("/")
        return base + href

    def find_articles(self) -> None:
        """
        Find articles.
        """
        for url in self.config.get_seed_urls():
            try:
                response = make_request(url, self.config)
                soup = BeautifulSoup(response.text, "html.parser")
                seed = self.config.get_seed_urls()[0]
                for tag in soup.find_all("a"):
                    link = self._extract_url(tag)
                    if link and link not in self.urls:
                        if seed in link:
                            self.urls.append(link)
                    if len(self.urls) >= self.config.get_num_articles():
                        return
            except Exception:
                continue

    def get_search_urls(self) -> list:
        """
        Get seed_urls param.

        Returns:
            list: seed_urls param
        """
        return self.config.get_seed_urls()


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
